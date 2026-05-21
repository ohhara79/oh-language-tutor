"""Source-language predicates used to gate language-specific prompt sections.

The Learning-language field in the UI is free text, so callers may pass
``'Japanese'``, ``'Mandarin Chinese'``, ``'Korean (Seoul)'``, etc. Each
predicate does a case-insensitive substring match on the canonical English
name so all of those route to the right CJK section.
"""

from __future__ import annotations

import unicodedata


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


# Unicode codepoint ranges per script, kept in tagged tuples so the
# literals live in named data rather than scattered inline comparisons.
_HANGUL_RANGES: tuple[tuple[int, int], ...] = (
    (0xAC00, 0xD7AF),  # Hangul Syllables
    (0x1100, 0x11FF),  # Hangul Jamo
    (0xA960, 0xA97F),  # Hangul Jamo Extended-A
    (0xD7B0, 0xD7FF),  # Hangul Jamo Extended-B
    (0x3130, 0x318F),  # Hangul Compatibility Jamo
)

_KANA_RANGES: tuple[tuple[int, int], ...] = (
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x31F0, 0x31FF),  # Katakana Phonetic Extensions
)

_HAN_RANGES: tuple[tuple[int, int], ...] = (
    (0x3400, 0x4DBF),  # CJK Ext A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0x20000, 0x2A6DF),  # CJK Ext B
    (0x2A700, 0x2EBEF),  # CJK Ext C/D/E/F
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
)


def _any_in_ranges(text: str, ranges: tuple[tuple[int, int], ...]) -> bool:
    for ch in text:
        cp = ord(ch)
        for start, end in ranges:
            if start <= cp <= end:
                return True
    return False


def text_has_hangul(text: str) -> bool:
    """Return True if *text* contains any Hangul syllable or Jamo."""
    return _any_in_ranges(text, _HANGUL_RANGES)


def text_has_kana(text: str) -> bool:
    """Return True if *text* contains any Japanese kana (hiragana or katakana)."""
    return _any_in_ranges(text, _KANA_RANGES)


def text_has_han(text: str) -> bool:
    """Return True if *text* contains any Han (CJK Unified) ideograph."""
    return _any_in_ranges(text, _HAN_RANGES)


def text_has_letters(text: str) -> bool:
    """Return True if *text* contains any character classified as a letter."""
    return any(unicodedata.category(ch).startswith('L') for ch in text)


def _classify_text(text: str) -> str:
    """Bucket *text* by primary script.

    Returns one of ``'korean'``, ``'japanese'``, ``'han-only'``,
    ``'latin-or-other'``, or ``'unknown'`` (when there's no letter to
    judge on — pure whitespace/digits/punctuation).
    """
    if text_has_hangul(text):
        return 'korean'
    if text_has_kana(text):
        return 'japanese'
    if text_has_han(text):
        return 'han-only'
    if text_has_letters(text):
        return 'latin-or-other'
    return 'unknown'


_BUCKET_LABEL = {
    'korean': 'Korean',
    'japanese': 'Japanese',
    'han-only': 'Chinese (or kanji-only)',
    'latin-or-other': 'a non-CJK language',
}


def detect_language_mismatch(learning_language: str, text: str) -> str | None:
    """Return a user-facing error message if *text*'s script can't match
    *learning_language*, else ``None``.

    Detection is script-based: it reliably catches CJK ↔ non-CJK and
    cross-CJK confusions, but cannot distinguish Latin-script languages
    from each other (English vs. French both classify as
    ``'latin-or-other'``). Pure-kanji lines are accepted for both
    Japanese and Chinese Learning Languages since their script is the
    same.
    """
    bucket = _classify_text(text)
    if bucket == 'unknown':
        return None

    if is_korean(learning_language):
        expected = {'korean'}
    elif is_japanese(learning_language):
        expected = {'japanese', 'han-only'}
    elif is_chinese(learning_language):
        expected = {'han-only'}
    else:
        expected = {'latin-or-other'}

    if bucket in expected:
        return None

    return (
        f'Text appears to be {_BUCKET_LABEL[bucket]}, but Learning Language is set to '
        f'{learning_language.strip()!r}. Update the Learning Language in the menu and try again.'
    )
