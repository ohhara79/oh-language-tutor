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
from tutor.types import ThreadMessage, ThreadMeta

if TYPE_CHECKING:
    from typing import TextIO

    from tutor.registry import LineRegistry
    from tutor.thread_store import ThreadStore
    from tutor.types import OutputSink


@dataclass(slots=True)
class _ActiveThread:
    """Runtime state for an open thread."""

    thread_id: str
    meta: ThreadMeta
    system_prompt: str
    client: ClaudeSDKClient | None = None
    task: asyncio.Task[None] | None = None


class FollowupThreadPool:
    """Manages side ``ClaudeSDKClient`` sessions with on-disk persistence."""

    def __init__(
        self,
        *,
        model: str,
        registry: LineRegistry,
        sink: OutputSink,
        store: ThreadStore,
        log: TextIO,
        source_language: str,
        target_language: str,
        level: str,
    ) -> None:
        self._model: str = model
        self._registry: LineRegistry = registry
        self._sink: OutputSink = sink
        self._store: ThreadStore = store
        self._log: TextIO = log
        self._source_language: str = source_language
        self._target_language: str = target_language
        self._level: str = level
        self._active: dict[str, _ActiveThread] = {}

    # -- public API -----------------------------------------------------------

    async def open_thread(self, thread_id: str, anchor_idx: int) -> None:
        """Create a new followup thread anchored to *anchor_idx*.

        The Claude API session is created lazily on the first
        ``send_message`` call so that rapid open/close cycles don't
        spin up (and potentially exhaust) API sessions.
        """
        anchor = self._registry.get(anchor_idx)
        if anchor is None:
            self._sink.on_error(f'line {anchor_idx} not found in registry')
            return

        context_lines = self._registry.recent(100)
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
        )
        self._active[thread_id] = _ActiveThread(
            thread_id=thread_id,
            meta=meta,
            system_prompt=system_prompt,
        )
        self._log.write(f'=== thread open anchor_raw="{anchor.raw}" thread_id={thread_id} ===\n')

    async def reopen_thread(self, thread_id: str) -> None:
        """Reopen a previously saved thread, resuming the Claude session."""
        meta = self._store.load_thread(thread_id)
        if meta is None:
            self._sink.on_error(f'thread {thread_id} not found on disk')
            return

        options = ClaudeAgentOptions(
            system_prompt='',
            model=self._model,
            allowed_tools=[],
            resume=meta.session_id,
        )
        try:
            client = ClaudeSDKClient(options=options)
            await client.__aenter__()
            self._active[thread_id] = _ActiveThread(
                thread_id=thread_id,
                meta=meta,
                system_prompt='',
                client=client,
            )
            self._log.write(f'=== thread reopen thread_id={thread_id} ===\n')
        except Exception as exc:  # noqa: BLE001
            self._sink.on_error(f'session expired for thread {thread_id}: {exc}')
            return

    async def send_message(self, thread_id: str, text: str) -> None:
        """Send a user message and stream the response."""
        at = self._active.get(thread_id)
        if at is None:
            self._sink.on_error(f'thread {thread_id} is not active')
            return

        # Lazily create the Claude API session on first message.
        if at.client is None:
            try:
                at.client = await self._connect(at.system_prompt)
            except Exception as exc:  # noqa: BLE001
                self._sink.on_error(f'failed to connect thread {thread_id}: {exc}')
                return

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

    async def _connect(self, system_prompt: str) -> ClaudeSDKClient:
        """Create and enter a new Claude API session."""
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=self._model,
            allowed_tools=[],
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
