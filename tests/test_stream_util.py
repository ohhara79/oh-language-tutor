"""Tests for tutor.stream_util.text_delta."""

from __future__ import annotations

from claude_agent_sdk import StreamEvent

from tutor.stream_util import text_delta


def _event(raw: dict[str, object]) -> StreamEvent:
    return StreamEvent(uuid='u', session_id='s', event=raw)


def test_text_delta_extracts_text_from_content_block_delta():
    e = _event(
        {
            'type': 'content_block_delta',
            'index': 0,
            'delta': {'type': 'text_delta', 'text': 'hello'},
        }
    )
    assert text_delta(e) == 'hello'


def test_text_delta_returns_none_for_non_content_block_delta():
    e = _event({'type': 'message_start'})
    assert text_delta(e) is None


def test_text_delta_returns_none_for_non_text_delta_kind():
    e = _event(
        {
            'type': 'content_block_delta',
            'delta': {'type': 'input_json_delta', 'partial_json': '{}'},
        }
    )
    assert text_delta(e) is None


def test_text_delta_returns_none_for_missing_delta():
    e = _event({'type': 'content_block_delta'})
    assert text_delta(e) is None


def test_text_delta_returns_none_for_non_string_text():
    e = _event(
        {
            'type': 'content_block_delta',
            'delta': {'type': 'text_delta', 'text': 42},
        }
    )
    assert text_delta(e) is None
