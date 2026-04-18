"""Pilot-driven tests for ``tutor.tui.OhLanguageTutorApp``."""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING, Any

from textual.widgets import Button, Input, Label, Static

from tutor.thread_store import ThreadStore
from tutor.tui import ExplanationBlock, LineBlock, OhLanguageTutorApp, ThreadListItem
from tutor.tutor_store import TutorStore
from tutor.types import (
    Cmd,
    DeleteThreadCmd,
    DeleteTutorEntryCmd,
    HideThreadCmd,
    OpenThreadCmd,
    ReopenThreadCmd,
    SendMessageCmd,
    ThreadMeta,
    TutorEntry,
)

if TYPE_CHECKING:
    from pathlib import Path


class FakePool:
    """FollowupThreadPool stand-in that records calls and returns seeded metas."""

    def __init__(self, threads: list[ThreadMeta] | None = None) -> None:
        self._threads: dict[str, ThreadMeta] = {m.thread_id: m for m in (threads or [])}
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def list_threads(self) -> list[ThreadMeta]:
        return list(self._threads.values())

    def peek_meta(self, thread_id: str) -> ThreadMeta | None:
        return self._threads.get(thread_id)

    def load_thread_meta(self, thread_id: str) -> ThreadMeta | None:
        return self._threads.get(thread_id)


def _make_app(
    tmp_path: Path,
    *,
    tutor_entries: list[TutorEntry] | None = None,
    threads: list[ThreadMeta] | None = None,
) -> tuple[OhLanguageTutorApp, FakePool, asyncio.Queue[Cmd], io.StringIO, TutorStore]:
    tutor_store = TutorStore(tmp_path / 'tutor.json')
    for entry in tutor_entries or []:
        tutor_store.append(entry)
    thread_store = ThreadStore(tmp_path / 'threads')
    log = io.StringIO()
    queue: asyncio.Queue[Cmd] = asyncio.Queue()
    pool = FakePool(threads)
    app = OhLanguageTutorApp(
        pool=pool,  # pyright: ignore[reportArgumentType]
        cmd_queue=queue,
        log=log,
        tutor_store=tutor_store,
        thread_store=thread_store,
        state_dir=tmp_path,
    )
    return app, pool, queue, log, tutor_store


# -- compose / on_mount ------------------------------------------------------


async def test_compose_and_mount(tmp_path: Path):
    app, _, _, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        # compose yielded the expected containers
        assert pilot.app.query_one('#stream-pane')
        assert pilot.app.query_one('#thread-pane')
        assert pilot.app.query_one('#thread-list-container')
        assert pilot.app.query_one('#thread-messages')
        assert pilot.app.query_one('#thread-input', Input)
        assert pilot.app.query_one('#status-bar', Label)
        # placeholder present when no entries
        assert pilot.app.query('#stream-placeholder')
        # hot references cached
        assert app._stream_pane is not None
        assert app._thread_list_container is not None
        assert app._thread_messages is not None
        assert app._thread_input is not None
        assert app._status_bar is not None


async def test_restore_tutor_entries_mounts_line_and_explanation_blocks(tmp_path: Path):
    entries = [
        TutorEntry(raw='r1', explanation='e1', id='a-1'),
        TutorEntry(raw='r2', explanation='e2', id='a-2'),
    ]
    app, _, _, _, _ = _make_app(tmp_path, tutor_entries=entries)
    async with app.run_test():
        # placeholder removed, blocks mounted
        assert not app.query('#stream-placeholder')
        line_blocks = list(app.query(LineBlock).results(LineBlock))
        assert [b.tutor_id for b in line_blocks] == ['a-1', 'a-2']
        exp_blocks = list(app.query(ExplanationBlock))
        assert len(exp_blocks) == 2


async def test_on_error_before_mount_stores_pending(tmp_path: Path):
    app, _, _, _, _ = _make_app(tmp_path)
    # Before mount: _screen_stack is empty
    app.on_error('boom')
    assert 'boom' in app._pending_errors


