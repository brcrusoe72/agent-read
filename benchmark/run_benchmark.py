#!/usr/bin/env python3
"""The number for agent-read: on a corpus of hard, real-world URLs, what share
does it turn into usable clean text — versus the naive thing a dev writes in
20 lines (browser-UA httpx.get + strip tags, single fetch, no fallback)?

    python benchmark/run_benchmark.py            # run + print table
    python benchmark/run_benchmark.py --md        # also write RESULTS.md body

The baseline is deliberately *strong* (a real Chrome User-Agent + Accept
headers, follow redirects) so agent-read's wins come from the escalation chain
— readability, UA-rotation, Wayback, PDF — not merely from setting a UA.

Success is judged identically for both: >=200 chars, not a paywall stub, and
the text looks like prose (letter ratio + word breaks) — the last test is what
stops PDF-bytes-as-mojibake from wrongly scoring the strip-tags baseline a win.
"""
from __future__ import annotations

import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from urls import URLS  # noqa: E402

sys.path.insert(0, __file__.rsplit("/", 2)[0])
from agent_read.extract import is_paywalled  # noqa: E402
from agent_read.killchain import read  # noqa: E402

MIN_CHARS = 200
CHROME_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_STRIP_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def looks_like_text(t: str) -> bool:
    """Cheap prose test: enough length, mostly letters, real word breaks.
    Rejects binary/PDF mojibake and tag soup that clears the length bar."""
    t = t.strip()
    if len(t) < MIN_CHARS:
        return False
    letters = sum(c.isalpha() for c in t)
    if letters / len(t) < 0.5:          # too many symbols → not prose
        return False
    if t.count(" ") / len(t) < 0.04:    # no spaces → not words
        return False
    return True


def usable(text: str | None) -> bool:
    return bool(text) and looks_like_text(text) and not is_paywalled(text.strip())


def baseline(url: str) -> str:
    """What a naive 20-line reader gets: one browser-UA fetch, strip tags."""
    try:
        r = httpx.get(url, follow_redirects=True, timeout=15.0, headers={
            "User-Agent": CHROME_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
    except Exception:
        return ""
    if not r.is_success:
        return ""
    html = _TAG_RE.sub(" ", r.text)
    return _WS_RE.sub(" ", _STRIP_RE.sub(" ", html)).strip()


def run_one(tag: str, url: str) -> dict:
    t0 = time.time()
    try:
        rr = read(url)
        tool_text = rr.content if rr.ok else None
        strategy = rr.strategy or "-"
    except Exception as exc:
        tool_text, strategy = None, f"err:{type(exc).__name__}"
    base_text = baseline(url)
    return {
        "tag": tag, "url": url,
        "tool_ok": usable(tool_text), "strategy": strategy,
        "tool_chars": len(tool_text or ""),
        "base_ok": usable(base_text), "base_chars": len(base_text),
        "secs": round(time.time() - t0, 1),
    }


def main() -> int:
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(run_one, t, u): u for t, u in URLS}
        for fut in as_completed(futs):
            rows.append(fut.result())
    rows.sort(key=lambda r: (r["tag"], r["url"]))

    n = len(rows)
    tool = sum(r["tool_ok"] for r in rows)
    base = sum(r["base_ok"] for r in rows)
    only_tool = sum(r["tool_ok"] and not r["base_ok"] for r in rows)
    only_base = sum(r["base_ok"] and not r["tool_ok"] for r in rows)

    print(f"\n=== agent-read benchmark — {n} hard URLs ===\n")
    print(f"{'tag':8} {'tool':4} {'base':4} {'strategy':12} "
          f"{'t.chars':>8} {'b.chars':>8}  url")
    for r in rows:
        print(f"{r['tag']:8} {'Y' if r['tool_ok'] else '.':4} "
              f"{'Y' if r['base_ok'] else '.':4} {r['strategy']:12} "
              f"{r['tool_chars']:>8} {r['base_chars']:>8}  {r['url']}")

    print(f"\nagent-read : {tool}/{n} = {tool/n:.0%}")
    print(f"baseline   : {base}/{n} = {base/n:.0%}")
    print(f"only agent-read wins: {only_tool}   only baseline wins: {only_base}")

    # by tag
    print("\nby category:")
    tags = sorted({r["tag"] for r in rows})
    for tg in tags:
        sub = [r for r in rows if r["tag"] == tg]
        st = sum(r["tool_ok"] for r in sub)
        sb = sum(r["base_ok"] for r in sub)
        print(f"  {tg:8} agent-read {st}/{len(sub)}   baseline {sb}/{len(sub)}")

    # winning strategies among tool successes
    print("\nagent-read winning strategies:")
    from collections import Counter
    strat = Counter(r["strategy"] for r in rows if r["tool_ok"])
    for s, c in strat.most_common():
        print(f"  {s:12} {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
