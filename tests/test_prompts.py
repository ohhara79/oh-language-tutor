"""Tests for ``tutor.prompts``."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest

from tutor.prompts import (
    MAX_SYSTEM_PROMPT_BYTES,
    _truncate_to_utf8_bytes,
    build_base_system_prompt,
    build_system_prompt,
    build_thread_system_prompt,
)
from tutor.types import LineRecord

if TYPE_CHECKING:
    from pathlib import Path


def _base_ns(
    *,
    extra_system_prompt: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        source_language='English',
        target_language='Korean',
        level='intermediate',
        skip_token='SKIP',  # noqa: S106
        extra_system_prompt=extra_system_prompt,
    )


def test_build_base_system_prompt_contains_core_fields() -> None:
    prompt = build_base_system_prompt('English', 'Korean', 'intermediate', 'SKIP')
    assert 'English' in prompt
    assert 'Korean' in prompt
    assert 'intermediate' in prompt
    assert 'SKIP' in prompt


def test_build_system_prompt_without_extra_equals_base() -> None:
    args = _base_ns()
    assert build_system_prompt(args) == build_base_system_prompt('English', 'Korean', 'intermediate', 'SKIP')


def test_build_system_prompt_appends_extra_file(tmp_path: Path) -> None:
    extra = tmp_path / 'extra.md'
    extra_text = 'Domain-specific stuff about a video game.'
    extra.write_text(extra_text, encoding='utf-8')

    prompt = build_system_prompt(_base_ns(extra_system_prompt=str(extra)))

    marker = 'ADDITIONAL SOURCE-SPECIFIC CONTEXT:'
    assert marker in prompt
    assert prompt.index(marker) < prompt.index(extra_text)


def test_build_system_prompt_missing_extra_raises(tmp_path: Path) -> None:
    missing = tmp_path / 'nope.md'
    with pytest.raises(SystemExit) as excinfo:
        build_system_prompt(_base_ns(extra_system_prompt=str(missing)))
    assert str(excinfo.value).startswith('oh-language-tutor: cannot read')


def test_build_system_prompt_oversized_extra_raises(tmp_path: Path) -> None:
    extra = tmp_path / 'huge.md'
    extra.write_text('A' * (MAX_SYSTEM_PROMPT_BYTES + 1), encoding='utf-8')
    with pytest.raises(SystemExit) as excinfo:
        build_system_prompt(_base_ns(extra_system_prompt=str(extra)))
    assert 'execve per-arg cap' in str(excinfo.value)


def test_truncate_to_utf8_bytes_short_passthrough() -> None:
    assert _truncate_to_utf8_bytes('hello', 100) == 'hello'


def test_truncate_to_utf8_bytes_ascii_truncates_with_ellipsis() -> None:
    result = _truncate_to_utf8_bytes('A' * 1000, 50)
    assert result.endswith('\u2026')
    assert result.startswith('A' * 50)


def test_truncate_to_utf8_bytes_multibyte_boundary_safe() -> None:
    # Each '가' is 3 bytes in UTF-8; cutting at an arbitrary byte limit would
    # land mid-codepoint. _truncate_to_utf8_bytes must produce valid UTF-8.
    src = '가' * 100
    result = _truncate_to_utf8_bytes(src, 50)
    # Must decode cleanly — an invalid boundary would have raised by now.
    assert result.endswith('\u2026')
    assert len(result.encode('utf-8')) <= 50 + len('\u2026'.encode())


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
