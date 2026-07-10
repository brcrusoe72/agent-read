"""The kill chain — escalating extraction until one strategy wins.

Order, cheapest to most aggressive:
  1. direct       — GET + content selectors
  2. readability  — density scoring (no semantic markup needed)
  3. ua-rotation  — retry under other browser User-Agents (beats naive 403s)
  4. wayback      — Internet Archive snapshot (beats dead/blocked live pages)
  special-cased by URL: pdf (pdfplumber), youtube (yt-dlp transcript)

Every result reports which strategies were tried, so a failure is legible and
never silent. PDF and YouTube support are OPTIONAL extras — if the library
isn't installed, that strategy reports 'not installed' instead of vanishing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from .extract import clean_html, is_paywalled, readability_extract, MIN_USEFUL_CHARS
from .safety import is_safe_url
from .sanitize import scrub

DEFAULT_MAX_CHARS = 15_000
FETCH_TIMEOUT = 15.0
WAYBACK_TIMEOUT = 20.0

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]


@dataclass
class ReadResult:
    url: str
    ok: bool
    content: str | None = None
    strategy: str | None = None
    chars: int = 0
    strategies_tried: list[str] = field(default_factory=list)
    error: str | None = None
    paywalled: bool = False
    threats_redacted: int = 0


def read(url: str, max_chars: int = DEFAULT_MAX_CHARS,
         client: httpx.Client | None = None) -> ReadResult:
    """Extract clean text from one URL. Never raises for a fetch failure —
    returns ReadResult(ok=False, error=...) so callers/agents branch on data."""
    safe, reason = is_safe_url(url)
    if not safe:
        return ReadResult(url, ok=False, error=f"blocked by safety check: {reason}")

    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=FETCH_TIMEOUT)
    try:
        return _run_chain(client, url, max_chars)
    finally:
        if owns_client:
            client.close()


def _run_chain(client: httpx.Client, url: str, max_chars: int) -> ReadResult:
    tried: list[str] = []

    # YouTube has exactly one sensible strategy — don't waste the HTML chain.
    if _is_youtube(url):
        return _finish(url, _strategy_youtube(url), "youtube", tried, max_chars,
                       fail="YouTube transcript failed (install agent-read[youtube]?)")

    # Single initial fetch, reused by direct + readability (no double GET).
    # PDFs are detected by extension OR content-type OR a %PDF body — arxiv-
    # style URLs like /pdf/1706.03762 carry no .pdf suffix.
    html: str | None = None
    tried.append("direct")
    try:
        resp = _fetch(client, url, 0)
    except Exception:
        resp = None

    if resp is not None and _looks_pdf(url, resp):
        tried.append("pdf")
        raw = _extract_pdf_bytes(resp.content)
        if raw:
            return _finalize(url, raw, "pdf", tried, max_chars)
    elif resp is not None and resp.is_success:
        html = resp.text
        raw = clean_html(html, max_chars)
        if raw and not is_paywalled(raw):
            r = _finalize(url, raw, "direct", tried, max_chars)
            if r.ok:
                return r
        tried.append("readability")
        raw = readability_extract(html, max_chars)
        if raw and not is_paywalled(raw):
            r = _finalize(url, raw, "readability", tried, max_chars)
            if r.ok:
                return r

    # Escalate: other User-Agents (beats naive 403s), then Wayback.
    for name, fn in (
        ("ua-rotation", lambda: _strategy_ua_rotation(client, url)),
        ("wayback", lambda: _strategy_wayback(client, url, max_chars)),
    ):
        tried.append(name)
        try:
            raw = fn()
        except Exception:
            raw = None
        if raw:
            r = _finalize(url, raw, name, tried, max_chars)
            if r.ok:
                return r

    # A .pdf URL that failed the fetch above still deserves the pdf lib.
    if _is_pdf_url(url) and "pdf" not in tried:
        tried.append("pdf")
        raw = _strategy_pdf(client, url)
        if raw:
            return _finalize(url, raw, "pdf", tried, max_chars)

    return ReadResult(url, ok=False, strategies_tried=tried,
                      error="all extraction strategies failed")


def _finalize(url: str, raw: str, strategy: str, tried: list[str],
              max_chars: int) -> ReadResult:
    content, redactions = scrub(raw[:max_chars])
    content = content.strip()
    if len(content) < MIN_USEFUL_CHARS:
        # Too little to be real content — let the chain keep escalating.
        return ReadResult(url, ok=False, strategies_tried=tried)
    return ReadResult(
        url, ok=True, content=content, strategy=strategy, chars=len(content),
        strategies_tried=tried, paywalled=is_paywalled(content),
        threats_redacted=redactions,
    )


def _finish(url: str, raw: str | None, strategy: str, tried: list[str],
            max_chars: int, fail: str) -> ReadResult:
    tried.append(strategy)
    if not raw:
        return ReadResult(url, ok=False, strategies_tried=tried, error=fail)
    return _finalize(url, raw, strategy, tried, max_chars) if raw else \
        ReadResult(url, ok=False, strategies_tried=tried, error=fail)


# --- strategies -------------------------------------------------------------

def _fetch(client: httpx.Client, url: str, ua_index: int) -> httpx.Response:
    return client.get(url, headers={
        "User-Agent": USER_AGENTS[ua_index % len(USER_AGENTS)],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })


def _looks_pdf(url: str, resp: httpx.Response) -> bool:
    if _is_pdf_url(url):
        return True
    if "pdf" in resp.headers.get("content-type", "").lower():
        return True
    return resp.content[:5].startswith(b"%PDF")


def _strategy_ua_rotation(client: httpx.Client, url: str) -> str | None:
    for i in range(1, len(USER_AGENTS)):  # 0 already tried by direct
        try:
            r = _fetch(client, url, i)
        except Exception:
            continue
        if r.status_code in (403, 429) or not r.is_success:
            continue
        text = clean_html(r.text, DEFAULT_MAX_CHARS)
        if text and not is_paywalled(text):
            return text
    return None


def _strategy_wayback(client: httpx.Client, url: str, max_chars: int) -> str | None:
    cdx = (f"https://web.archive.org/cdx/search/cdx"
           f"?url={url}&output=json&limit=1&sort=reverse")
    r = client.get(cdx, timeout=FETCH_TIMEOUT)
    if not r.is_success:
        return None
    data = r.json()
    if len(data) <= 1:  # row 0 is the header
        return None
    timestamp = data[1][1]
    snap = client.get(f"https://web.archive.org/web/{timestamp}/{url}",
                      timeout=WAYBACK_TIMEOUT, headers={"User-Agent": USER_AGENTS[0]})
    if not snap.is_success:
        return None
    return clean_html(snap.text, max_chars)


def _strategy_pdf(client: httpx.Client, url: str) -> str | None:
    try:
        r = _fetch(client, url, 0)
    except Exception:
        return None
    return _extract_pdf_bytes(r.content) if r.is_success else None


def _extract_pdf_bytes(data: bytes) -> str | None:
    try:
        import pdfplumber  # optional extra
    except ImportError:
        return None
    import io
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            # x_tolerance=1.5: many PDFs (e.g. arxiv) position words with
            # sub-space gaps; the default tolerance runs them together.
            parts = [p.extract_text(x_tolerance=1.5) for p in pdf.pages[:50]]
        return "\n".join(p for p in parts if p) or None
    except Exception:
        return None


def _strategy_youtube(url: str) -> str | None:
    import os
    import re
    import subprocess
    import tempfile
    from pathlib import Path
    if not _which("yt-dlp"):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "subs")
        try:
            subprocess.run(
                ["yt-dlp", "--write-auto-sub", "--sub-lang", "en",
                 "--sub-format", "vtt", "--skip-download", "--no-playlist",
                 "--max-downloads", "1", "-o", out, url],
                capture_output=True, text=True, timeout=90,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        vtt = Path(tmp) / "subs.en.vtt"
        if not vtt.exists():
            return None
        lines, seen = [], set()
        for line in vtt.read_text().splitlines():
            line = line.strip()
            if (not line or line.startswith("WEBVTT")
                    or re.match(r"^\d{2}:\d{2}", line) or "<" in line):
                continue
            clean = re.sub(r"<[^>]+>", "", line).strip()
            if clean and clean not in seen:
                seen.add(clean)
                lines.append(clean)
        return " ".join(lines) or None


# --- helpers ----------------------------------------------------------------

def _which(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None


def _is_pdf_url(url: str) -> bool:
    return url.lower().rstrip("/").endswith(".pdf")


def _is_youtube(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host.endswith("youtube.com") or host.endswith("youtu.be")
