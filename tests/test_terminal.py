"""Tests for ``tutor.terminal.run_terminal``."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any

import pytest

from tests.conftest import FakeClaudeSDKClient
from tutor import terminal as term_mod
from tutor.terminal import run_terminal
from tutor.tutor_store import TutorStore
from tutor.types import TutorEntry

if TYPE_CHECKING:
    from pathlib import Path


def _args(state_dir: Path, **overrides: Any) -> argparse.Namespace:
    base = argparse.Namespace(
        source_language='Korean',
        target_language='English',
        level='intermediate',
        extra_system_prompt=None,
        filter_regex=None,
        skip_token='SKIP',
        explain_model='claude-haiku-4-5',
        ask_model='claude-opus-4-7',
        state_dir=str(state_dir),
        new_session=False,
        resume_id=None,
        tui=False,
        web=False,
        web_host='127.0.0.1',
        web_port=8000,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


async def test_run_terminal_invalid_filter_regex_raises_system_exit(tmp_path: Path):
    args = _args(tmp_path, filter_regex='(bad')
    with pytest.raises(SystemExit, match='invalid --filter-regex'):
        await run_terminal(args)


async def test_run_terminal_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    args = _args(tmp_path / 'state')
    fake_client = FakeClaudeSDKClient()

    async def fake_connect(*_a: Any, **_kw: Any) -> FakeClaudeSDKClient:
        return fake_client

    stdin_calls: list[Any] = []

    async def fake_stdin_loop(*a: Any, **kw: Any) -> None:
        stdin_calls.append((a, kw))

    monkeypatch.setattr(term_mod, 'connect_with_fallback', fake_connect)
    monkeypatch.setattr(term_mod, 'stdin_loop', fake_stdin_loop)

    rc = await run_terminal(args)
    assert rc == 0
    assert fake_client.exited is True
    assert len(stdin_calls) == 1
    log_text = (tmp_path / 'state' / 'tutor.log').read_text()
    assert '=== session start' in log_text
    assert '=== session end ===' in log_text


async def test_run_terminal_with_resume_id_passes_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # Seed a resume id on disk and a tutor entry.
    state = tmp_path / 'state'
    state.mkdir(parents=True)
    (state / 'session.id').write_text('resume-xyz\n')
    store = TutorStore(state / 'tutor.json')
    store.append(TutorEntry(raw='r', explanation='e', id='a'))

    args = _args(state)
    captured: dict[str, Any] = {}

    async def fake_connect(primary: Any, *, fresh: Any, tutor_entries: Any, sink: Any, log: Any) -> FakeClaudeSDKClient:
        captured['tutor_entries'] = tutor_entries
        captured['primary_resume'] = primary.resume
        return FakeClaudeSDKClient()

    async def fake_stdin_loop(*_a: Any, **_kw: Any) -> None:
        return

    monkeypatch.setattr(term_mod, 'connect_with_fallback', fake_connect)
    monkeypatch.setattr(term_mod, 'stdin_loop', fake_stdin_loop)

    await run_terminal(args)
    assert captured['primary_resume'] == 'resume-xyz'
    assert len(captured['tutor_entries']) == 1


async def test_run_terminal_without_resume_passes_empty_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    state = tmp_path / 'state'
    args = _args(state)
    captured: dict[str, Any] = {}

    async def fake_connect(primary: Any, *, fresh: Any, tutor_entries: Any, sink: Any, log: Any) -> FakeClaudeSDKClient:
        captured['tutor_entries'] = tutor_entries
        return FakeClaudeSDKClient()

    async def fake_stdin_loop(*_a: Any, **_kw: Any) -> None:
        return

    monkeypatch.setattr(term_mod, 'connect_with_fallback', fake_connect)
    monkeypatch.setattr(term_mod, 'stdin_loop', fake_stdin_loop)

    await run_terminal(args)
    assert captured['tutor_entries'] == []


async def test_run_terminal_suppresses_sigint_notimplemented(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """On platforms where add_signal_handler isn't supported the code must not crash."""
    import asyncio

    args = _args(tmp_path / 'state')

    async def fake_connect(*_a: Any, **_kw: Any) -> FakeClaudeSDKClient:
        return FakeClaudeSDKClient()

    async def fake_stdin_loop(*_a: Any, **_kw: Any) -> None:
        return

    monkeypatch.setattr(term_mod, 'connect_with_fallback', fake_connect)
    monkeypatch.setattr(term_mod, 'stdin_loop', fake_stdin_loop)

    real_loop = asyncio.get_running_loop()

    def raise_ni(*_a: Any, **_kw: Any) -> None:
        raise NotImplementedError

    monkeypatch.setattr(real_loop, 'add_signal_handler', raise_ni)
    rc = await run_terminal(args)
    assert rc == 0
