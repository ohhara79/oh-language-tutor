"""Tests for ``tutor.core``."""

from __future__ import annotations

import asyncio
import io
import re
from typing import Any

from tutor.core import _stdin_line_stream, stdin_loop
from tutor.types import TutorEntry


class _RecordingSink:
    def __init__(self):
        self.raws: list[str] = []
        self.appended: list[TutorEntry] = []
        self.errors: list[str] = []

    def on_raw_line(self, raw: str) -> None:
        self.raws.append(raw)

    def on_entry_appended(self, entry: TutorEntry) -> None:
        self.appended.append(entry)

    def on_entry_explained(self, entry: TutorEntry) -> None: ...
    def on_thread_chunk(self, thread_id: str, chunk: str) -> None: ...
    def on_thread_done(self, thread_id: str, last_assistant: str) -> None: ...
    def on_thread_list(self, threads: list[Any]) -> None: ...
    def on_tutor_entry_removed(self, anchor_id: str) -> None: ...
    def on_entry_explanation_cleared(self, entry: TutorEntry) -> None: ...

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


async def test_stdin_loop_appends_unexplained_entry():
    src = io.StringIO('hello\n')
    sink = _RecordingSink()
    await stdin_loop(sink, None, asyncio.Event(), use_thread=True, input_file=src)
    assert sink.raws == ['hello']
    assert len(sink.appended) == 1
    entry = sink.appended[0]
    assert entry.raw == 'hello'
    assert entry.explanation is None


async def test_stdin_loop_filter_regex_skips_non_matching():
    src = io.StringIO('skip me\nKOREAN line\n')
    sink = _RecordingSink()
    await stdin_loop(sink, re.compile(r'KOREAN'), asyncio.Event(), use_thread=True, input_file=src)
    assert sink.raws == ['skip me', 'KOREAN line']
    assert [e.raw for e in sink.appended] == ['KOREAN line']


async def test_stdin_loop_filter_regex_capture_group_rewrites_line():
    src = io.StringIO('1: aa bb\nnope\n')
    sink = _RecordingSink()
    await stdin_loop(
        sink,
        re.compile(r'^\d+:\s*(.+)$'),
        asyncio.Event(),
        use_thread=True,
        input_file=src,
    )
    # Raw log keeps the original stdin line untouched.
    assert sink.raws == ['1: aa bb', 'nope']
    # Persisted entry uses group(1) only.
    assert [e.raw for e in sink.appended] == ['aa bb']


async def test_stdin_loop_filter_regex_falls_back_when_group_did_not_match():
    # Alternation: group 1 captures only on the 'foo' branch; on 'bar' it's None.
    src = io.StringIO('bar\n')
    sink = _RecordingSink()
    await stdin_loop(
        sink,
        re.compile(r'(foo)|bar'),
        asyncio.Event(),
        use_thread=True,
        input_file=src,
    )
    assert [e.raw for e in sink.appended] == ['bar']


async def test_stdin_loop_skips_blank_and_duplicate():
    src = io.StringIO('hi\nhi\n\nhi\n')
    sink = _RecordingSink()
    await stdin_loop(sink, None, asyncio.Event(), use_thread=True, input_file=src)
    # Four raw lines received, but only one appended (duplicates + blank skipped).
    assert sink.raws == ['hi', 'hi', '', 'hi']
    assert [e.raw for e in sink.appended] == ['hi']


async def test_stdin_loop_stop_event_breaks_loop():
    src = io.StringIO('one\ntwo\n')
    sink = _RecordingSink()
    stop = asyncio.Event()
    stop.set()
    await stdin_loop(sink, None, stop, use_thread=True, input_file=src)
    # Stop event fires before the first line is processed.
    assert sink.raws == []
    assert sink.appended == []