async def test_pending_error_displayed_on_mount(tmp_path: Path):
    app, _, _, _, _ = _make_app(tmp_path)
    app._pending_errors.append('startup fail')
    async with app.run_test() as pilot:
        await pilot.pause()
        status = app._status_bar
        assert 'startup fail' in str(status.render())


# -- event handlers ----------------------------------------------------------


async def test_on_raw_line_writes_log_and_removes_placeholder(tmp_path: Path):
    app, _, _, log, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        app.on_raw_line('hello')
        await pilot.pause()
    assert log.getvalue() == 'hello\n'
    # After call_later fires, placeholder is removed
    assert not app.query('#stream-placeholder')


async def test_on_explanation_mounts_blocks_and_writes_disk(tmp_path: Path):
    app, _, _, log, tutor_store = _make_app(tmp_path)
    async with app.run_test() as pilot:
        app.on_explanation('raw-x', 'the **why**')
        await pilot.pause()
        # Flush the async append task
        if app._pending_writes:
            await asyncio.gather(*app._pending_writes, return_exceptions=True)
        line_blocks = list(app.query(LineBlock).results(LineBlock))
        assert len(line_blocks) == 1
        assert line_blocks[0].raw == 'raw-x'
        assert '--- explanation for: raw-x' in log.getvalue()
    assert [e.raw for e in tutor_store.load()] == ['raw-x']


async def test_on_thread_chunk_and_done(tmp_path: Path):
    app, _, _, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        # Activate a thread so chunks are accepted
        app._current_thread_id = 't-1'
        app._thread_messages.display = True

        app.on_thread_chunk('t-1', 'foo')
        await pilot.pause()
        app.on_thread_chunk('t-1', 'bar')
        await pilot.pause()
        assert app._streaming_text == 'foobar'
        assert app._streaming_label is not None

        app.on_thread_done('t-1', 'foobar')
        await pilot.pause()
        assert app._streaming_label is None
        assert app._streaming_text == ''
        assert app._thread_input.disabled is False


async def test_on_thread_chunk_ignored_for_other_thread(tmp_path: Path):
    app, _, _, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        app._current_thread_id = 't-1'
        app.on_thread_chunk('t-other', 'ignored')
        await pilot.pause()
        assert app._streaming_text == ''
        assert app._streaming_label is None


async def test_on_thread_list_populates_container(tmp_path: Path):
    meta_a = ThreadMeta(thread_id='t-a', anchor_raw='hello', session_id='s', created_at='2026-04-18T00:00:00+00:00')
    meta_b = ThreadMeta(thread_id='t-b', anchor_raw='world', session_id='s', created_at='2026-04-18T00:00:00+00:00')
    app, pool, _, _, _ = _make_app(tmp_path, threads=[meta_a, meta_b])
    async with app.run_test() as pilot:
        await pilot.pause()
        items = list(app.query(ThreadListItem).results(ThreadListItem))
        assert len(items) == 2
        # Now simulate pool going empty and list refreshing
        pool._threads.clear()
        app.on_thread_list([])
        await pilot.pause()
        items = list(app.query(ThreadListItem).results(ThreadListItem))
        assert len(items) == 0


async def test_on_tutor_entry_removed_drops_line_and_explanation(tmp_path: Path):
    entries = [
        TutorEntry(raw='keep', explanation='e1', id='a-keep'),
        TutorEntry(raw='drop', explanation='e2', id='a-drop'),
    ]
    app, _, _, _, _ = _make_app(tmp_path, tutor_entries=entries)
    async with app.run_test() as pilot:
        assert 'a-drop' in app._line_blocks
        app.on_tutor_entry_removed('a-drop')
        await pilot.pause()
        assert 'a-drop' not in app._line_blocks
        remaining = [b.tutor_id for b in app.query(LineBlock).results(LineBlock)]
        assert remaining == ['a-keep']
        # Only one explanation block remains
        assert len(list(app.query(ExplanationBlock))) == 1


