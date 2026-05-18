"""Tests for ``tutor.japanese`` — shinjitai ↔ kyūjitai conversion."""

from __future__ import annotations

from tutor.japanese import _TABLE, is_japanese, to_kyujitai_template


def test_table_excludes_meta_keys() -> None:
    assert all(not k.startswith('_') for k in _TABLE)
    assert _TABLE


def test_table_keys_are_single_characters() -> None:
    assert all(len(k) == 1 for k in _TABLE)


def test_table_values_are_non_empty_lists() -> None:
    assert all(isinstance(v, list) and v for v in _TABLE.values())


def test_to_kyujitai_unambiguous_substitution() -> None:
    assert to_kyujitai_template('学校') == '學校'


def test_to_kyujitai_long_tail_kanji() -> None:
    # The Tōyō simplifications the model is least reliable about.
    assert to_kyujitai_template('渋い') == '澁い'
    assert to_kyujitai_template('缶') == '罐'
    assert to_kyujitai_template('芸術') == '藝術'
    assert to_kyujitai_template('観光') == '觀光'


def test_to_kyujitai_ambiguous_emits_brackets() -> None:
    # 弁 maps to 4 different kyūjitai by meaning.
    assert to_kyujitai_template('弁護士') == '[辨|瓣|辯|辮]護士'
    assert to_kyujitai_template('花弁') == '花[辨|瓣|辯|辮]'


def test_to_kyujitai_preserves_unmapped_characters() -> None:
    # Kana and non-shinjitai kanji pass through verbatim.
    assert to_kyujitai_template('学校に行きます') == '學校に行きます'


def test_to_kyujitai_returns_none_when_nothing_converts() -> None:
    assert to_kyujitai_template('こんにちは') is None
    assert to_kyujitai_template('カタカナ') is None
    # Pure kanji line whose characters have no kyūjitai variant.
    assert to_kyujitai_template('人山川') is None


def test_to_kyujitai_empty_string() -> None:
    assert to_kyujitai_template('') is None


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
    assert not is_japanese('')
