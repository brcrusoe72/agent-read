"""SSRF protection — the 'safely' half. Carved from agent-search killchain.

An agent will hand this tool whatever URL a page or an LLM produced. That URL
must never be allowed to reach the local network, cloud metadata endpoints,
or a private host. This runs BEFORE any fetch.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Link-shorteners and known dead-ends: fetching them wastes a round trip.
BLOCKED_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly",
    "buff.ly", "is.gd", "v.gd", "short.io",
}

# TLDs dominated by throwaway/malicious hosts. An agent rarely wants these.
SUSPICIOUS_TLDS = {
    ".tk", ".ml", ".ga", ".cf", ".gq",
    ".buzz", ".top", ".work", ".click",
}


def is_safe_url(url: str) -> tuple[bool, str]:
    """Return (ok, reason). reason is '' when ok, else why it was blocked."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "unparseable URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"non-HTTP scheme {parsed.scheme!r}"

    hostname = parsed.hostname
    if not hostname:
        return False, "no hostname"
    host = hostname.lower()

    if host in ("localhost", "localhost.localdomain", "0.0.0.0"):
        return False, "localhost"

    for blocked in BLOCKED_DOMAINS:
        if host == blocked or host.endswith("." + blocked):
            return False, f"blocked domain {blocked}"

    for tld in SUSPICIOUS_TLDS:
        if host.endswith(tld):
            return False, f"suspicious TLD {tld}"

    # IP literal: block private/reserved directly.
    try:
        addr = ipaddress.ip_address(host)
        if _is_internal(addr):
            return False, f"private/reserved IP {addr}"
        return True, ""
    except ValueError:
        pass  # hostname, not an IP — resolve and check below

    # DNS rebinding guard: resolve and reject if ANY address is internal.
    try:
        for _, _, _, _, sockaddr in socket.getaddrinfo(
            host, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        ):
            try:
                addr = ipaddress.ip_address(sockaddr[0])
            except ValueError:
                continue
            if _is_internal(addr):
                return False, f"{host} resolves to private IP {addr}"
    except (socket.gaierror, OSError):
        # Can't resolve — let the fetch attempt fail loudly rather than
        # guess. A dead host is a fetch error, not a safety block.
        pass

    return True, ""


def _is_internal(addr: ipaddress._BaseAddress) -> bool:
    return (
        addr.is_private or addr.is_reserved
        or addr.is_loopback or addr.is_link_local
    )
