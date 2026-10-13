"""Fail-closed URL/DNS validation for public web retrieval."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_DOMAINS = {'bit.ly', 'tinyurl.com', 't.co', 'goo.gl', 'ow.ly',
                   'buff.ly', 'is.gd', 'v.gd', 'short.io'}
SUSPICIOUS_TLDS = {'.tk', '.ml', '.ga', '.cf', '.gq', '.buzz', '.top', '.work', '.click'}


class UnsafeURL(ValueError):
    """URL, resolution, or redirect is not a public web destination."""


def public_addresses(host: str, port: int, *, resolver=None) -> tuple[str, ...]:
    """Validate every answer, returning only numeric connection destinations."""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            rows = (resolver or socket.getaddrinfo)(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            values = [row[4][0] for row in rows]
        except (OSError, ValueError, TypeError, IndexError) as exc:
            raise UnsafeURL('DNS resolution failed') from exc
    else:
        values = [str(literal)]
    if not values:
        raise UnsafeURL('DNS returned no addresses')
    addresses = []
    for value in values:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise UnsafeURL('Invalid DNS address') from exc
        # is_global alone includes multicast on supported Python versions.
        if (not address.is_global or address.is_multicast or address.is_reserved
                or address.is_unspecified or '%' in value):
            raise UnsafeURL('Non-public destination blocked')
        if address.version == 6 and address.ipv4_mapped is not None:
            mapped = address.ipv4_mapped
            if not mapped.is_global or mapped.is_multicast or mapped.is_reserved:
                raise UnsafeURL('Non-public mapped address blocked')
        addresses.append(address.compressed)
    return tuple(dict.fromkeys(addresses))


def validate_url(url: str) -> tuple[str, int]:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or '').rstrip('.').encode('idna').decode('ascii').lower()
        port = parsed.port
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeURL('URL credentials are not allowed')
    except (ValueError, UnicodeError) as exc:
        raise UnsafeURL('Malformed URL') from exc
    if parsed.scheme not in ('http', 'https'):
        raise UnsafeURL('Only HTTP(S) URLs are allowed')
    if not host or port == 0:
        raise UnsafeURL('Invalid host or port')
    if host in ('localhost', 'localhost.localdomain'):
        raise UnsafeURL('Localhost blocked')
    if any(host == d or host.endswith('.' + d) for d in BLOCKED_DOMAINS):
        raise UnsafeURL('Blocked domain')
    if any(host.endswith(tld) for tld in SUSPICIOUS_TLDS):
        raise UnsafeURL('Blocked hostname policy')
    return host, port or (443 if parsed.scheme == 'https' else 80)


def is_safe_url(url: str) -> tuple[bool, str]:
    try:
        host, port = validate_url(url)
        public_addresses(host, port)
        return True, ''
    except (ValueError, TypeError, AttributeError) as exc:
        return False, str(exc)
