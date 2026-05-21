"""Tests for ``tutor.prompts``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tutor.prompts import (
    EXPLAIN_CONTEXT_K,
    MAX_SYSTEM_PROMPT_BYTES,
    PromptTooLargeError,
    _truncate_to_utf8_bytes,
    build_base_system_prompt,
    build_explain_user_message,
    build_system_prompt,
    build_thread_system_prompt,
    read_extras_system_prompt,
)
from tutor.types import LineRecord

if TYPE_CHECKING:
    from pathlib import Path


def test_build_base_system_prompt_contains_core_fields() -> None:
    prompt = build_base_system_prompt('English', 'Korean', 'intermediate')
    assert 'English' in prompt
    assert 'Korean' in prompt
    assert 'intermediate' in prompt


def test_build_base_system_prompt_mentions_chinese_variant() -> None:
    prompt = build_base_system_prompt('Mandarin Chinese', 'Korean', 'intermediate')
    assert 'Variant' in prompt
    # The pronunciation bullet must show both simplified and traditional
    # halves wrapped in per-character pinyin ruby.
    assert '<ruby>学<rt>xué</rt>习<rt>xí</rt></ruby>' in prompt
    assert '<ruby>學<rt>xué</rt>習<rt>xí</rt></ruby>' in prompt


def test_build_base_system_prompt_chinese_variant_is_mandatory() -> None:
    prompt = build_base_system_prompt('Chinese', 'Korean', 'intermediate')
    assert 'ALWAYS include when the source is Chinese' in prompt
    # Guard against silent reintroduction of the script-identical carve-out
    # that allowed the model to drop the Variant row on short lines.
    assert 'script-identical' not in prompt
    # Even when simplified and traditional come out byte-identical, the row
    # must still appear so the learner reads pinyin for the full sentence.
    assert 'character-for-character identical' in prompt
    assert 'raw 你好 → variant 你好' in prompt


def test_build_base_system_prompt_chinese_pinyin_ruby() -> None:
    prompt = build_base_system_prompt('Mandarin Chinese', 'Korean', 'intermediate')
    # Every Han-character span is wrapped in <ruby><rt> with per-character pinyin.
    assert '<ruby>' in prompt
    assert '<rt>' in prompt
    # The rule must apply beyond the Vocabulary row — Variant and quoted
    # Expression / Context phrases also get pinyin ruby.
    assert 'Vocabulary headwords' in prompt
    assert 'Variant rewrite' in prompt
    assert 'Expression or Context' in prompt
    # One Han character = one syllable; per-character ruby is the rule.
    assert 'one Han character = one syllable' in prompt
    # The 你好 example must use the per-character ruby form, not the old
    # parenthetical pinyin form.
    assert '<ruby>你<rt>nǐ</rt>好<rt>hǎo</rt></ruby>' in prompt


def test_build_base_system_prompt_chinese_variant_calls_for_ruby() -> None:
    prompt = build_base_system_prompt('Mandarin Chinese', 'Korean', 'intermediate')
    # The Variant row clause must direct the model to apply pinyin ruby to the
    # simplified ↔ traditional rewrite, not just copy bare characters.
    variant_idx = prompt.index('\U0001f501 Variant:')
    pronunciation_idx = prompt.index('Pronunciation notation:')
    variant_clause = prompt[variant_idx:pronunciation_idx]
    assert '<ruby>' in variant_clause
    assert 'pinyin' in variant_clause


def test_build_base_system_prompt_mentions_japanese_kyujitai() -> None:
    prompt = build_base_system_prompt('Japanese', 'Korean', 'intermediate')
    # The Variant row must call out the kyūjitai (旧字体) rewrite for Japanese.
    assert 'kyūjitai' in prompt
    assert '旧字体' in prompt
    # The pronunciation bullet must show the shinjitai/kyūjitai vocab format
    # using furigana ruby tags for both halves.
    assert '<ruby>学校<rt>がっこう</rt></ruby>' in prompt
    assert '<ruby>學校<rt>がっこう</rt></ruby>' in prompt


def test_build_base_system_prompt_japanese_variant_conditions() -> None:
    prompt = build_base_system_prompt('Japanese', 'Korean', 'intermediate')
    # The Japanese clause must be present on the Variant row.
    assert 'source is Japanese' in prompt
    # The "skip any empty section" override still applies to this row.
    assert 'does not apply to this row' in prompt
    # When no GROUND TRUTH block is supplied (kyūjitai is a no-op for this
    # line), the row must still fire and carry furigana — the previous
    # "omit the row" carve-out is gone.
    assert 'kyūjitai conversion is a no-op' in prompt
    assert 'copy the original target line verbatim' in prompt
    # Omission is now reserved for lines with no kanji at all.
    assert 'no kanji at all' in prompt


def test_build_base_system_prompt_japanese_furigana_ruby() -> None:
    prompt = build_base_system_prompt('Japanese', 'Korean', 'intermediate')
    # Every kanji-bearing Japanese form is wrapped in <ruby><rt> furigana.
    assert '<ruby>' in prompt
    assert '<rt>' in prompt
    # The rule must apply beyond the Vocabulary row — Variant and quoted
    # Expression / Context phrases also get furigana.
    assert 'Vocabulary headwords' in prompt
    assert 'Variant rewrite' in prompt
    assert 'Expression or Context' in prompt
    # Pure-kana / ASCII tokens are explicitly excluded so the model doesn't
    # try to wrap ありがとう or English glosses in <ruby>.
    assert 'unwrapped' in prompt


def test_build_base_system_prompt_variant_row_overrides_skip_empty() -> None:
    # The Variant row carries the per-line pronunciation ruby for Chinese
    # (pinyin) and Japanese (furigana), so the generic "skip any empty
    # section" rule in the rubric must not let the model drop it when the
    # rewrite ends up identical to the source line.
    prompt = build_base_system_prompt('Japanese', 'Korean', 'intermediate')
    variant_idx = prompt.index('\U0001f501 Variant:')
    pronunciation_idx = prompt.index('Pronunciation notation:')
    variant_clause = prompt[variant_idx:pronunciation_idx]
    assert 'does not apply to this row for any language' in variant_clause
    assert 'character-for-character identical to the source line' in variant_clause


def test_build_base_system_prompt_japanese_variant_calls_for_ruby() -> None:
    prompt = build_base_system_prompt('Japanese', 'Korean', 'intermediate')
    # The Variant row clause must direct the model to apply furigana to the
    # kyūjitai rewrite, not just copy bare kanji.
    variant_idx = prompt.index('\U0001f501 Variant:')
    pronunciation_idx = prompt.index('Pronunciation notation:')
    variant_clause = prompt[variant_idx:pronunciation_idx]
    assert '<ruby>' in variant_clause
    assert 'furigana' in variant_clause


def test_build_base_system_prompt_separates_sections_with_blank_lines() -> None:
    # Python-markdown collapses consecutive label lines into one <p> unless a
    # blank line separates them. Each non-leading section label must be
    # preceded by a blank line so it renders as its own paragraph.
    prompt = build_base_system_prompt('Chinese', 'Korean', 'intermediate')
    for label in (
        '\U0001f501 Variant:',
        '\U0001f4da Vocabulary:',
        '\U0001f4a1 Expression:',
        '\U0001f3ac Context:',
    ):
        idx = prompt.index(label)
        # Two newlines immediately precede the two spaces of indentation.
        assert prompt[idx - 4 : idx - 2] == '\n\n', f'section {label!r} is not preceded by a blank line'
    # The header still advertises the blank-line rule.
    assert 'blank line' in prompt
    # Existing invariants still hold.
    assert 'ALWAYS include when the source is Chinese' in prompt
    assert 'skip any empty section' in prompt
    assert 'under 100 words' in prompt


def test_build_base_system_prompt_includes_ipa_for_chinese() -> None:
    prompt = build_base_system_prompt('Mandarin Chinese', 'Korean', 'intermediate')
    # Chinese per-character pinyin ruby + IPA in brackets.
    assert '<ruby>学<rt>xué</rt>习<rt>xí</rt></ruby> / <ruby>學<rt>xué</rt>習<rt>xí</rt></ruby> [ɕɥěɕǐ]' in prompt
    assert 'not IPA' not in prompt
    assert 'omit the bracket' not in prompt


def test_build_base_system_prompt_includes_ipa_for_japanese() -> None:
    prompt = build_base_system_prompt('Japanese', 'Korean', 'intermediate')
    # Japanese furigana ruby + IPA in brackets.
    assert '<ruby>受け入れる<rt>うけいれる</rt></ruby> [ɯke̞iɾe̞ɾɯ]' in prompt  # noqa: RUF001


def test_build_base_system_prompt_includes_ipa_for_korean() -> None:
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    # Korean Sino-Korean dual-script item: romanization + IPA in parens.
    assert '(haksŭp, [haks͈ɯp])' in prompt  # noqa: RUF001


def test_build_base_system_prompt_includes_ipa_for_phonetic_source() -> None:
    prompt = build_base_system_prompt('Spanish', 'Korean', 'intermediate')
    # Phonetic-script catch-all carries IPA in brackets even when no CJK matched.
    assert '[ˈola]' in prompt  # noqa: RUF001 — IPA primary-stress mark


def test_build_base_system_prompt_mentions_korean_hanja_variant() -> None:
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    # The Variant row must call out the hanja (漢字) rewrite for Korean.
    assert 'hanja' in prompt
    assert '漢字' in prompt
    assert '漢字語' in prompt
    # The pronunciation bullet must show the Hangul/hanja dual-script vocab format.
    assert '학습 / 學習' in prompt


def test_build_base_system_prompt_korean_variant_omit_rule() -> None:
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    # The omission rule is now phrased in terms of confidence rather than
    # the presence of Sino-Korean words: omit only if no word can be
    # converted confidently.
    assert 'no word in the line can be converted with confidence' in prompt
    # Native Korean parts must be called out as staying in Hangul.
    assert '고유어' in prompt
    # The "skip any empty section" override still applies to this row.
    assert 'does not apply to this row' in prompt


def test_build_base_system_prompt_korean_dual_script_vocab_format() -> None:
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    # Sino-Korean vocab format: 한글 / 漢字 (romanization, [IPA]) → translation.
    assert '학습 / 學習 (haksŭp, [haks͈ɯp])' in prompt  # noqa: RUF001
    # Native Korean vocab format: drops the slash, keeps IPA in brackets.
    assert '아름답다 [a̠ɾɯmda̠p̚t͈a̠]' in prompt  # noqa: RUF001


def test_build_base_system_prompt_korean_variant_confidence_rule() -> None:
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    # The confidence gate must be unambiguous.
    assert 'Convert a word ONLY when you are confident' in prompt
    # Each of the four documented failure modes must appear explicitly.
    # (a) proper nouns without pinned context
    assert 'proper noun' in prompt
    # (b) ambiguous homophones — both example pairs are spelled out.
    assert '사기 = 詐欺 / 士氣 / 史記' in prompt
    assert '수도 = 首都 / 水道 / 修道' in prompt
    # (b) also makes the context-override explicit, with positive examples
    # so the model isn't overly conservative on context-disambiguated lines.
    assert 'context CLEARLY selects one sense' in prompt
    assert '사기를 쳤다 → 詐欺를 쳤다' in prompt
    assert '대한민국의 수도 → 대한민국의 首都' in prompt
    assert 'go ahead and convert' in prompt
    # (c) native-vs-Sino-Korean uncertainty.
    assert 'Sino-Korean or native Korean' in prompt
    # (d) rare / literary hanja.
    assert 'rare or literary' in prompt


def test_build_base_system_prompt_korean_partial_conversion_allowed() -> None:
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    # Partial conversion (mixed Hangul / hanja) must be explicitly endorsed.
    assert 'mixed Hangul / hanja' in prompt
    assert 'PREFERRED' in prompt
    # The omit-row threshold is the strict one: nothing can be converted.
    assert 'Omit the entire row only when no word in the line can be converted' in prompt


def test_build_base_system_prompt_korean_variant_calls_for_ruby() -> None:
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    # The Variant row clause must direct the model to apply per-character ruby
    # to the Korean rewrite under one unified orientation: Hanja as base,
    # Hangul as <rt>, regardless of input script.
    variant_idx = prompt.index('\U0001f501 Variant:')
    pronunciation_idx = prompt.index('Pronunciation notation:')
    variant_clause = prompt[variant_idx:pronunciation_idx]
    assert '<ruby>' in variant_clause
    assert '<rt>' in variant_clause
    # Per-character / one-hanja-equals-one-syllable alignment must be spelled out.
    assert 'one hanja = one Hangul syllable' in variant_clause
    # The fixed orientation must be stated positively and as a prohibition.
    assert 'Hanja as base' in variant_clause
    assert 'Hangul ruby' in variant_clause
    assert 'NEVER put Hangul as the base or hanja inside <rt>' in variant_clause
    # Particles, endings, native Korean, and kept-as-input spans must be
    # explicitly excluded from ruby wrapping.
    assert 'NEVER wrap' in variant_clause
    assert '고유어' in variant_clause


def test_build_base_system_prompt_korean_variant_ruby_worked_examples() -> None:
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    # Both worked examples end up Hanja-base/Hangul-ruby. The Hangul-input
    # example shows the line gaining hanja; the Hanja-input example shows
    # the hanja kept verbatim with the Hangul reading supplied as <rt>.
    assert ('input 공부합니다 → variant <ruby>工<rt>공</rt>夫<rt>부</rt></ruby>합니다') in prompt
    assert ('input 工夫합니다 → variant <ruby>工<rt>공</rt>夫<rt>부</rt></ruby>합니다') in prompt


def test_build_base_system_prompt_korean_variant_forbids_half_converted_word() -> None:
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    # The new rules live inside the Variant clause, not the pronunciation bullet.
    variant_idx = prompt.index('\U0001f501 Variant:')
    pronunciation_idx = prompt.index('Pronunciation notation:')
    variant_clause = prompt[variant_idx:pronunciation_idx]
    # Structural invariant: Hanja count == <rt> count, alternate one-to-one,
    # no consecutive <rt>s, no <rt> without a Hanja base before it.
    assert 'alternate one-to-one' in variant_clause
    assert 'Hanja count MUST equal the <rt> count' in variant_clause
    assert 'NEVER emit two consecutive <rt>s' in variant_clause
    # Per-word atomicity: convert the whole Sino-Korean word or none of it.
    assert 'converted atomically' in variant_clause
    assert 'every syllable of the word' in variant_clause
    assert 'NEVER convert only some syllables of a multi-syllable Sino-Korean word' in variant_clause
    # Both negative worked examples must appear verbatim so the model has
    # explicit counter-templates for the two reported failure shapes.
    assert 'NEVER <ruby>地<rt>지</rt></ruby>갑' in variant_clause
    assert 'NEVER <ruby>帽<rt>모</rt><rt>자</rt></ruby>' in variant_clause


def test_build_base_system_prompt_korean_uncertain_vocab_drops_slash() -> None:
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    # The pronunciation bullet must document the Hangul-only fallback for
    # Sino-Korean items whose hanja the model isn't sure about.
    assert '사기 [sʌːɡi]' in prompt  # noqa: RUF001
    # The bullet must say uncertain Sino-Korean words drop the slash form.
    assert 'Sino-Korean but the specific hanja is uncertain' in prompt


def test_build_base_system_prompt_forbids_duplicate_dual_script() -> None:
    # A global backstop rule must forbid emitting `X / X` (identical halves)
    # for any of the three CJK dual-script vocab formats.
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    assert 'NEVER emit two halves that are character-for-character identical' in prompt
    # All three dual-script pairings must be named so a future refactor
    # doesn't silently drop one of them from the rule.
    assert '新字体 / 旧字体' in prompt
    assert 'simplified / traditional' in prompt
    assert 'Hangul / 漢字' in prompt
    # The action is explicit: drop the slash and the duplicate.
    assert 'drop the slash and the duplicate' in prompt


def test_build_base_system_prompt_english_source_omits_variant_row() -> None:
    # When the source language isn't CJK, there is no script variant to write —
    # the Variant row label must not appear in the rubric.
    prompt = build_base_system_prompt('English', 'Korean', 'intermediate')
    assert '\U0001f501 Variant:' not in prompt


def test_build_base_system_prompt_english_source_omits_cjk_content() -> None:
    prompt = build_base_system_prompt('English', 'Korean', 'intermediate')
    # None of the CJK-specific ruby / dual-script vocabulary instructions
    # should leak into the prompt for a non-CJK source.
    for needle in ('kyūjitai', 'furigana', 'pinyin', 'hanja', '고유어', '漢字'):
        assert needle not in prompt, f'unexpected CJK content {needle!r} for English source'
    # And the universal dual-script backstop drops out too — it has no targets.
    assert 'NEVER emit two halves' not in prompt


def test_build_base_system_prompt_english_source_keeps_phonetic_catchall() -> None:
    prompt = build_base_system_prompt('English', 'Korean', 'intermediate')
    # The phonetic-script catch-all bullet still ships, so IPA stays available.
    assert '[ˈola]' in prompt  # noqa: RUF001 — IPA primary-stress mark
    assert 'hola' in prompt


def test_build_base_system_prompt_chinese_omits_japanese_and_korean_clauses() -> None:
    prompt = build_base_system_prompt('Chinese', 'English', 'intermediate')
    # Per-language Variant clauses for other languages must not appear.
    assert 'For Japanese:' not in prompt
    assert 'For Korean:' not in prompt
    # Japanese / Korean pronunciation bullets must not appear either.
    assert '- For Japanese,' not in prompt
    assert '- For Korean,' not in prompt
    # The backstop bullet still mentions all three pairings when it's included,
    # but the Korean-only 고유어 mention does not leak from the Korean bullet.
    assert '고유어' not in prompt


def test_build_base_system_prompt_japanese_omits_chinese_and_korean_clauses() -> None:
    prompt = build_base_system_prompt('Japanese', 'English', 'intermediate')
    assert 'For Chinese:' not in prompt
    assert 'For Korean:' not in prompt
    assert '- For Mandarin Chinese,' not in prompt
    assert '- For Korean,' not in prompt
    assert '고유어' not in prompt


def test_build_base_system_prompt_korean_omits_chinese_and_japanese_clauses() -> None:
    prompt = build_base_system_prompt('Korean', 'English', 'intermediate')
    assert 'For Chinese:' not in prompt
    assert 'For Japanese:' not in prompt
    assert '- For Mandarin Chinese,' not in prompt
    assert '- For Japanese,' not in prompt
    # Japanese-only furigana ruby example must not leak.
    assert '<ruby>受け入れる<rt>うけいれる</rt></ruby>' not in prompt


def test_build_base_system_prompt_substring_match_mandarin_chinese() -> None:
    # The free-text "Mandarin Chinese" input must still route to the Chinese
    # clauses through the substring matcher.
    prompt = build_base_system_prompt('Mandarin Chinese', 'English', 'intermediate')
    assert 'For Chinese:' in prompt
    assert '<ruby>你<rt>nǐ</rt>好<rt>hǎo</rt></ruby>' in prompt


def test_build_system_prompt_without_extra_equals_base() -> None:
    assert build_system_prompt('English', 'Korean', 'intermediate') == build_base_system_prompt(
        'English',
        'Korean',
        'intermediate',
    )


def test_build_system_prompt_appends_extra_text() -> None:
    extra_text = 'Domain-specific stuff about a video game.'
    prompt = build_system_prompt('English', 'Korean', 'intermediate', extras_text=extra_text)

    marker = 'ADDITIONAL SOURCE-SPECIFIC CONTEXT:'
    assert marker in prompt
    assert prompt.index(marker) < prompt.index(extra_text)


def test_build_system_prompt_appends_kyujitai_ground_truth() -> None:
    prompt = build_system_prompt(
        'Japanese',
        'Korean',
        'intermediate',
        kyujitai_variant='[辨|瓣|辯|辮]護士',
    )
    assert 'GROUND TRUTH FOR THE TARGET LINE:' in prompt
    assert '[辨|瓣|辯|辮]護士' in prompt
    # The block must teach the bracket-resolution rule.
    assert 'pick exactly one form' in prompt


def test_build_system_prompt_omits_ground_truth_when_unset() -> None:
    prompt = build_system_prompt('Japanese', 'Korean', 'intermediate')
    assert 'GROUND TRUTH FOR THE TARGET LINE:' not in prompt


def test_build_system_prompt_appends_kyujitai_mappings_bullet() -> None:
    prompt = build_system_prompt(
        'Japanese',
        'Korean',
        'intermediate',
        kyujitai_mappings={'学': ['學'], '弁': ['辨', '瓣', '辯', '辮']},
    )
    assert 'GROUND TRUTH FOR THE TARGET LINE:' in prompt
    assert 'Per-kanji kyūjitai mappings' in prompt
    # Single-candidate entry renders as plain arrow.
    assert '学 → 學' in prompt
    # Multi-candidate entry renders alternatives + the "pick by meaning" hint.
    assert '弁 → 辨 / 瓣 / 辯 / 辮' in prompt
    assert 'pick by meaning' in prompt


def test_build_system_prompt_omits_mappings_bullet_when_empty() -> None:
    prompt_none = build_system_prompt('Japanese', 'Korean', 'intermediate')
    prompt_empty = build_system_prompt(
        'Japanese',
        'Korean',
        'intermediate',
        kyujitai_mappings={},
    )
    for prompt in (prompt_none, prompt_empty):
        assert 'Per-kanji kyūjitai mappings' not in prompt


def test_build_system_prompt_combines_variant_and_mappings() -> None:
    prompt = build_system_prompt(
        'Japanese',
        'Korean',
        'intermediate',
        kyujitai_variant='[辨|瓣|辯|辮]護士',
        kyujitai_mappings={'弁': ['辨', '瓣', '辯', '辮']},
    )
    # Both bullets live under a single GROUND TRUTH header.
    assert prompt.count('GROUND TRUTH FOR THE TARGET LINE:') == 1
    assert '[辨|瓣|辯|辮]護士' in prompt
    assert 'Per-kanji kyūjitai mappings' in prompt


def test_build_base_system_prompt_japanese_vocab_rule_references_ground_truth() -> None:
    prompt = build_base_system_prompt('Japanese', 'Korean', 'intermediate')
    # The Japanese pronunciation bullet must direct the model to use the
    # GROUND TRUTH mappings as the source of truth for kyūjitai forms.
    assert 'GROUND TRUTH mappings' in prompt


def test_build_base_system_prompt_japanese_variant_references_ground_truth() -> None:
    prompt = build_base_system_prompt('Japanese', 'Korean', 'intermediate')
    # The Variant row must point the model at the GROUND TRUTH block and
    # teach the bracket convention.
    assert 'GROUND TRUTH block' in prompt
    assert '[A|B|C]' in prompt


def test_build_system_prompt_oversized_extras_raises() -> None:
    huge = 'A' * (MAX_SYSTEM_PROMPT_BYTES + 1)
    with pytest.raises(PromptTooLargeError) as excinfo:
        build_system_prompt('English', 'Korean', 'intermediate', extras_text=huge)
    assert 'execve per-arg cap' in str(excinfo.value)


def test_read_extras_system_prompt_returns_file_contents(tmp_path: Path) -> None:
    extra = tmp_path / 'extra.md'
    extra.write_text('hello extras', encoding='utf-8')
    assert read_extras_system_prompt(str(extra)) == 'hello extras'


def test_read_extras_system_prompt_missing_raises(tmp_path: Path) -> None:
    missing = tmp_path / 'nope.md'
    with pytest.raises(SystemExit) as excinfo:
        read_extras_system_prompt(str(missing))
    assert str(excinfo.value).startswith('oh-language-tutor: cannot read')


def test_explain_context_k_is_positive() -> None:
    assert EXPLAIN_CONTEXT_K > 0


def test_build_explain_user_message_no_context() -> None:
    msg = build_explain_user_message('target line', [])
    assert 'target line' in msg
    assert 'Explain this line:' in msg
    assert 'Recent context' not in msg


def test_build_explain_user_message_with_context_preserves_order() -> None:
    msg = build_explain_user_message('the target', ['first', 'second', 'third'])
    assert 'Recent context' in msg
    idx_first = msg.index('first')
    idx_second = msg.index('second')
    idx_third = msg.index('third')
    idx_target = msg.index('the target')
    assert idx_first < idx_second < idx_third < idx_target


def test_truncate_to_utf8_bytes_short_passthrough() -> None:
    assert _truncate_to_utf8_bytes('hello', 100) == 'hello'


def test_truncate_to_utf8_bytes_ascii_truncates_with_ellipsis() -> None:
    result = _truncate_to_utf8_bytes('A' * 1000, 50)
    assert result.endswith('…')
    assert result.startswith('A' * 50)


def test_truncate_to_utf8_bytes_multibyte_boundary_safe() -> None:
    # Each '가' is 3 bytes in UTF-8; cutting at an arbitrary byte limit would
    # land mid-codepoint. _truncate_to_utf8_bytes must produce valid UTF-8.
    src = '가' * 100
    result = _truncate_to_utf8_bytes(src, 50)
    # Must decode cleanly — an invalid boundary would have raised by now.
    assert result.endswith('…')
    assert len(result.encode('utf-8')) <= 50 + len('…'.encode())


def test_build_thread_system_prompt_renders_context_in_order() -> None:
    anchor = LineRecord(idx=3, raw='ANCHOR LINE', explanation='anchor explanation')
    ctx = [
        LineRecord(idx=0, raw='line-zero', explanation=None),
        LineRecord(idx=1, raw='line-one', explanation='explained-one'),
        LineRecord(idx=2, raw='line-two', explanation=None),
    ]
    prompt = build_thread_system_prompt('English', 'Korean', 'intermediate', anchor, ctx)
    # Each raw appears and in ascending order.
    positions = [prompt.index(lr.raw) for lr in ctx]
    assert positions == sorted(positions)
    assert 'explained-one' in prompt
    assert 'ANCHOR LINE' in prompt
    assert 'anchor explanation' in prompt


def test_build_thread_system_prompt_drops_oldest_when_oversized() -> None:
    anchor = LineRecord(idx=0, raw='anchor', explanation='short')
    # Build enough context to blow past the cap.  Each line is a few KB.
    chunk = 'X' * 4096
    ctx = [LineRecord(idx=i, raw=f'ctx-{i}-{chunk}', explanation=None) for i in range(64)]
    prompt = build_thread_system_prompt('English', 'Korean', 'intermediate', anchor, ctx)
    assert len(prompt.encode('utf-8')) <= MAX_SYSTEM_PROMPT_BYTES
    # The newest context line is most relevant and should survive trimming.
    assert f'ctx-63-{chunk}' in prompt
    # The oldest should have been dropped.
    assert 'ctx-0-' not in prompt


def test_build_thread_system_prompt_anchor_only_fallback_truncates() -> None:
    giant_explanation = 'Y' * (MAX_SYSTEM_PROMPT_BYTES * 2)
    anchor = LineRecord(idx=0, raw='anchor', explanation=giant_explanation)
    prompt = build_thread_system_prompt('English', 'Korean', 'intermediate', anchor, [])
    assert len(prompt.encode('utf-8')) <= MAX_SYSTEM_PROMPT_BYTES
    assert 'anchor' in prompt


def test_build_thread_system_prompt_anchor_without_explanation() -> None:
    anchor = LineRecord(idx=0, raw='ANCHOR RAW', explanation=None)
    prompt = build_thread_system_prompt('English', 'Korean', 'intermediate', anchor, [])
    assert '>>> ANCHOR RAW' in prompt
    # No "[explanation:" trail follows the anchor when explanation is None.
    anchor_pos = prompt.index('>>> ANCHOR RAW')
    tail = prompt[anchor_pos : anchor_pos + 200]
    assert '[explanation:' not in tail
