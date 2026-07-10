"""HTML → readable text. Carved from agent-search killchain.

Two extractors:
- clean_html: targeted content selectors, fall back to body text.
- readability_extract: score blocks by paragraph density vs link density,
  take the winner. Beats clean_html on pages with no semantic markup.

Plus paywall-stub detection, so we don't return "subscribe to continue" as
if it were the article.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

CONTENT_SELECTORS = [
    "main", "article", "[role=main]", ".content", "#content",
    ".post-content", ".entry-content", ".article-body", ".post-body",
    ".story-body", ".td-post-content", ".blog-content", ".page-content",
    "#article-body", ".article__body", ".article-text",
]

GARBAGE_TAGS = [
    "script", "style", "nav", "footer", "header", "aside",
    "iframe", "noscript", "svg", "form",
]

GARBAGE_CLASSES = [
    ".sidebar", ".comments", ".related", ".advertisement", ".ad",
    ".social-share", ".newsletter-signup", ".cookie-banner",
    ".popup", ".modal", ".nav-menu", ".breadcrumb",
]

PAYWALL_SIGNALS = [
    "subscribe to read", "premium content", "paywall",
    "sign up to continue", "members only", "login to view",
    "create a free account", "already a subscriber",
    "this content is for subscribers", "unlock this article",
    "start your free trial", "exclusive content",
]

MIN_USEFUL_CHARS = 200


def _strip_garbage(soup: BeautifulSoup) -> None:
    for tag in soup(GARBAGE_TAGS):
        tag.decompose()
    for selector in GARBAGE_CLASSES:
        for el in soup.select(selector):
            el.decompose()


def clean_html(html: str, max_chars: int) -> str | None:
    """Targeted content extraction; body-text fallback."""
    soup = BeautifulSoup(html, "html.parser")
    _strip_garbage(soup)

    for selector in CONTENT_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) >= MIN_USEFUL_CHARS:
                return text[:max_chars]

    text = soup.get_text(separator="\n", strip=True)
    return text[:max_chars] if len(text) >= MIN_USEFUL_CHARS else None


def readability_extract(html: str, max_chars: int) -> str | None:
    """Density-scored extraction — best block by text length and paragraph
    count, penalized for link density (nav/menu blocks are link-heavy)."""
    soup = BeautifulSoup(html, "html.parser")
    _strip_garbage(soup)

    best_score, best_text = 0.0, None
    for tag in soup.find_all(["div", "article", "section", "main"]):
        text = tag.get_text(strip=True)
        if len(text) < MIN_USEFUL_CHARS:
            continue
        p_count = len(tag.find_all("p"))
        link_density = len(tag.find_all("a")) / max(p_count, 1)
        score = len(text) + (p_count * 100) - (link_density * 200)
        if score > best_score:
            best_score, best_text = score, text

    return best_text[:max_chars] if best_text else None


def is_paywalled(text: str) -> bool:
    """A short chunk that reads like a subscribe-wall stub."""
    if len(text) > 2000:
        return False
    lower = text.lower()
    return any(sig in lower for sig in PAYWALL_SIGNALS)
