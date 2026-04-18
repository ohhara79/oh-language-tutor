"""Tests for ``tutor.replay``."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any, cast

import pytest
from claude_agent_sdk import ClaudeAgentOptions

from tests.conftest import FakeClaudeSDKClient, make_assistant, make_result
from tutor import replay
from tutor.replay import (
    build_preamble,
    connect_with_fallback,
    notify_fallback,
    pairs_from_thread,
)
from tutor.types import ThreadMessage, TutorEntry

if TYPE_CHECKING:
    from tests.conftest import FakeClaudeSDKClientFactory


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
    def on_explanation(self, raw: str, text: str) -> None: ...
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


# -- connect_with_fallback ---------------------------------------------------


def _opts(resume: str | None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(system_prompt='sys', model='m', allowed_tools=[], resume=resume)


async def test_connect_with_fallback_primary_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    fake_client_factory: FakeClaudeSDKClientFactory,
):
    fake_client_factory.push(FakeClaudeSDKClient())
    monkeypatch.setattr(replay, 'ClaudeSDKClient', fake_client_factory)

    log = io.StringIO()
    sink = _RecordingSink()
    client = await connect_with_fallback(
        _opts(resume='sid'),
        fresh=_opts(resume=None),
        tutor_entries=[],
        sink=sink,
        log=log,
    )
    assert len(fake_client_factory.constructed) == 1
    assert cast('FakeClaudeSDKClient', client).entered is True
    assert sink.errors == []


async def test_connect_with_fallback_no_resume_raises_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    fake_client_factory: FakeClaudeSDKClientFactory,
):
    fake_client_factory.push(FakeClaudeSDKClient(raise_on_enter=RuntimeError('boom')))
    monkeypatch.setattr(replay, 'ClaudeSDKClient', fake_client_factory)

    log = io.StringIO()
    sink = _RecordingSink()
    with pytest.raises(RuntimeError, match='boom'):
        await connect_with_fallback(
            _opts(resume=None),
            fresh=_opts(resume=None),
            tutor_entries=[TutorEntry(raw='r', explanation='e', id='x')],
            sink=sink,
            log=log,
        )
    assert sink.errors == []


async def test_connect_with_fallback_resume_fallback_replays(
    monkeypatch: pytest.MonkeyPatch,
    fake_client_factory: FakeClaudeSDKClientFactory,
):
    # First client: fails to enter (simulating resume failure).
    fake_client_factory.push(FakeClaudeSDKClient(raise_on_enter=RuntimeError('resume gone')))
    # Second client: fresh, succeeds; seed a response so the preamble's
    # receive_response loop terminates.
    fresh = FakeClaudeSDKClient([[make_assistant('ack'), make_result('new-sid')]])
    fake_client_factory.push(fresh)
    monkeypatch.setattr(replay, 'ClaudeSDKClient', fake_client_factory)

    log = io.StringIO()
    sink = _RecordingSink()
    entries = [
        TutorEntry(raw='r1', explanation='e1', id='x1'),
        TutorEntry(raw='r2', explanation='e2', id='x2'),
    ]
    client = await connect_with_fallback(
        _opts(resume='sid'),
        fresh=_opts(resume=None),
        tutor_entries=entries,
        sink=sink,
        log=log,
    )
    assert client is fresh
    assert fresh.entered is True
    assert len(fresh.queries) == 1
    preamble = fresh.queries[0]
    assert 'User: r2' in preamble
    assert 'Assistant: e2' in preamble
    assert 'resume failed; replayed 2/2' in sink.errors[0]
    assert '=== resume failed;' in log.getvalue()


async def test_connect_with_fallback_empty_entries_skips_preamble(
    monkeypatch: pytest.MonkeyPatch,
    fake_client_factory: FakeClaudeSDKClientFactory,
):
    fake_client_factory.push(FakeClaudeSDKClient(raise_on_enter=RuntimeError('resume gone')))
    fresh = FakeClaudeSDKClient()
    fake_client_factory.push(fresh)
    monkeypatch.setattr(replay, 'ClaudeSDKClient', fake_client_factory)

    log = io.StringIO()
    sink = _RecordingSink()
    client = await connect_with_fallback(
        _opts(resume='sid'),
        fresh=_opts(resume=None),
        tutor_entries=[],
        sink=sink,
        log=log,
    )
    assert client is fresh
    assert fresh.queries == []
    assert 'replayed 0/0' in sink.errors[0]