async def test_on_error_after_mount_updates_status(tmp_path: Path):
    app, _, _, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        app.on_error('runtime issue')
        await pilot.pause()
        assert 'runtime issue' in str(app._status_bar.render())


# -- two-tap delete state machines ------------------------------------------


async def test_line_delete_arms_then_queues(tmp_path: Path):
    entries = [TutorEntry(raw='r', explanation='e', id='a-1')]
    app, _, queue, _, _ = _make_app(tmp_path, tutor_entries=entries)
    async with app.run_test() as pilot:
        btn = app.query_one('#line-delete-a-1', Button)
        app._handle_line_delete_press('a-1', btn)
        await pilot.pause()
        assert app._delete_arming_id == 'a-1'
        assert 'armed' in btn.classes
        assert queue.empty()

        app._handle_line_delete_press('a-1', btn)
        await pilot.pause()
        assert app._delete_arming_id is None
        # Queue has a DeleteTutorEntryCmd
        cmd = queue.get_nowait()
        assert isinstance(cmd, DeleteTutorEntryCmd)
        assert cmd.anchor_id == 'a-1'


async def test_line_delete_switching_targets_disarms_first(tmp_path: Path):
    entries = [
        TutorEntry(raw='r1', explanation='e1', id='a-1'),
        TutorEntry(raw='r2', explanation='e2', id='a-2'),
    ]
    app, _, queue, _, _ = _make_app(tmp_path, tutor_entries=entries)
    async with app.run_test() as pilot:
        btn1 = app.query_one('#line-delete-a-1', Button)
        btn2 = app.query_one('#line-delete-a-2', Button)
        app._handle_line_delete_press('a-1', btn1)
        await pilot.pause()
        assert 'armed' in btn1.classes
        app._handle_line_delete_press('a-2', btn2)
        await pilot.pause()
        assert 'armed' not in btn1.classes
        assert 'armed' in btn2.classes
        assert app._delete_arming_id == 'a-2'
        assert queue.empty()


async def test_disarm_delete_if_ignores_mismatched_id(tmp_path: Path):
    entries = [TutorEntry(raw='r', explanation='e', id='a-1')]
    app, _, _, _, _ = _make_app(tmp_path, tutor_entries=entries)
    async with app.run_test() as pilot:
        btn = app.query_one('#line-delete-a-1', Button)
        app._handle_line_delete_press('a-1', btn)
        await pilot.pause()
        # A stale timer callback arrives for a different id — should be a no-op
        app._disarm_delete_if('different-id')
        assert app._delete_arming_id == 'a-1'


async def test_thread_delete_arms_then_queues(tmp_path: Path):
    meta = ThreadMeta(thread_id='t-1', anchor_raw='hi', session_id='s', created_at='2026-04-18T00:00:00+00:00')
    app, _, queue, _, _ = _make_app(tmp_path, threads=[meta])
    async with app.run_test() as pilot:
        await pilot.pause()
        btn = app.query_one('#delete-t-1', Button)
        app._handle_thread_delete_press('t-1', btn)
        await pilot.pause()
        assert app._thread_delete_arming_id == 't-1'
        assert queue.empty()

        app._handle_thread_delete_press('t-1', btn)
        await pilot.pause()
        assert app._thread_delete_arming_id is None
        cmd = queue.get_nowait()
        assert isinstance(cmd, DeleteThreadCmd)
        assert cmd.thread_id == 't-1'


# -- button dispatcher -------------------------------------------------------


