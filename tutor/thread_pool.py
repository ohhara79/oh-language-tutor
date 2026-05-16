"""Followup thread pool: manages side ClaudeSDKClient sessions."""

from __future__ import annotations

import asyncio
import contextlib
import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
    TextBlock,
)

from tutor.prompts import build_thread_system_prompt
from tutor.replay import (
    REPLAY_MAX_TURNS,
    build_preamble,
    notify_fallback,
    pairs_from_thread,
)
from tutor.stream_util import text_delta
from tutor.types import LineRecord, ThreadMessage, ThreadMeta

if TYPE_CHECKING:
    from typing import TextIO

    from tutor.thread_store import ThreadStore
    from tutor.tutor_store import TutorStore
    from tutor.types import OutputSink


@dataclass(slots=True)
class _ActiveThread:
    """Runtime state for an open thread."""

    thread_id: str
    meta: ThreadMeta
    system_prompt: str
    client: ClaudeSDKClient | None = None
    task: asyncio.Task[None] | None = None
    resume_session_id: str | None = None
    hide_pending: bool = False


class FollowupThreadPool:
    """Manages side ``ClaudeSDKClient`` sessions with on-disk persistence."""

    def __init__(
        self,
        *,
        model: str,
        sink: OutputSink,
        store: ThreadStore,
        tutor_store: TutorStore,
        log: TextIO,
    ) -> None:
        self._model: str = model
        self._sink: OutputSink = sink
        self._store: ThreadStore = store
        self._tutor_store: TutorStore = tutor_store
        self._log: TextIO = log
        self._active: dict[str, _ActiveThread] = {}

    # -- public API -----------------------------------------------------------

    async def open_thread(
        self,
        thread_id: str,
        anchor_id: str,
        *,
        source_language: str,
        target_language: str,
        level: str,
    ) -> None:
        """Create a new followup thread anchored to tutor entry *anchor_id*.

        The anchor's ``raw`` and ``explanation`` are resolved by reading
        the ``TutorStore`` — the single source of truth for explained lines,
        stable across restarts. The current array position is derived from
        the id so the 100-line context window reflects the live file.

        The Claude API session is created lazily on the first
        ``send_message`` call so that rapid open/close cycles don't
        spin up (and potentially exhaust) API sessions.
        """
        entries = self._tutor_store.load()
        anchor_idx = next((i for i, e in enumerate(entries) if e.id == anchor_id), -1)
        if anchor_idx < 0:
            self._sink.on_error(f'tutor entry {anchor_id} not found')
            return
        entry = entries[anchor_idx]
        anchor = LineRecord(idx=-1, raw=entry.raw, explanation=entry.explanation)

        context_entries = entries[max(0, anchor_idx - 100) : anchor_idx]
        context_lines = [LineRecord(idx=-1, raw=e.raw, explanation=e.explanation) for e in context_entries]
        system_prompt = build_thread_system_prompt(
            source_language,
            target_language,
            level,
            anchor,
            context_lines,
        )
        now = datetime.datetime.now(tz=datetime.UTC).isoformat()
        meta = ThreadMeta(
            thread_id=thread_id,
            anchor_raw=anchor.raw,
            session_id=str(uuid4()),
            created_at=now,
            anchor_id=anchor_id,
        )
        self._active[thread_id] = _ActiveThread(
            thread_id=thread_id,
            meta=meta,
            system_prompt=system_prompt,
        )
        self._log.write(f'=== thread open anchor_raw="{anchor.raw}" thread_id={thread_id} ===\n')

    async def reopen_thread(self, thread_id: str) -> None:
        """Reopen a previously saved thread.

        The Claude API session is resumed lazily on the first
        ``send_message`` call so that viewing thread contents doesn't
        spawn a CLI subprocess.
        """
        meta = self._store.load_thread(thread_id)
        if meta is None:
            self._sink.on_error(f'thread {thread_id} not found on disk')
            return
        self._active[thread_id] = _ActiveThread(
            thread_id=thread_id,
            meta=meta,
            system_prompt='',
            resume_session_id=meta.session_id,
        )
        self._log.write(f'=== thread reopen thread_id={thread_id} ===\n')

    async def send_message(self, thread_id: str, text: str) -> None:
        """Schedule a user message and its streamed response.

        Returns as soon as the stream task is spawned so the dispatcher
        (``_dispatch_commands``) never blocks on a slow or stuck stream.
        Per-thread serialization (no concurrent ``client.query()`` on the
        same session) is enforced *inside* the new task by awaiting the
        prior ``at.task`` before issuing its own query.
        """
        at = self._active.get(thread_id)
        if at is None:
            self._sink.on_error(f'thread {thread_id} is not active')
            return
        # A new message re-engages the thread, so any pending idle-hide is
        # cancelled.
        at.hide_pending = False
        prev_task = at.task
        at.task = asyncio.create_task(self._stream_response(at, text, prev_task))
        at.task.add_done_callback(self._on_task_done)

    async def hide_thread(self, thread_id: str) -> None:
        """Disconnect the session but keep metadata on disk.

        Give the in-flight task up to 2 s to finish cleanly so its final
        reply and ``session_id`` land; if it's stuck, cancel it. The
        ``_stream_response`` ``finally`` block tolerates ``CancelledError``
        and still persists whatever was buffered.
        """
        at = self._active.pop(thread_id, None)
        if at is None:
            return
        if at.task and not at.task.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                try:
                    await asyncio.wait_for(asyncio.shield(at.task), timeout=2.0)
                except TimeoutError:
                    at.task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await at.task
        if at.client is not None:
            await self._disconnect(at.client)
        self._log.write(f'=== thread close thread_id={thread_id} ===\n')

    async def hide_when_idle(self, thread_id: str) -> None:
        """Disconnect the thread now if idle, else after the in-flight reply lands.

        ``hide_thread`` cancels an in-flight stream after a 2 s grace; that's
        appropriate when we *must* close (delete, shutdown). For routine
        navigation away from a thread we'd rather wait for the reply to
        finish naturally — the ``_stream_response`` ``finally`` block sees
        ``hide_pending`` and tears down the subprocess after persisting the
        reply.
        """
        at = self._active.get(thread_id)
        if at is None:
            return
        if at.task is None or at.task.done():
            await self.hide_thread(thread_id)
            return
        at.hide_pending = True

    async def delete_thread(self, thread_id: str) -> None:
        """Disconnect and remove from disk permanently."""
        await self.hide_thread(thread_id)
        self._store.delete_thread(thread_id)
        self._sink.on_thread_list(self.list_threads())

    async def delete_tutor_entry(self, anchor_id: str) -> None:
        """Remove a tutor entry and cascade-delete every thread anchored to it."""
        if not anchor_id:
            return
        active_to_close = [tid for tid, at in self._active.items() if at.meta.anchor_id == anchor_id]
        for tid in active_to_close:
            await self.hide_thread(tid)
        self._store.delete_by_anchor_id(anchor_id)
        await self._tutor_store.delete_async(anchor_id)
        self._sink.on_thread_list(self.list_threads())
        self._sink.on_tutor_entry_removed(anchor_id)

    async def close_all(self) -> None:
        """Disconnect all active threads on shutdown."""
        for tid in list(self._active):
            await self.hide_thread(tid)

    def list_threads(self) -> list[ThreadMeta]:
        """Return all saved threads (delegates to store)."""
        return self._store.list_threads()

    def load_thread_meta(self, thread_id: str) -> ThreadMeta | None:
        """Load a single thread's metadata from disk."""
        return self._store.load_thread(thread_id)

    def peek_meta(self, thread_id: str) -> ThreadMeta | None:
        """Return the in-memory meta if the thread is active, else load from disk.

        In-memory meta reflects messages appended by an in-flight task before
        its reply has been flushed, so the TUI can render up-to-date state
        when switching back into a thread whose response is still streaming.
        """
        at = self._active.get(thread_id)
        if at is not None:
            return at.meta
        return self._store.load_thread(thread_id)

    # -- internal -------------------------------------------------------------

    async def _connect(
        self,
        system_prompt: str,
        resume_session_id: str | None = None,
    ) -> ClaudeSDKClient:
        """Create and enter a new Claude API session.

        If *resume_session_id* is provided, resume that session instead of
        starting a fresh one from *system_prompt*.
        """
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=self._model,
            allowed_tools=[],
            resume=resume_session_id,
            include_partial_messages=True,
        )
        client = ClaudeSDKClient(options=options)
        await client.__aenter__()
        return client

    def _on_task_done(self, task: asyncio.Task[None]) -> None:
        """Log any unexpected exception from a fire-and-forget stream task."""
        if not task.cancelled():
            exc = task.exception()
            if exc is not None:
                self._sink.on_error(f'thread task failed: {exc}')

    async def _stream_response(
        self,
        at: _ActiveThread,
        text: str,
        prev_task: asyncio.Task[None] | None,
    ) -> None:
        """Wait for any prior reply on this thread, then query and stream.

        Running the serialization wait inside the task (instead of in
        ``send_message``) keeps the command dispatcher free; a stuck
        upstream reply can no longer block unrelated commands.
        """
        if prev_task is not None and not prev_task.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await prev_task

        if at.client is None:
            try:
                at.client = await self._connect(at.system_prompt, at.resume_session_id)
            except Exception as exc:  # noqa: BLE001
                if at.resume_session_id is None:
                    self._sink.on_error(f'failed to connect thread {at.thread_id}: {exc}')
                    self._sink.on_thread_list(self._store.list_threads())
                    self._sink.on_thread_done(at.thread_id, '')
                    return
                # Resume failed — start a fresh session and replay the thread's
                # prior turns as a preamble so Claude has context.
                try:
                    at.client = await self._connect('', None)
                except Exception as retry_exc:  # noqa: BLE001
                    self._sink.on_error(f'failed to connect thread {at.thread_id}: {retry_exc}')
                    self._sink.on_thread_list(self._store.list_threads())
                    self._sink.on_thread_done(at.thread_id, '')
                    return
                all_pairs = pairs_from_thread(at.meta.messages)
                pairs = all_pairs[-REPLAY_MAX_TURNS:]
                if pairs:
                    try:
                        await at.client.query(build_preamble(pairs))
                        async for _ in at.client.receive_response():
                            pass
                    except Exception as seed_exc:  # noqa: BLE001
                        self._sink.on_error(f'thread replay failed: {seed_exc}')
                        self._sink.on_thread_list(self._store.list_threads())
                        self._sink.on_thread_done(at.thread_id, '')
                        return
                notify_fallback(self._log, self._sink, total=len(all_pairs), replayed=len(pairs))
                at.resume_session_id = None

        at.meta.messages.append(ThreadMessage(role='user', text=text))
        await self._store.save_thread_async(at.meta)
        self._log.write(f'[user] {text}\n')
        self._sink.on_thread_list(self._store.list_threads())

        buf: list[str] = []
        try:
            await at.client.query(text)
            async for msg in at.client.receive_response():
                if isinstance(msg, StreamEvent):
                    delta = text_delta(msg)
                    if delta:
                        self._sink.on_thread_chunk(at.thread_id, delta)
                elif isinstance(msg, AssistantMessage):
                    buf.extend(b.text for b in msg.content if isinstance(b, TextBlock))
                elif isinstance(msg, ResultMessage):
                    at.meta.session_id = msg.session_id
        except Exception as exc:  # noqa: BLE001
            self._sink.on_error(f'thread query failed: {exc}')
        finally:
            # Persist whatever was accumulated even on CancelledError — otherwise
            # an app shutdown mid-stream leaves the user message on disk with no
            # matching assistant reply.
            response = ''.join(buf).strip()
            if response:
                at.meta.messages.append(ThreadMessage(role='assistant', text=response))
                await self._store.save_thread_async(at.meta)
                self._log.write(f'[assistant] {response}\n')
                self._sink.on_thread_list(self._store.list_threads())
            self._sink.on_thread_done(at.thread_id, response)
            if at.hide_pending:
                # User navigated away while we were streaming. Now that the
                # reply has landed, drop the entry and tear down the subprocess.
                # Disconnecting from inside the task itself (vs. via
                # hide_thread) avoids an asyncio.shield(at.task) self-deadlock.
                # ``at.client`` may still be None if the connect attempt above
                # failed before assigning — guard explicitly so the disconnect
                # is skipped in that case.
                self._active.pop(at.thread_id, None)
                at.hide_pending = False
                # Early-return paths above (e.g. failed initial connect) can
                # land here with at.client still None; basedpyright doesn't
                # see those paths because its narrowing is taken from the
                # successful query branch.
                if at.client is not None:  # pyright: ignore[reportUnnecessaryComparison]
                    client_to_close = at.client
                    at.client = None
                    await self._disconnect(client_to_close)
                self._log.write(f'=== thread close (deferred) thread_id={at.thread_id} ===\n')

    @staticmethod
    async def _disconnect(client: ClaudeSDKClient) -> None:
        with contextlib.suppress(Exception):
            await client.__aexit__(None, None, None)
