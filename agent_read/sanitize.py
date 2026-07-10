"""Prompt-injection scrubbing — the other half of 'safely'.

Fetched page content is UNTRUSTED. It may carry text engineered to hijack the
agent reading it ("ignore previous instructions", fake tool calls, hidden
system prompts). We redact the highest-signal patterns and report the count so
the caller knows the page tried something.

This is a deliberately small, high-precision set — not the 70-pattern engine
from agent-search. v1 favors few false positives over exhaustive coverage;
widen only when a real page slips something through.
"""

from __future__ import annotations

import re

_REDACTION = "[redacted: possible prompt injection]"

# Each pattern targets a well-known injection shape. Case-insensitive, and we
# keep them specific enough that ordinary prose won't trip them.
_PATTERNS = [
    r"ignore (?:all |any )?(?:previous|prior|above) instructions",
    r"disregard (?:all |any )?(?:previous|prior|above) (?:instructions|context)",
    r"forget (?:everything|all) (?:above|before|you were told)",
    r"you are now (?:a|an|in) [^.\n]{0,60}(?:mode|assistant|dan)",
    r"new (?:system )?(?:instructions?|prompt|directive)s?\s*[:\-]",
    r"</?(?:system|assistant|user)>",
    r"\[/?(?:system|inst|instructions)\]",
    r"<\|(?:im_start|im_end|system|endoftext)\|>",
    r"do not (?:tell|inform|alert) the user",
    r"reveal (?:your|the) (?:system )?(?:prompt|instructions)",
    r"exfiltrat\w+|send (?:the |all )?(?:data|secrets?|keys?) to",
    r"(?:print|output|repeat) (?:your |the )?(?:system )?prompt",
]

_COMPILED = re.compile("|".join(f"(?:{p})" for p in _PATTERNS), re.IGNORECASE)


def scrub(text: str) -> tuple[str, int]:
    """Redact injection patterns. Returns (clean_text, redaction_count)."""
    if not text:
        return text, 0
    count = 0

    def _sub(_match: re.Match) -> str:
        nonlocal count
        count += 1
        return _REDACTION

    cleaned = _COMPILED.sub(_sub, text)
    return cleaned, count
