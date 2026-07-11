"""The benchmark corpus — real, mostly-stable URLs that exercise the hard cases
a reader has to survive: PDFs with no .html, pages that block non-browser
clients, JS-only SPAs, dead/moved links, and paywalls.

Kept deliberately stable (Wikipedia, arXiv IDs, iconic PDFs, gov forms) so the
number is *reproducible* — re-running months later should land close. The
`tag` is only for grouping the writeup; scoring is empirical and identical for
every URL.
"""

URLS = [
    # --- plain articles: control. Both tool and baseline should pass. -------
    ("plain", "https://en.wikipedia.org/wiki/Overall_equipment_effectiveness"),
    ("plain", "https://en.wikipedia.org/wiki/Single-minute_exchange_of_die"),
    ("plain", "https://en.wikipedia.org/wiki/Shift_work"),
    ("plain", "https://en.wikipedia.org/wiki/Levelized_cost_of_electricity"),
    ("plain", "https://www.paulgraham.com/ds.html"),
    ("plain", "https://peps.python.org/pep-0008/"),
    ("plain", "https://www.gnu.org/philosophy/free-sw.html"),
    ("plain", "https://go.dev/blog/slices"),
    ("plain", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/User-Agent"),

    # --- government / data pages: heavier, real content ----------------------
    ("gov", "https://www.energy.gov/eere/solar/solar-photovoltaic-technology-basics"),
    ("gov", "https://www.eia.gov/energyexplained/electricity/"),
    ("gov", "https://ourworldindata.org/electricity-mix"),
    ("gov", "https://www.osha.gov/laws-regs"),

    # --- PDFs with no .html: baseline strip-tags gets binary garbage ---------
    ("pdf", "https://arxiv.org/pdf/1706.03762"),   # Attention Is All You Need
    ("pdf", "https://arxiv.org/pdf/2005.14165"),   # GPT-3
    ("pdf", "https://arxiv.org/pdf/2201.11903"),   # Chain-of-Thought
    ("pdf", "https://arxiv.org/pdf/1810.04805"),   # BERT
    ("pdf", "https://arxiv.org/pdf/2307.09288"),   # Llama 2
    ("pdf", "https://arxiv.org/pdf/1512.03385"),   # ResNet
    ("pdf", "https://bitcoin.org/bitcoin.pdf"),    # Bitcoin whitepaper
    ("pdf", "https://www.irs.gov/pub/irs-pdf/fw4.pdf"),   # IRS W-4 form
    ("pdf", "https://www.irs.gov/pub/irs-pdf/f1040.pdf"), # IRS 1040 form

    # --- bot-hostile / JS-only / auth-walls: direct fetch is blocked or empty
    ("blocked", "https://www.reddit.com/r/manufacturing/"),
    ("blocked", "https://medium.com/tag/lean-manufacturing"),
    ("blocked", "https://www.quora.com/What-is-OEE-in-manufacturing"),
    ("blocked", "https://www.glassdoor.com/Reviews/index.htm"),
    ("blocked", "https://www.crunchbase.com/organization/openai"),
    ("blocked", "https://www.linkedin.com/company/general-motors/"),
    ("blocked", "https://twitter.com/nasa"),          # JS SPA — may defeat both
    ("blocked", "https://www.instagram.com/nasa/"),   # JS SPA — may defeat both

    # --- paywalled publishers: stub, block, or full article via Wayback ------
    ("paywall", "https://www.nytimes.com/section/business"),
    ("paywall", "https://www.wsj.com/tech"),
    ("paywall", "https://www.economist.com/business"),
    ("paywall", "https://www.ft.com/companies"),
    ("paywall", "https://www.washingtonpost.com/business/"),
    ("paywall", "https://www.wired.com/category/business/"),
    ("paywall", "https://www.bloomberg.com/technology"),

    # --- dead / moved: live fetch 404s; Wayback has the snapshot -------------
    ("dead", "https://blog.ycombinator.com/the-airbnbs/"),
    ("dead", "https://www.google.com/googlebooks/uspto.html"),
    ("dead", "https://arstechnica.com/gadgets/2015/01/this-page-does-not-exist-404/"),
]
