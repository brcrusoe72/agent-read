"""agent-read — turn any URL into clean text for an AI agent.

    agent-read https://example.com/article
    agent-read a.com b.com c.com --json          # batch, concurrent
    agent-read https://site.com/paper.pdf --max-chars 30000
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

from . import __version__
from .killchain import DEFAULT_MAX_CHARS, ReadResult, read
from .render import to_json, to_terminal

MAX_CONCURRENCY = 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-read",
        description="Turn any URL into clean text. Survives paywalls, 403s, "
        "PDFs, and YouTube. No server, no API key.",
    )
    parser.add_argument("urls", nargs="+", help="one or more URLs to read")
    parser.add_argument("--json", action="store_true", help="JSON output for agents")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                        help=f"cap per-URL content (default {DEFAULT_MAX_CHARS})")
    parser.add_argument("--version", action="version", version=f"agent-read {__version__}")
    parser.add_argument("--allow-external-downloader", action="store_true",
                        help="allow yt-dlp for trusted YouTube URLs; outside protected HTTP fetching")
    args = parser.parse_args(argv)

    results = _read_all(args.urls, args.max_chars, args.allow_external_downloader)

    print(to_json(results) if args.json else to_terminal(results))

    # Loud exit code: fail if EVERY URL failed. An agent branches on this
    # without parsing, and a partial batch success still exits 0.
    return 0 if any(r.ok for r in results) else 1


def _read_all(urls: list[str], max_chars: int, allow_external_downloader: bool = False) -> list[ReadResult]:
    if len(urls) == 1:
        return [read(urls[0], max_chars=max_chars, allow_external_downloader=allow_external_downloader)]
    # Each worker creates the same protected client as a single-URL read.
    def _one(u: str) -> ReadResult:
        return read(u, max_chars=max_chars, allow_external_downloader=allow_external_downloader)

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
        return list(pool.map(_one, urls))


if __name__ == "__main__":
    sys.exit(main())
