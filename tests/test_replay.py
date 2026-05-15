"""Tests for ``tutor.replay``."""

from __future__ import annotations

import io
from typing import Any

from tutor.replay import build_preamble, notify_fallback, pairs_from_thread
from tutor.types import ThreadMessage, TutorEntry

# -- build_preamble ----------------------------------------------------------


def test_build_preamble_empty_list_returns_empty_string():
    assert build_preamble([]) == ''


def test_build_preamble_formats_single_pair():
    result = build_preamble([('hello', 'world')])
    assert 'User: hello' in result
    assert 'Assistant: world' in result
    assert result.endswith('(continue from here)')
    assert result.startswith('Here is our prior conversation.')


def test_build_preamble_formats_multiple_pairs_in_order():
    pairs = [('q1', 'a1'), ('q2', 'a2')]
    result = build_preamble(pairs)
    idx_q1 = result.index('User: q1')
    idx_a1 = result.index('Assistant: a1')
    idx_q2 = result.index('User: q2')
    idx_a2 = result.index('Assistant: a2')
    assert idx_q1 < idx_a1 < idx_q2 < idx_a2


# -- pairs_from_thread -------------------------------------------------------


def test_pairs_from_thread_empty_returns_empty():
    assert pairs_from_thread([]) == []


def test_pairs_from_thread_alternating_messages():
    msgs = [
        ThreadMessage(role='user', text='u1'),
        ThreadMessage(role='assistant', text='a1'),
        ThreadMessage(role='user', text='u2'),
        ThreadMessage(role='assistant', text='a2'),
    ]
    assert pairs_from_thread(msgs) == [('u1', 'a1'), ('u2', 'a2')]


def test_pairs_from_thread_drops_trailing_user():
    msgs = [
        ThreadMessage(role='user', text='u1'),
        ThreadMessage(role='assistant', text='a1'),
        ThreadMessage(role='user', text='u-unreplied'),
    ]
    assert pairs_from_thread(msgs) == [('u1', 'a1')]


def test_pairs_from_thread_drops_leading_assistant():
    msgs = [
        ThreadMessage(role='assistant', text='orphan'),
        ThreadMessage(role='user', text='u'),
        ThreadMessage(role='assistant', text='a'),
    ]
    assert pairs_from_thread(msgs) == [('u', 'a')]


# -- notify_fallback ---------------------------------------------------------


class _RecordingSink:
    def __init__(self):
        self.errors: list[str] = []

    def on_raw_line(self, raw: str) -> None: ...
    def on_entry_appended(self, entry: TutorEntry) -> None: ...
    def on_entry_explained(self, entry: TutorEntry) -> None: ...
    def on_thread_chunk(self, thread_id: str, chunk: str) -> None: ...
    def on_thread_done(self, thread_id: str, last_assistant: str) -> None: ...
    def on_thread_list(self, threads: list[Any]) -> None: ...
    def on_tutor_entry_removed(self, anchor_id: str) -> None: ...
    def on_error(self, msg: str) -> None:
        self.errors.append(msg)


def test_notify_fallback_writes_log_and_sink():
    log = io.StringIO()
    sink = _RecordingSink()
    notify_fallback(log, sink, total=10, replayed=5)
    assert log.getvalue() == '=== resume failed; replayed 5/10 turns into a new session ===\n'
    assert sink.errors == ['resume failed; replayed 5/10 turns into a new session']
