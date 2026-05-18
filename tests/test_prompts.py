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
    assert '学习 / 學習' in prompt


def test_build_base_system_prompt_includes_ipa_for_every_language() -> None:
    prompt = build_base_system_prompt('Mandarin Chinese', 'Korean', 'intermediate')
    # Chinese pinyin + IPA, both inside the same parens.
    assert '(xuéxí, [ɕɥěɕǐ])' in prompt
    # Japanese hiragana + IPA.
    assert '(うけいれる, [ɯke̞iɾe̞ɾɯ])' in prompt  # noqa: RUF001
    # Phonetic-script source languages now also carry IPA.
    assert '[annjʌŋɦasejo]' in prompt
    # Guard against silent reintroduction of the old "not IPA" carve-outs.
    assert 'not IPA' not in prompt
    assert 'omit the bracket' not in prompt


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
