"""Source-language predicates used to gate language-specific prompt sections.

The Learning-language field in the UI is free text, so callers may pass
``'Japanese'``, ``'Mandarin Chinese'``, ``'Korean (Seoul)'``, etc. Each
predicate does a case-insensitive substring match on the canonical English
name so all of those route to the right CJK section.
"""

from __future__ import annotations


def _matches(language: str, name: str) -> bool:
    return name in language.strip().casefold()


def is_chinese(language: str) -> bool:
    """Return True when *language* names a Chinese variety (Mandarin, etc.)."""
    return _matches(language, 'chinese')


def is_japanese(language: str) -> bool:
    """Return True when *language* names Japanese."""
    return _matches(language, 'japanese')


def is_korean(language: str) -> bool:
    """Return True when *language* names Korean."""
    return _matches(language, 'korean')
