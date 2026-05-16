"""Tests for ``tutor.thread_pool.FollowupThreadPool``."""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING

import pytest

from tests.conftest import (
    FakeClaudeSDKClient,
    make_assistant_multi,
    make_result,
    make_text_delta,
)
from tutor import thread_pool as tp_mod
from tutor.thread_pool import FollowupThreadPool
from tutor.thread_store import ThreadStore
from tutor.tutor_store import TutorStore
from tutor.types import ThreadMessage, ThreadMeta, TutorEntry

if TYPE_CHECKING:
    from pathlib import Path

    from tests.conftest import FakeClaudeSDKClientFactory


class RecordingSink:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.chunks: list[tuple[str, str]] = []
        self.dones: list[tuple[str, str]] = []
        self.thread_lists: list[list[ThreadMeta]] = []
        self.entry_removed: list[str] = []
        self.entry_explanation_cleared: list[str] = []

    def on_raw_line(self, raw: str) -> None: ...
    def on_entry_appended(self, entry: TutorEntry) -> None: ...
    def on_entry_explained(self, entry: TutorEntry) -> None: ...
    def on_thread_chunk(self, thread_id: str, chunk: str) -> None:
        self.chunks.append((thread_id, chunk))

    def on_thread_done(self, thread_id: str, last_assistant: str) -> None:
        self.dones.append((thread_id, last_assistant))

    def on_thread_list(self, threads: list[ThreadMeta]) -> None:
        self.thread_lists.append(list(threads))

    def on_tutor_entry_removed(self, anchor_id: str) -> None:
        self.entry_removed.append(anchor_id)

    def on_entry_explanation_cleared(self, entry: TutorEntry) -> None:
        self.entry_explanation_cleared.append(entry.id)

    def on_error(self, msg: str) -> None:
        self.errors.append(msg)


def _pool(tmp_path: Path, sink: RecordingSink) -> tuple[FollowupThreadPool, ThreadStore, TutorStore, io.StringIO]:
    tstore = ThreadStore(tmp_path / 'threads')
    tutor_store = TutorStore(tmp_path / 'tutor.json')
    log = io.StringIO()
    pool = FollowupThreadPool(
        model='test-model',
        sink=sink,
        store=tstore,
        tutor_store=tutor_store,
        log=log,
    )
    return pool, tstore, tutor_store, log


_OPEN_AUDIENCE = {'source_language': 'ko', 'target_language': 'en', 'level': 'intermediate'}


# -- open_thread -------------------------------------------------------------


async def test_open_thread_unknown_anchor_emits_error(tmp_path: Path):
    sink = RecordingSink()
    pool, _, _, _ = _pool(tmp_path, sink)
    await pool.open_thread('t-1', 'missing-anchor', **_OPEN_AUDIENCE)
    assert any('missing-anchor' in e for e in sink.errors)
    assert pool.peek_meta('t-1') is None


async def test_open_thread_success_seeds_active_without_connecting(tmp_path: Path):
    sink = RecordingSink()
    pool, _, tutor_store, log = _pool(tmp_path, sink)
    entry = TutorEntry(raw='hello', explanation='meaning', id='a-1')
    tutor_store.append(entry)

    await pool.open_thread('t-1', 'a-1', **_OPEN_AUDIENCE)
    meta = pool.peek_meta('t-1')
    assert meta is not None
    assert meta.anchor_raw == 'hello'
    assert meta.anchor_id == 'a-1'
    assert '=== thread open' in log.getvalue()


# -- reopen_thread -----------------------------------------------------------


async def test_reopen_thread_missing_emits_error(tmp_path: Path):
    sink = RecordingSink()
    pool, _, _, _ = _pool(tmp_path, sink)
    await pool.reopen_thread('t-nope')
    assert any('t-nope' in e for e in sink.errors)


async def test_reopen_thread_loads_meta_and_sets_resume(tmp_path: Path):
    sink = RecordingSink()
    pool, tstore, _, _ = _pool(tmp_path, sink)
    meta = ThreadMeta(
        thread_id='t-1',
        anchor_raw='hi',
        session_id='stored-sid',
        created_at='2026-04-18T00:00:00+00:00',
        anchor_id='a',
    )
    tstore.save_thread(meta)

    await pool.reopen_thread('t-1')
    assert pool.peek_meta('t-1') is not None
    # Private state inspection: the active thread should have resume_session_id wired
    at = pool._active['t-1']
    assert at.resume_session_id == 'stored-sid'
    assert at.client is None


