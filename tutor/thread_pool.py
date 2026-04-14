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
    TextBlock,
)

from tutor.prompts import build_thread_system_prompt
from tutor.replay import (
    REPLAY_MAX_TURNS,
    build_preamble,
    notify_fallback,
    pairs_from_thread,
)
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
        source_language: str,
        target_language: str,
        level: str,
    ) -> None:
        self._model: str = model
        self._sink: OutputSink = sink
        self._store: ThreadStore = store
        self._tutor_store: TutorStore = tutor_store
        self._log: TextIO = log
        self._source_language: str = source_language
        self._target_language: str = target_language
        self._level: str = level
        self._active: dict[str, _ActiveThread] = {}

    # -- public API -----------------------------------------------------------

    async def open_thread(self, thread_id: str, anchor_idx: int) -> None:
        """Create a new followup thread anchored to tutor.json entry *anchor_idx*.

        The anchor's ``raw`` and ``explanation`` are resolved by reading
        the ``TutorStore`` at that position — the single source of truth
        for explained lines, stable across restarts.

        The Claude API session is created lazily on the first
        ``send_message`` call so that rapid open/close cycles don't
        spin up (and potentially exhaust) API sessions.
        """
        entries = self._tutor_store.load()
        if not 0 <= anchor_idx < len(entries):
            self._sink.on_error(f'tutor entry {anchor_idx} not found')
            return
        entry = entries[anchor_idx]
        anchor = LineRecord(idx=-1, raw=entry.raw, explanation=entry.explanation)

        context_entries = entries[max(0, anchor_idx - 100):anchor_idx]
        context_lines = [
            LineRecord(idx=-1, raw=e.raw, explanation=e.explanation) for e in context_entries
        ]
        system_prompt = build_thread_system_prompt(
            self._source_language,
            self._target_language,
            self._level,
            anchor,
            context_lines,
        )
        now = datetime.datetime.now(tz=datetime.UTC).isoformat()
        meta = ThreadMeta(
            thread_id=thread_id,
            anchor_raw=anchor.raw,
            session_id=str(uuid4()),
            created_at=now,
            anchor_idx=anchor_idx,
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
        """Send a user message and stream the response."""
        at = self._active.get(thread_id)
        if at is None:
            self._sink.on_error(f'thread {thread_id} is not active')
            return

        # Lazily create the Claude API session on first message.
        if at.client is None:
            try:
                at.client = await self._connect(at.system_prompt, at.resume_session_id)
            except Exception as exc:  # noqa: BLE001
                if at.resume_session_id is None:
                    self._sink.on_error(f'failed to connect thread {thread_id}: {exc}')
                    return
                # Resume failed — start a fresh session and replay the thread's
                # prior turns as a preamble so Claude has context.
                try:
                    at.client = await self._connect('', None)
                except Exception as retry_exc:  # noqa: BLE001
                    self._sink.on_error(f'failed to connect thread {thread_id}: {retry_exc}')
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
                        return
                notify_fallback(self._log, self._sink, total=len(all_pairs), replayed=len(pairs))
                at.resume_session_id = None

        at.meta.messages.append(ThreadMessage(role='user', text=text))
        self._store.save_thread(at.meta)
        self._log.write(f'[user] {text}\n')

        at.task = asyncio.create_task(self._stream_response(at, text))
        at.task.add_done_callback(self._on_task_done)

    async def hide_thread(self, thread_id: str) -> None:
        """Disconnect the session but keep metadata on disk.

        If a response is still streaming, let it finish so the real
        ``session_id`` and the full reply are captured and saved.
        """
        at = self._active.pop(thread_id, None)
        if at is None:
            return
        if at.task and not at.task.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await at.task
        if at.client is not None:
            await self._disconnect(at.client)
        self._log.write(f'=== thread close thread_id={thread_id} ===\n')

    async def delete_thread(self, thread_id: str) -> None:
        """Disconnect and remove from disk permanently."""
        await self.hide_thread(thread_id)
        self._store.delete_thread(thread_id)
        self._sink.on_thread_list(self.list_threads())

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

    async def _stream_response(self, at: _ActiveThread, text: str) -> None:
        """Query Claude and stream the response to the sink."""
        if at.client is None:
            self._sink.on_error(f'thread {at.thread_id} has no active client')
            self._sink.on_thread_done(at.thread_id)
            return
        buf: list[str] = []
        try:
            await at.client.query(text)
            async for msg in at.client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            buf.append(block.text)
                            self._sink.on_thread_chunk(at.thread_id, block.text)
                elif isinstance(msg, ResultMessage):
                    at.meta.session_id = msg.session_id
        except Exception as exc:  # noqa: BLE001
            self._sink.on_error(f'thread query failed: {exc}')
            return
        finally:
            self._sink.on_thread_done(at.thread_id)

        response = ''.join(buf).strip()
        if response:
            at.meta.messages.append(ThreadMessage(role='assistant', text=response))
            self._store.save_thread(at.meta)
            self._log.write(f'[assistant] {response}\n')

    @staticmethod
    async def _disconnect(client: ClaudeSDKClient) -> None:
        with contextlib.suppress(Exception):
            await client.__aexit__(None, None, None)
