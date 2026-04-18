"""Tests for ``tutor.types`` helpers."""

from __future__ import annotations

from tutor.types import format_created_at_utc


def test_format_created_at_utc_zero_offset() -> None:
    assert format_created_at_utc('2026-04-18T12:34:56+00:00') == '2026-04-18 12:34:56 UTC'


def test_format_created_at_utc_converts_non_utc_offset() -> None:
    # 21:34:56 KST (+09:00) → 12:34:56 UTC
    assert format_created_at_utc('2026-04-18T21:34:56+09:00') == '2026-04-18 12:34:56 UTC'


def test_format_created_at_utc_negative_offset() -> None:
    # 07:34:56 EST (-05:00) → 12:34:56 UTC
    assert format_created_at_utc('2026-04-18T07:34:56-05:00') == '2026-04-18 12:34:56 UTC'