# -- send_message ------------------------------------------------------------


async def test_send_message_unknown_thread_emits_error(tmp_path: Path):
    sink = RecordingSink()
    pool, _, _, _ = _pool(tmp_path, sink)
    await pool.send_message('t-nope', 'hi')
    assert any('t-nope' in e for e in sink.errors)


async def _drain(pool: FollowupThreadPool, thread_id: str) -> None:
    at = pool._active.get(thread_id)
    if at and at.task:
        try:
            await at.task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


async def test_send_message_happy_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_client_factory: FakeClaudeSDKClientFactory,
):
    sink = RecordingSink()
    pool, _, tutor_store, _ = _pool(tmp_path, sink)
    tutor_store.append(TutorEntry(raw='r', explanation='e', id='a-1'))
    await pool.open_thread('t-1', 'a-1', **_OPEN_AUDIENCE)

    client = FakeClaudeSDKClient(
        [
            [
                make_text_delta('foo '),
                make_text_delta('bar'),
                make_assistant_multi('foo ', 'bar'),
                make_result('new-sid'),
            ]
        ]
    )
    fake_client_factory.push(client)
    monkeypatch.setattr(tp_mod, 'ClaudeSDKClient', fake_client_factory)

    await pool.send_message('t-1', 'question?')
    await _drain(pool, 't-1')

    assert client.queries == ['question?']
    assert sink.chunks == [('t-1', 'foo '), ('t-1', 'bar')]
    assert sink.dones == [('t-1', 'foo bar')]
    meta = pool.peek_meta('t-1')
    assert meta is not None
    roles = [(m.role, m.text) for m in meta.messages]
    assert roles == [('user', 'question?'), ('assistant', 'foo bar')]
    assert meta.session_id == 'new-sid'


async def test_send_message_fresh_connect_failure_emits_done_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_client_factory: FakeClaudeSDKClientFactory,
):
    sink = RecordingSink()
    pool, _, tutor_store, _ = _pool(tmp_path, sink)
    tutor_store.append(TutorEntry(raw='r', explanation='e', id='a-1'))
    await pool.open_thread('t-1', 'a-1', **_OPEN_AUDIENCE)

    client = FakeClaudeSDKClient(raise_on_enter=RuntimeError('no network'))
    fake_client_factory.push(client)
    monkeypatch.setattr(tp_mod, 'ClaudeSDKClient', fake_client_factory)

    await pool.send_message('t-1', 'hi')
    await _drain(pool, 't-1')

    assert any('no network' in e for e in sink.errors)
    assert sink.dones == [('t-1', '')]


async def test_send_message_resume_failure_replays_and_proceeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_client_factory: FakeClaudeSDKClientFactory,
):
    sink = RecordingSink()
    pool, tstore, _, log = _pool(tmp_path, sink)
    # Pre-populate a saved thread with prior messages so replay has content.
    prior_meta = ThreadMeta(
        thread_id='t-1',
        anchor_raw='hi',
        session_id='dead-sid',
        created_at='2026-04-18T00:00:00+00:00',
        anchor_id='a-1',
        messages=[
            ThreadMessage(role='user', text='prev-q'),
            ThreadMessage(role='assistant', text='prev-a'),
        ],
    )
    tstore.save_thread(prior_meta)
    await pool.reopen_thread('t-1')

    # First client: resume attempt fails on enter.
    failing = FakeClaudeSDKClient(raise_on_enter=RuntimeError('resume gone'))
    # Second client: fresh, seeds one batch for the replay preamble and one for the actual user text.
    fresh = FakeClaudeSDKClient(
        [
            [make_result('ignore-sid')],  # preamble reply
            [make_assistant_multi('ok'), make_result('fresh-sid')],  # real user message
        ]
    )
    fake_client_factory.push(failing)
    fake_client_factory.push(fresh)
    monkeypatch.setattr(tp_mod, 'ClaudeSDKClient', fake_client_factory)

    await pool.send_message('t-1', 'new-q')
    await _drain(pool, 't-1')

    # Replay preamble + real query were both sent
    assert len(fresh.queries) == 2
    assert 'prev-q' in fresh.queries[0]
    assert fresh.queries[1] == 'new-q'
    assert any('replayed 1/1' in e for e in sink.errors)
    assert '=== resume failed' in log.getvalue()


