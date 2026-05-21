"""Tests for ``tutor.languages`` source-language predicates."""

from __future__ import annotations

from tutor.languages import is_chinese, is_japanese, is_korean


def test_is_japanese_canonical() -> None:
    assert is_japanese('Japanese')


def test_is_japanese_case_and_whitespace_insensitive() -> None:
    assert is_japanese('japanese')
    assert is_japanese('JAPANESE')
    assert is_japanese('  Japanese  ')


def test_is_japanese_rejects_other_languages() -> None:
    assert not is_japanese('Korean')
    assert not is_japanese('Chinese')
    assert not is_japanese('Mandarin Chinese')
    assert not is_japanese('English')
    assert not is_japanese('')


def test_is_chinese_canonical_and_mandarin_prefix() -> None:
    assert is_chinese('Chinese')
    assert is_chinese('chinese')
    assert is_chinese('Mandarin Chinese')
    assert is_chinese('  Traditional Chinese  ')


def test_is_chinese_rejects_other_languages() -> None:
    assert not is_chinese('Japanese')
    assert not is_chinese('Korean')
    assert not is_chinese('English')
    assert not is_chinese('Mandarin')  # bare "Mandarin" without "Chinese" doesn't match
    assert not is_chinese('')


def test_is_korean_canonical_and_variants() -> None:
    assert is_korean('Korean')
    assert is_korean('korean')
    assert is_korean('  Korean (Seoul)  ')


def test_is_korean_rejects_other_languages() -> None:
    assert not is_korean('Japanese')
    assert not is_korean('Chinese')
    assert not is_korean('English')
    assert not is_korean('')


def test_predicates_are_mutually_exclusive() -> None:
    for label in ('Japanese', 'Mandarin Chinese', 'Korean', 'English', 'Spanish'):
        matches = [is_chinese(label), is_japanese(label), is_korean(label)]
        assert sum(matches) <= 1, f'{label!r} matched multiple predicates: {matches}'
