"""Japanese-specific helpers: shinjitai (新字体) → kyūjitai (旧字体) conversion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

_DATA_PATH: Final[Path] = Path(__file__).parent / 'data' / 'shinjitai_kyujitai.json'


def _load_table() -> dict[str, list[str]]:
    raw = json.loads(_DATA_PATH.read_text(encoding='utf-8'))
    return {k: v for k, v in raw.items() if not k.startswith('_')}


_TABLE: Final[dict[str, list[str]]] = _load_table()


def is_japanese(language: str) -> bool:
    """Return True when *language* names Japanese, ignoring case and whitespace."""
    return language.strip().casefold() == 'japanese'


def to_kyujitai_template(text: str) -> str | None:
    """Rewrite *text* into a kyūjitai template; return None if no substitution applies.

    For each character:
    * not in the table → emit verbatim.
    * exactly one kyūjitai candidate → emit that candidate directly.
    * multiple candidates → emit ``[A|B|C]`` so the LLM can pick by context.

    Returns the assembled string when at least one character was rewritten or
    bracketed, otherwise None (so callers can omit the Variant row).
    """
    out: list[str] = []
    changed = False
    for ch in text:
        forms = _TABLE.get(ch)
        if forms is None:
            out.append(ch)
        elif len(forms) == 1:
            out.append(forms[0])
            changed = True
        else:
            out.append('[' + '|'.join(forms) + ']')
            changed = True
    return ''.join(out) if changed else None