# -- hide_thread / delete_thread --------------------------------------------


async def test_hide_thread_nonexistent_is_noop(tmp_path: Path):
    sink = RecordingSink()
    pool, _, _, _ = _pool(tmp_path, sink)
    await pool.hide_thread('missing')
    # No error path for missing — just a silent noop
    assert sink.errors == []


async def test_delete_thread_removes_file_and_refreshes_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_client_factory: FakeClaudeSDKClientFactory,
):
    sink = RecordingSink()
    pool, tstore, tutor_store, _ = _pool(tmp_path, sink)
    tutor_store.append(TutorEntry(raw='r', explanation='e', id='a-1'))
    await pool.open_thread('t-1', 'a-1', **_OPEN_AUDIENCE)
    # Persist so there's something to delete
    tstore.save_thread(pool.peek_meta('t-1'))  # pyright: ignore[reportArgumentType]
    assert tstore.load_thread('t-1') is not None

    monkeypatch.setattr(tp_mod, 'ClaudeSDKClient', fake_client_factory)
    await pool.delete_thread('t-1')
    assert tstore.load_thread('t-1') is None
    # Last broadcast after delete is an empty list
    assert sink.thread_lists[-1] == []


async def test_delete_tutor_entry_cascades(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_client_factory: FakeClaudeSDKClientFactory,
):
    sink = RecordingSink()
    pool, tstore, tutor_store, _ = _pool(tmp_path, sink)
    entry = TutorEntry(raw='r', explanation='e', id='a-1')
    tutor_store.append(entry)

    await pool.open_thread('t-1', 'a-1', **_OPEN_AUDIENCE)
    tstore.save_thread(pool.peek_meta('t-1'))  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(tp_mod, 'ClaudeSDKClient', fake_client_factory)
    await pool.delete_tutor_entry('a-1')

    assert tstore.load_thread('t-1') is None
    assert tutor_store.load() == []
    assert sink.entry_removed == ['a-1']


async def test_delete_tutor_entry_empty_id_noops(tmp_path: Path):
    sink = RecordingSink()
    pool, _, _, _ = _pool(tmp_path, sink)
    await pool.delete_tutor_entry('')
    assert sink.entry_removed == []


# -- close_all ---------------------------------------------------------------


async def test_close_all_disconnects_active_threads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_client_factory: FakeClaudeSDKClientFactory,
):
    sink = RecordingSink()
    pool, _, tutor_store, _ = _pool(tmp_path, sink)
    tutor_store.append(TutorEntry(raw='r', explanation='e', id='a-1'))
    await pool.open_thread('t-1', 'a-1', **_OPEN_AUDIENCE)
    await pool.open_thread('t-2', 'a-1', **_OPEN_AUDIENCE)

    monkeypatch.setattr(tp_mod, 'ClaudeSDKClient', fake_client_factory)
    await pool.close_all()
    assert pool._active == {}


# -- list / peek / load ------------------------------------------------------


async def test_list_and_load_delegates_to_store(tmp_path: Path):
    sink = RecordingSink()
    pool, tstore, _, _ = _pool(tmp_path, sink)
    meta = ThreadMeta(
        thread_id='t-1',
        anchor_raw='hi',
        session_id='s',
        created_at='2026-04-18T00:00:00+00:00',
        anchor_id='a',
    )
    tstore.save_thread(meta)
    assert [m.thread_id for m in pool.list_threads()] == ['t-1']
    assert pool.load_thread_meta('t-1') is not None


async def test_peek_meta_prefers_active_over_disk(tmp_path: Path):
    sink = RecordingSink()
    pool, tstore, tutor_store, _ = _pool(tmp_path, sink)
    tutor_store.append(TutorEntry(raw='r', explanation='e', id='a-1'))
    disk_meta = ThreadMeta(
        thread_id='t-1',
        anchor_raw='stale',
        session_id='s',
        created_at='2026-04-18T00:00:00+00:00',
        anchor_id='a-1',
    )
    tstore.save_thread(disk_meta)
    await pool.open_thread('t-1', 'a-1', **_OPEN_AUDIENCE)  # overwrites in-memory with 'r' anchor_raw
    assert pool.peek_meta('t-1').anchor_raw == 'r'  # pyright: ignore[reportOptionalMemberAccess]
