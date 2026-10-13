# agent-read

Turn any URL into clean text for an AI agent. Survives paywalls, 403s, PDFs,
and YouTube. No server, no API key.

```bash
uv tool install agent-read        # or: pipx install agent-read
agent-read https://example.com/article
```

```
# https://example.com/article
[strategy: direct · 4821 chars]

The full article text, stripped of nav, ads, and cookie banners...
```

Agents use `--json`, and can batch URLs (fetched concurrently):

```bash
agent-read a.com b.com c.com --json
```

```json
{
  "url": "https://example.com/article",
  "ok": true,
  "content": "...",
  "strategy": "wayback",
  "chars": 4821,
  "strategies_tried": ["direct", "readability", "ua-rotation", "wayback"],
  "paywalled": false,
  "threats_redacted": 0
}
```

## Why

Web *search* is a commodity — every agent already has it. Reliably *reading*
what search returns is the hard part: pages 403 you, hide behind paywalls, or
are PDFs and videos. `agent-read` is one command that escalates through
strategies until one works, and tells you which one did.

## The kill chain

Cheapest strategy first; escalates until one succeeds:

1. **direct** — GET + smart content selectors
2. **readability** — density scoring for pages with no semantic markup
3. **ua-rotation** — retry under other browser User-Agents (beats naive 403s)
4. **wayback** — Internet Archive snapshot (beats dead or blocked live pages)

PDF (`.pdf` URLs) and explicitly enabled YouTube transcripts get dedicated paths. Every result
lists `strategies_tried`, so a failure is legible, never silent.

## Safe by default

Fetched content is untrusted, so `agent-read`:

- **Validates every HTTP target and redirect** — rejects unresolved names,
  non-public IPv4/IPv6 addresses, URL credentials, and non-HTTP schemes.
  Connections use validated IP addresses while retaining the original TLS
  hostname. Single and batch reads use the same protected transport.
- **Bounds ordinary HTTP responses** to 10 MiB and redirects to five hops.
  This is a fetch boundary, not an operating-system sandbox for PDF parsing.
- **Ignores environment proxies** in the default client so an implicit proxy
  cannot bypass destination validation.
- **Redacts prompt injections** in the returned text (fake system prompts,
  "ignore previous instructions", exfiltration lures) and reports the count.
- **Flags paywall stubs** instead of returning "subscribe to continue" as if
  it were the article.

## Optional extras

PDF and YouTube are opt-in so the base install stays tiny:

```bash
uv tool install "agent-read[pdf]"       # pdfplumber
# YouTube transcripts shell out to yt-dlp — install it on PATH.
```

YouTube uses an external process with its own networking. It is disabled by
default because the protected HTTP transport cannot constrain that process.
For a trusted YouTube URL, explicitly opt in:

```bash
agent-read --allow-external-downloader https://www.youtube.com/watch?v=VIDEO_ID
```

The equivalent Python option is `read(url, allow_external_downloader=True)`.
When explicitly supplying `read(..., client=...)`, the caller owns transport
security: use `agent_read.fetch.public_client()` for DNS pinning. Plain custom
HTTPX clients retain redirect checks but do not receive connection pinning.

Without optional dependencies, a PDF or YouTube URL fails loudly ("install agent-read[pdf]?")
rather than silently.

## Non-goals

- **No search.** Pair it with your agent's web search, or a scholarly one.
  `agent-read` is the reader, not the finder.
- **No JS rendering / headless browser.** If a page needs a full browser,
  that's a different tool (e.g. agent-browser).
- **No Google Cache / meta-search fallbacks.** Both need a server or are dead;
  this stays keyless and self-contained.

## The number

On 40 real, hard URLs (PDFs, paywalls, bot-blocked pages, dead links),
`agent-read` returns usable clean text **85% of the time — vs. 48%** for a
strong naive baseline (browser User-Agent + strip-tags, single fetch). It wins
15 URLs the baseline can't and loses **zero**. PDFs alone are **9/9 vs. 0/9**;
Wayback and UA-rotation rescue paywalled and blocked pages the baseline gets a
403 or a stub on. [Full results + method](benchmark/RESULTS.md); reproduce with
`python benchmark/run_benchmark.py`.

## Development

```bash
uv sync --extra dev --extra pdf
uv run pytest        # pure-logic tests + live contract tests (network)
```

## License

MIT
