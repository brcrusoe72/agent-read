"""Extraction logic — pure, no network."""

from agent_read.extract import clean_html, is_paywalled, readability_extract

ARTICLE = """
<html><body>
<nav><a href="/">Home</a><a href="/about">About</a></nav>
<article>
<p>The Transformer architecture dispenses with recurrence entirely.</p>
<p>It relies solely on attention mechanisms to draw global dependencies
between input and output, which makes it far more parallelizable than
prior sequence models and cheaper to train at scale on modern hardware.</p>
</article>
<footer>Copyright 2026</footer>
</body></html>
"""


def test_clean_html_pulls_article_drops_chrome():
    text = clean_html(ARTICLE, max_chars=5000)
    assert "Transformer architecture" in text
    assert "Home" not in text and "Copyright" not in text


def test_readability_finds_dense_block():
    text = readability_extract(ARTICLE, max_chars=5000)
    assert text and "attention mechanisms" in text


def test_paywall_stub_detected():
    assert is_paywalled("Subscribe to read the rest of this premium content.")
    assert not is_paywalled("A" * 3000)
