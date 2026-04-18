"""Tests for ``tutor.tui._dispatch_commands``.

Pure asyncio; no Textual harness needed.
"""

from __future__ import annotations

import asyncio
from typing import Any

from tutor.tui import _dispatch_commands
from tutor.types import (
    DeleteThreadCmd,
    DeleteTutorEntryCmd,
    HideThreadCmd,
    OpenThreadCmd,
    ReopenThreadCmd,
    SendMessageCmd,
)


class _RecordingPool:
    """Captures every pool call for assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def open_thread(self, thread_id: str, anchor_id: str) -> None:
        self.calls.append(('open_thread', (thread_id, anchor_id)))

    async def reopen_thread(self, thread_id: str) -> None:
        self.calls.append(('reopen_thread', (thread_id,)))

    async def send_message(self, thread_id: str, text: str) -> None:
        self.calls.append(('send_message', (thread_id, text)))

    async def hide_thread(self, thread_id: str) -> None:
        self.calls.append(('hide_thread', (thread_id,)))

    async def delete_thread(self, thread_id: str) -> None:
        self.calls.append(('delete_thread', (thread_id,)))

    async def delete_tutor_entry(self, anchor_id: str) -> None:
        self.calls.append(('delete_tutor_entry', (anchor_id,)))


async def _run_once(pool: Any, queue: asyncio.Queue[Any]) -> None:
    """Run the dispatcher just long enough to drain the queue, then stop."""
    stop = asyncio.Event()
    task = asyncio.create_task(_dispatch_commands(queue, pool, stop))
    # Poll until the queue is empty, or abort after a hard cap.
    for _ in range(50):
        await asyncio.sleep(0.02)
        if queue.empty():
            break
    stop.set()
    await task


async def test_open_thread_cmd_dispatches():
    pool = _RecordingPool()
    q: asyncio.Queue[Any] = asyncio.Queue()
    q.put_nowait(OpenThreadCmd(thread_id='t-1', anchor_id='a-1'))
    await _run_once(pool, q)
    assert pool.calls == [('open_thread', ('t-1', 'a-1'))]


async def test_reopen_thread_cmd_dispatches():
    pool = _RecordingPool()
    q: asyncio.Queue[Any] = asyncio.Queue()
    q.put_nowait(ReopenThreadCmd(thread_id='t-2'))
    await _run_once(pool, q)
    assert pool.calls == [('reopen_thread', ('t-2',))]


async def test_send_message_cmd_dispatches():
    pool = _RecordingPool()
    q: asyncio.Queue[Any] = asyncio.Queue()
    q.put_nowait(SendMessageCmd(thread_id='t-3', text='hi'))
    await _run_once(pool, q)
    assert pool.calls == [('send_message', ('t-3', 'hi'))]


async def test_hide_thread_cmd_dispatches():
    pool = _RecordingPool()
    q: asyncio.Queue[Any] = asyncio.Queue()
    q.put_nowait(HideThreadCmd(thread_id='t-4'))
    await _run_once(pool, q)
    assert pool.calls == [('hide_thread', ('t-4',))]


async def test_delete_thread_cmd_dispatches():
    pool = _RecordingPool()
    q: asyncio.Queue[Any] = asyncio.Queue()
    q.put_nowait(DeleteThreadCmd(thread_id='t-5'))
    await _run_once(pool, q)
    assert pool.calls == [('delete_thread', ('t-5',))]


async def test_delete_tutor_entry_cmd_dispatches():
    pool = _RecordingPool()
    q: asyncio.Queue[Any] = asyncio.Queue()
    q.put_nowait(DeleteTutorEntryCmd(anchor_id='a-9'))
    await _run_once(pool, q)
    assert pool.calls == [('delete_tutor_entry', ('a-9',))]


async def test_multiple_commands_dispatched_in_order():
    pool = _RecordingPool()
    q: asyncio.Queue[Any] = asyncio.Queue()
    q.put_nowait(OpenThreadCmd(thread_id='t-1', anchor_id='a-1'))
    q.put_nowait(SendMessageCmd(thread_id='t-1', text='q'))
    q.put_nowait(HideThreadCmd(thread_id='t-1'))
    await _run_once(pool, q)
    assert [c[0] for c in pool.calls] == ['open_thread', 'send_message', 'hide_thread']


async def test_stop_event_exits_loop_on_empty_queue():
    """With no commands, the loop should exit shortly after stop_event is set."""
    pool = _RecordingPool()
    q: asyncio.Queue[Any] = asyncio.Queue()
    stop = asyncio.Event()
    task = asyncio.create_task(_dispatch_commands(q, pool, stop))  # pyright: ignore[reportArgumentType]
    # Give the loop a couple of poll cycles to hit the 0.1 s timeout branch
    await asyncio.sleep(0.25)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)
    assert pool.calls == []
