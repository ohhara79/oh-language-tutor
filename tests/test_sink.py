"""Tests for ``tutor.sink``."""

from __future__ import annotations

import io
import sys
from typing import TYPE_CHECKING

import pytest

from tutor.sink import TerminalSink, ansi_enabled
from tutor.tutor_store import TutorStore

if TYPE_CHECKING:
    from pathlib import Path


# -- ansi_enabled ------------------------------------------------------------


def test_ansi_enabled_true_when_tty_and_no_color_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sys.stdout, 'isatty', lambda: True)
    monkeypatch.delenv('NO_COLOR', raising=False)
    assert ansi_enabled() is True


def test_ansi_enabled_false_when_no_color_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sys.stdout, 'isatty', lambda: True)
    monkeypatch.setenv('NO_COLOR', '1')
    assert ansi_enabled() is False


def test_ansi_enabled_false_when_not_a_tty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sys.stdout, 'isatty', lambda: False)
    monkeypatch.delenv('NO_COLOR', raising=False)
    assert ansi_enabled() is False


# -- TerminalSink ------------------------------------------------------------


def _sink(tmp_path: Path, *, ansi: bool = False) -> tuple[TerminalSink, io.StringIO, TutorStore]:
    log = io.StringIO()
    store = TutorStore(tmp_path / 'tutor.json')
    return TerminalSink(log, ansi=ansi, tutor_store=store), log, store


def test_on_raw_line_writes_stdout_and_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    sink, log, _ = _sink(tmp_path)
    sink.on_raw_line('hello world')
    captured = capsys.readouterr()
    assert captured.out == 'hello world\n'
    assert log.getvalue() == 'hello world\n'


async def test_on_explanation_without_ansi_writes_plain_rule(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    sink, log, store = _sink(tmp_path, ansi=False)
    sink.on_explanation('raw-line', 'the explanation')
    await sink.flush_pending_writes()

    captured = capsys.readouterr()
    rule = '\u2500' * 72
    assert rule in captured.out
    assert 'the explanation' in captured.out
    assert '\033[' not in captured.out
    assert '--- explanation for: raw-line' in log.getvalue()
    assert 'the explanation' in log.getvalue()
    entries = store.load()
    assert len(entries) == 1
    assert entries[0].raw == 'raw-line'
    assert entries[0].explanation == 'the explanation'


async def test_on_explanation_with_ansi_emits_escapes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    sink, _, _ = _sink(tmp_path, ansi=True)
    sink.on_explanation('r', 'e')
    await sink.flush_pending_writes()
    captured = capsys.readouterr()
    assert '\033[2m' in captured.out
    assert '\033[36m' in captured.out
    assert '\033[0m' in captured.out


def test_on_error_writes_stderr_with_prefix(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    sink, _, _ = _sink(tmp_path)
    sink.on_error('something broke')
    captured = capsys.readouterr()
    assert captured.err == '[oh-language-tutor] something broke\n'
    assert captured.out == ''


def test_noop_methods_return_none(tmp_path: Path):
    sink, _, _ = _sink(tmp_path)
    assert sink.on_thread_chunk('t', 'c') is None
    assert sink.on_thread_done('t', 'msg') is None
    assert sink.on_thread_list([]) is None
    assert sink.on_tutor_entry_removed('a') is None


async def test_flush_pending_writes_with_no_tasks_is_noop(tmp_path: Path):
    sink, _, _ = _sink(tmp_path)
    await sink.flush_pending_writes()
