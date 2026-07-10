"""Output: readable text for humans, JSON for agents."""

from __future__ import annotations

import dataclasses
import json

from .killchain import ReadResult


def to_json(results: list[ReadResult]) -> str:
    payload = [dataclasses.asdict(r) for r in results]
    # Single URL → emit the object, not a one-item array. Easier for agents.
    return json.dumps(payload[0] if len(payload) == 1 else payload, indent=2)


def to_terminal(results: list[ReadResult]) -> str:
    blocks = []
    for r in results:
        if r.ok:
            head = f"# {r.url}\n[strategy: {r.strategy} · {r.chars} chars"
            if r.paywalled:
                head += " · paywall stub?"
            if r.threats_redacted:
                head += f" · {r.threats_redacted} injection(s) redacted"
            head += "]"
            blocks.append(f"{head}\n\n{r.content}")
        else:
            blocks.append(
                f"# {r.url}\n[FAILED: {r.error}]\n"
                f"[tried: {', '.join(r.strategies_tried) or 'none'}]"
            )
    return "\n\n" + ("\n\n" + "─" * 60 + "\n\n").join(blocks)