async def test_ask_button_opens_new_thread(tmp_path: Path):
    entries = [TutorEntry(raw='source text', explanation='e', id='a-1')]
    app, _, queue, _, _ = _make_app(tmp_path, tutor_entries=entries)
    async with app.run_test() as pilot:
        btn = app.query_one('#ask-a-1', Button)
        await pilot.click(btn)
        await pilot.pause()
        # OpenThreadCmd queued
        cmds: list[Cmd] = []
        while not queue.empty():
            cmds.append(queue.get_nowait())
        assert any(isinstance(c, OpenThreadCmd) and c.anchor_id == 'a-1' for c in cmds)
        assert app._thread_view_mode == 'conversation'
        assert app._current_thread_id is not None


async def test_reopen_button_queues_reopen(tmp_path: Path):
    meta = ThreadMeta(thread_id='t-1', anchor_raw='anchor', session_id='s', created_at='2026-04-18T00:00:00+00:00')
    app, _, queue, _, _ = _make_app(tmp_path, threads=[meta])
    async with app.run_test() as pilot:
        await pilot.pause()
        btn = app.query_one('#reopen-t-1', Button)
        await pilot.click(btn)
        await pilot.pause()
        cmds: list[Cmd] = []
        while not queue.empty():
            cmds.append(queue.get_nowait())
        assert any(isinstance(c, ReopenThreadCmd) and c.thread_id == 't-1' for c in cmds)


async def test_reopen_same_thread_is_idempotent(tmp_path: Path):
    meta = ThreadMeta(thread_id='t-1', anchor_raw='anchor', session_id='s', created_at='2026-04-18T00:00:00+00:00')
    app, _, queue, _, _ = _make_app(tmp_path, threads=[meta])
    async with app.run_test() as pilot:
        await pilot.pause()
        app._current_thread_id = 't-1'
        app._reopen_thread('t-1')
        await pilot.pause()
        # No ReopenThreadCmd queued for fast path
        cmds: list[Cmd] = []
        while not queue.empty():
            cmds.append(queue.get_nowait())
        assert not any(isinstance(c, ReopenThreadCmd) for c in cmds)


# -- input flow --------------------------------------------------------------


async def test_on_input_submitted_empty_is_noop(tmp_path: Path):
    app, _, queue, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        app._current_thread_id = 't-1'
        inp = app._thread_input
        inp.value = '   '
        inp.post_message(Input.Submitted(inp, inp.value))
        await pilot.pause()
        assert queue.empty()


async def test_on_input_submitted_queues_send_message(tmp_path: Path):
    app, _, queue, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        app._current_thread_id = 't-1'
        app._show_conversation_mode()  # ensure thread_messages visible
        inp = app._thread_input
        inp.value = 'my question'
        inp.post_message(Input.Submitted(inp, inp.value))
        await pilot.pause()
        cmd = queue.get_nowait()
        assert isinstance(cmd, SendMessageCmd)
        assert cmd.thread_id == 't-1'
        assert cmd.text == 'my question'
        assert inp.value == ''
        assert inp.disabled is True


# -- escape / hide -----------------------------------------------------------


async def test_action_hide_thread_switches_to_list(tmp_path: Path):
    meta = ThreadMeta(thread_id='t-1', anchor_raw='x', session_id='s', created_at='2026-04-18T00:00:00+00:00')
    app, _, _, _, _ = _make_app(tmp_path, threads=[meta])
    async with app.run_test() as pilot:
        await pilot.pause()
        app._current_thread_id = 't-1'
        app._show_conversation_mode()
        app.action_hide_thread()
        await pilot.pause()
        assert app._thread_view_mode == 'list'
        assert app._thread_list_container.display is True
        assert app._thread_messages.display is False
        assert app._thread_input.display is False


async def test_open_new_thread_switches_previous_out(tmp_path: Path):
    entries = [TutorEntry(raw='r', explanation='e', id='a-1')]
    app, _, queue, _, _ = _make_app(tmp_path, tutor_entries=entries)
    async with app.run_test() as pilot:
        app._current_thread_id = 't-prev'
        app._open_new_thread(anchor_id='a-1', anchor_raw='anchor')
        await pilot.pause()
        cmds: list[Cmd] = []
        while not queue.empty():
            cmds.append(queue.get_nowait())
        # Both HideThreadCmd (for the prior) and OpenThreadCmd (new) appear
        assert any(isinstance(c, HideThreadCmd) and c.thread_id == 't-prev' for c in cmds)
        assert any(isinstance(c, OpenThreadCmd) and c.anchor_id == 'a-1' for c in cmds)
        assert app._current_thread_id != 't-prev'


