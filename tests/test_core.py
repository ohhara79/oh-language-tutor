"""Tests for ``tutor.core``."""

from __future__ import annotations

import asyncio
import io
import re
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import FakeClaudeSDKClient, make_assistant, make_assistant_multi, make_result
from tutor import core
from tutor.core import _stdin_line_stream, stdin_loop


class _RecordingSink:
    def __init__(self):
        self.raws: list[str] = []
        self.explanations: list[tuple[str, str]] = []
        self.errors: list[str] = []

    def on_raw_line(self, raw: str) -> None:
        self.raws.append(raw)

    def on_explanation(self, raw: str, text: str) -> None:
        self.explanations.append((raw, text))

    def on_thread_chunk(self, thread_id: str, chunk: str) -> None: ...
    def on_thread_done(self, thread_id: str, last_assistant: str) -> None: ...
    def on_thread_list(self, threads: list[Any]) -> None: ...
    def on_tutor_entry_removed(self, anchor_id: str) -> None: ...

    def on_error(self, msg: str) -> None:
        self.errors.append(msg)


# -- _stdin_line_stream ------------------------------------------------------


async def test_stdin_line_stream_yields_stripped_lines():
    src = io.StringIO('alpha\nbeta\n')
    out: list[str] = []
    async for line in _stdin_line_stream(use_thread=True, input_file=src):
        out.append(line)
    assert out == ['alpha', 'beta']


async def test_stdin_line_stream_stops_at_eof():
    src = io.StringIO('')
    out: list[str] = []
    async for line in _stdin_line_stream(use_thread=True, input_file=src):
        out.append(line)
    assert out == []


# -- stdin_loop --------------------------------------------------------------


def _session_path(tmp_path: Path) -> Path:
    return tmp_path / 'session.id'


async def test_stdin_loop_happy_path(tmp_path: Path):
    src = io.StringIO('hello\n')
    client = FakeClaudeSDKClient([[make_assistant_multi('one ', 'two'), make_result('sid-1')]])
    sink = _RecordingSink()
    stop = asyncio.Event()

    await stdin_loop(
        client,  # pyright: ignore[reportArgumentType]
        sink,
        None,
        stop,
        _session_path(tmp_path),
        use_thread=True,
        input_file=src,
    )
    assert sink.raws == ['hello']
    assert sink.explanations == [('hello', 'one two')]
    assert client.queries == ['hello']
    assert _session_path(tmp_path).read_text().strip() == 'sid-1'


async def test_stdin_loop_filter_regex_skips_non_matching(tmp_path: Path):
    src = io.StringIO('skip me\nKOREAN line\n')
    client = FakeClaudeSDKClient([[make_assistant('explanation'), make_result('sid')]])
    sink = _RecordingSink()
    await stdin_loop(
        client,  # pyright: ignore[reportArgumentType]
        sink,
        re.compile(r'KOREAN'),
        asyncio.Event(),
        _session_path(tmp_path),
        use_thread=True,
        input_file=src,
    )
    assert sink.raws == ['skip me', 'KOREAN line']
    assert sink.explanations == [('KOREAN line', 'explanation')]
    assert client.queries == ['KOREAN line']


async def test_stdin_loop_skips_blank_and_duplicate(tmp_path: Path):
    src = io.StringIO('hi\nhi\n\nhi\n')
    client = FakeClaudeSDKClient([[make_assistant('x'), make_result('sid')]])
    sink = _RecordingSink()
    await stdin_loop(
        client,  # pyright: ignore[reportArgumentType]
        sink,
        None,
        asyncio.Event(),
        _session_path(tmp_path),
        use_thread=True,
        input_file=src,
    )
    # Four raw lines received, but only one query (duplicates + blank skipped).
    assert sink.raws == ['hi', 'hi', '', 'hi']
    assert client.queries == ['hi']


async def test_stdin_loop_saves_session_id_only_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = io.StringIO('a\nb\n')
    client = FakeClaudeSDKClient(
        [
            [make_assistant('x'), make_result('sid-first')],
            [make_assistant('y'), make_result('sid-second')],
        ]
    )
    sink = _RecordingSink()
    calls: list[tuple[Path, str]] = []

    def fake_save(path: Path, sid: str) -> None:
        calls.append((path, sid))

    monkeypatch.setattr(core, 'save_session_id', fake_save)
    await stdin_loop(
        client,  # pyright: ignore[reportArgumentType]
        sink,
        None,
        asyncio.Event(),
        _session_path(tmp_path),
        use_thread=True,
        input_file=src,
    )
    assert calls == [(_session_path(tmp_path), 'sid-first')]


async def test_stdin_loop_query_raises_emits_error_and_continues(tmp_path: Path):
    src = io.StringIO('first\n')
    client = FakeClaudeSDKClient(raise_on_query=RuntimeError('boom'))
    sink = _RecordingSink()
    await stdin_loop(
        client,  # pyright: ignore[reportArgumentType]
        sink,
        None,
        asyncio.Event(),
        _session_path(tmp_path),
        use_thread=True,
        input_file=src,
    )
    assert sink.errors == ['query failed: boom']
    assert sink.explanations == []


async def test_stdin_loop_save_session_oserror_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = io.StringIO('a\n')
    client = FakeClaudeSDKClient([[make_assistant('x'), make_result('sid')]])
    sink = _RecordingSink()

    def fake_save(_path: Path, _sid: str) -> None:
        raise OSError('disk full')

    monkeypatch.setattr(core, 'save_session_id', fake_save)
    await stdin_loop(
        client,  # pyright: ignore[reportArgumentType]
        sink,
        None,
        asyncio.Event(),
        _session_path(tmp_path),
        use_thread=True,
        input_file=src,
    )
    assert any('could not save session id: disk full' in e for e in sink.errors)
    # The explanation still fires despite the save failure.
    assert sink.explanations == [('a', 'x')]


async def test_stdin_loop_empty_response_skipped(tmp_path: Path):
    """An assistant message with empty text shouldn't produce an explanation."""
    src = io.StringIO('a\n')
    client = FakeClaudeSDKClient([[make_assistant(''), make_result('sid')]])
    sink = _RecordingSink()
    await stdin_loop(
        client,  # pyright: ignore[reportArgumentType]
        sink,
        None,
        asyncio.Event(),
        _session_path(tmp_path),
        use_thread=True,
        input_file=src,
    )
    assert sink.explanations == []


async def test_stdin_loop_stop_event_breaks_loop(tmp_path: Path):
    src = io.StringIO('one\ntwo\n')
    client = FakeClaudeSDKClient(
        [
            [make_assistant('r1'), make_result('sid')],
            [make_assistant('r2'), make_result('sid')],
        ]
    )
    sink = _RecordingSink()
    stop = asyncio.Event()
    stop.set()
    await stdin_loop(
        client,  # pyright: ignore[reportArgumentType]
        sink,
        None,
        stop,
        _session_path(tmp_path),
        use_thread=True,
        input_file=src,
    )
    # Stop event fires before the first line is processed.
    assert sink.raws == []
    assert client.queries == []
