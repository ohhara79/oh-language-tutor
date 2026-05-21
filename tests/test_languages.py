"""Tests for ``tutor.languages`` source-language predicates."""

from __future__ import annotations

from tutor.languages import (
    detect_language_mismatch,
    is_chinese,
    is_japanese,
    is_korean,
)


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


# -- detect_language_mismatch ------------------------------------------------


def test_mismatch_passes_when_text_matches_learning_language() -> None:
    # Korean text under Korean setting.
    assert detect_language_mismatch('Korean', '안녕하세요') is None
    # Japanese text under Japanese setting.
    assert detect_language_mismatch('Japanese', 'こんにちは') is None
    # Chinese text under Chinese setting.
    assert detect_language_mismatch('Mandarin Chinese', '你好') is None
    # English text under English setting.
    assert detect_language_mismatch('English', 'Hello world') is None
    # French text under French setting (both Latin-script, both bucket as
    # latin-or-other, so we accept).
    assert detect_language_mismatch('French', 'Bonjour le monde') is None


def test_mismatch_flags_cjk_under_non_cjk() -> None:
    msg = detect_language_mismatch('English', '안녕하세요')
    assert msg is not None
    assert 'Korean' in msg
    assert 'English' in msg
    msg = detect_language_mismatch('English', 'こんにちは')
    assert msg is not None
    assert 'Japanese' in msg


def test_mismatch_flags_non_cjk_under_cjk() -> None:
    msg = detect_language_mismatch('Japanese', 'Hello world')
    assert msg is not None
    assert 'Japanese' in msg


def test_mismatch_flags_cross_cjk_confusions() -> None:
    # Japanese kana under Korean setting.
    assert detect_language_mismatch('Korean', 'こんにちは') is not None
    # Hangul under Japanese setting.
    assert detect_language_mismatch('Japanese', '안녕하세요') is not None
    # Hangul under Chinese setting.
    assert detect_language_mismatch('Chinese', '안녕하세요') is not None
    # Japanese kana under Chinese setting.
    assert detect_language_mismatch('Chinese', 'こんにちは') is not None


def test_mismatch_accepts_kanji_only_for_japanese_and_chinese() -> None:
    # Han-only line is indistinguishable from Chinese by script alone, so we
    # accept it for both Japanese and Chinese Learning Languages.
    assert detect_language_mismatch('Japanese', '学校') is None
    assert detect_language_mismatch('Mandarin Chinese', '学校') is None


def test_mismatch_skips_when_text_has_no_letters() -> None:
    # Pure punctuation/whitespace/digits gives no signal — don't false-positive.
    assert detect_language_mismatch('English', '   ') is None
    assert detect_language_mismatch('English', '...') is None
    assert detect_language_mismatch('Korean', '12345') is None
    assert detect_language_mismatch('Japanese', '!?@#') is None


def test_mismatch_japanese_mixed_with_latin_still_passes() -> None:
    # Japanese sentences often contain embedded English words; kana presence
    # is enough to bucket as 'japanese'.
    assert detect_language_mismatch('Japanese', 'これは Tokyo Tower です') is None


def test_mismatch_message_quotes_user_supplied_language() -> None:
    msg = detect_language_mismatch('English', '안녕')
    assert msg is not None
    assert "'English'" in msg
