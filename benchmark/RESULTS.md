# agent-read benchmark — results

## The number: 85% vs. 48%

On 40 real, hard URLs, `agent-read` returned usable clean text for **34 (85%)**.
A strong naive baseline — a browser User-Agent + strip-tags, single fetch —
got **19 (48%)**. `agent-read` won 15 URLs the baseline couldn't, and lost
**zero**: there is no URL in the corpus the baseline read and `agent-read`
didn't.

| | usable text |
|---|---|
| **agent-read** | **34 / 40 = 85%** |
| naive baseline | 19 / 40 = 48% |
| only agent-read succeeds | 15 |
| only baseline succeeds | **0** |

## Where the 37-point gap comes from

18 of the 40 URLs are controls — plain articles and government pages — where
both approaches already succeed (9/9 and 4/4). The entire gap is on the hard
half:

| category | agent-read | baseline | how agent-read won |
|---|:---:|:---:|---|
| PDF (arXiv, IRS, Bitcoin) | **9 / 9** | 0 / 9 | `pdf` — baseline gets binary mojibake |
| paywall (WSJ, WaPo, FT, NYT…) | 5 / 7 | 2 / 7 | `wayback` / `ua-rotation` rescue |
| bot-blocked (Reddit, Glassdoor, Medium…) | 5 / 8 | 2 / 8 | `wayback` rescue |
| dead / moved | 2 / 3 | 2 / 3 | *(see notes)* |
| plain article | 9 / 9 | 9 / 9 | `direct` |
| government / data | 4 / 4 | 4 / 4 | `direct` |

The kill chain's escalation *is* the 15 rescues. Every `agent-read` success and
which strategy earned it:

| winning strategy | URLs |
|---|:---:|
| direct | 19 |
| **pdf** | **9** |
| **wayback** | **5** |
| **ua-rotation** | **1** |

`direct` handles what the baseline also handles. Everything past it — 15 URLs —
is pure gain: PDFs the baseline reads as garbage, and live pages that 403 or
paywall the fetch but sit readable in the Internet Archive.

## Method

- 40 URLs in `urls.py`, chosen to be **stable/reproducible** (Wikipedia,
  arXiv IDs, iconic PDFs, IRS forms) and to stress each hard path.
- **agent-read**: `read(url)` from the library; success = the returned text
  passes the judge below.
- **baseline**: one `httpx.get` with a real **Chrome** User-Agent + Accept
  headers, follow redirects, then regex-strip tags. Deliberately *strong* — a
  Chrome UA, not httpx's default — so the wins measure the escalation chain,
  not merely setting a header.
- **Identical success judge** for both: ≥200 chars, not a paywall stub
  (`is_paywalled`), and the text looks like prose (letter-ratio + word-break
  test). The prose test is what stops raw PDF bytes decoded as text from
  scoring the baseline a false win — without it the strip-tags baseline would
  look far better on PDFs than it actually is (it returns megabytes of mojibake).

## Honest notes

- **It's 40, not 50.** The corpus favors reproducibility over count; each URL
  is one an agent actually hits, not filler.
- **The "dead" category barely exercised Wayback:** 2 of the 3 presumed-dead
  links were still served live, and the one true 404 (arstechnica) defeated
  both — it isn't in the archive either. Wayback earned its keep on the
  *paywall* and *blocked* rows instead (5 rescues there).
- **Six URLs defeat agent-read too:** Bloomberg, Economist, Crunchbase, Quora,
  Instagram, and the arstechnica 404 — heavy JS SPAs or hostile walls with no
  archived text version. `agent-read` runs no headless browser by design; that
  is [agent-web](https://github.com/brcrusoe72/agent-web)'s job.
- Single run, single automated judge, n=40. Directional, not publication-grade.

## Reproduce

```bash
uv sync --extra dev --extra pdf
python benchmark/run_benchmark.py
```