# -- refresh_thread_list empty branch ---------------------------------------


async def test_refresh_thread_list_empty_shows_hint(tmp_path: Path):
    app, _, _, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Default: pool has no threads → "No saved threads" Label
        labels = [str(lbl.render()) for lbl in app._thread_list_container.children if isinstance(lbl, Label)]
        assert any('No saved threads' in t for t in labels)


# -- unmount flushes pending writes -----------------------------------------


async def test_unmount_flushes_pending_writes(tmp_path: Path):
    app, _, _, _, tutor_store = _make_app(tmp_path)
    async with app.run_test() as pilot:
        app.on_explanation('raw', 'expl')
        await pilot.pause()
    # After the context manager exits, on_unmount has awaited the writes.
    assert [e.raw for e in tutor_store.load()] == ['raw']


# -- Static widget for streaming message -----------------------------------


async def test_streaming_label_updates_same_widget(tmp_path: Path):
    app, _, _, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        app._current_thread_id = 't-1'
        app._show_conversation_mode()
        app.on_thread_chunk('t-1', 'A')
        await pilot.pause()
        first = app._streaming_label
        app.on_thread_chunk('t-1', 'B')
        await pilot.pause()
        # Same widget instance, accumulated text
        assert app._streaming_label is first
        assert app._streaming_text == 'AB'


# -- on_button_pressed with non-matching id ---------------------------------


async def test_on_button_pressed_unknown_id_is_noop(tmp_path: Path):
    """A button without a tracked prefix should not raise."""
    app, _, queue, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        # Construct a Button event we can dispatch manually
        btn = Button('x', id='unknown-thing')
        # Mounting so .id is resolvable
        await app._status_bar.mount(btn)
        await pilot.pause()
        event = Button.Pressed(btn)
        app.on_button_pressed(event)
        await pilot.pause()
        assert queue.empty()


async def test_on_thread_list_called_via_public_method(tmp_path: Path):
    """Verify the public on_thread_list does NOT use the argument (bug magnet)."""
    meta = ThreadMeta(thread_id='t-x', anchor_raw='x', session_id='s', created_at='2026-04-18T00:00:00+00:00')
    app, pool, _, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Add to pool, then notify — the app reads list from pool, not the arg.
        pool._threads[meta.thread_id] = meta
        app.on_thread_list([])  # argument deliberately empty
        await pilot.pause()
        items = list(app.query(ThreadListItem).results(ThreadListItem))
        assert len(items) == 1


# -- sanity: Static is used for streaming ----------------------------------


async def test_apply_thread_done_without_prior_chunks_is_safe(tmp_path: Path):
    """thread_done with no streaming state should not raise."""
    app, _, _, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        app._current_thread_id = 't-1'
        app.on_thread_done('t-1', '')
        await pilot.pause()
        assert app._streaming_label is None
        assert app._streaming_text == ''


async def test_on_input_submitted_mounts_user_message(tmp_path: Path):
    app, _, queue, _, _ = _make_app(tmp_path)
    async with app.run_test() as pilot:
        app._current_thread_id = 't-1'
        app._show_conversation_mode()
        inp = app._thread_input
        inp.value = 'hello?'
        inp.post_message(Input.Submitted(inp, inp.value))
        await pilot.pause()
        _ = queue.get_nowait()
        user_statics = [s for s in app._thread_messages.children if isinstance(s, Static) and 'You:' in str(s.render())]
        assert len(user_statics) == 1
        assert 'hello?' in str(user_statics[0].render())
