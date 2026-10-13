"""Live contract tests — the kill chain against the real internet.

These are what actually prove the moat: real pages, real obstacles. Network
required; skipped cleanly offline.
"""

import httpx
import pytest

from agent_read.killchain import read


def _online() -> bool:
    try:
        httpx.get("https://example.com", timeout=5)
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _online(), reason="offline")


def test_reads_a_normal_page():
    r = read("https://en.wikipedia.org/wiki/Transformer_(deep_learning_architecture)")
    assert r.ok
    assert r.chars > 500
    assert r.strategy in ("direct", "readability", "ua-rotation", "wayback")


def test_safety_block_is_loud_not_empty():
    r = read("http://169.254.169.254/latest/meta-data/")
    assert not r.ok
    assert "safety" in (r.error or "")


def test_dns_failure_reports_safety_refusal():
    # DNS failure now fails closed before any extraction strategy runs.
    r = read("https://this-domain-does-not-exist-abc123xyz.example")
    assert not r.ok
    assert "safety" in (r.error or "")
    assert not r.strategies_tried
