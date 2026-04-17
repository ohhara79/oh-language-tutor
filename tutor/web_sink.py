"""Fan-out OutputSink for the web UI: renders Jinja2 partials and pushes them over SSE."""

from __future__ import annotations

import asyncio
import html
from typing import TYPE_CHECKING

from tutor.markdown_util import render_markdown
from tutor.types import TutorEntry

if TYPE_CHECKING:
    from typing import TextIO

    from jinja2 import Environment

    from tutor.tutor_store import TutorStore
    from tutor.types import ThreadMeta


# Per-subscriber queue bound. Drops rather than blocks the sink when a slow
# subscriber falls behind; the user will see a gap rather than the whole app
# wedging on one dead browser tab.
_SUBSCRIBER_QUEUE_MAX = 256


class WebSink:
    """OutputSink implementation that fans rendered HTML fragments to SSE subscribers."""

    def __init__(
        self,
        *,
        log: TextIO,
        tutor_store: TutorStore,
        env: Environment,
    ) -> None:
        self._log: TextIO = log
        self._tutor_store: TutorStore = tutor_store
        self._env: Environment = env
        self._subs: set[asyncio.Queue[tuple[str, str]]] = set()
        self._pending_writes: set[asyncio.Task[None]] = set()
        self._thread_list: list[ThreadMeta] = []

    # -- subscription ---------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[tuple[str, str]]:
        q: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAX)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[tuple[str, str]]) -> None:
        self._subs.discard(q)

    async def flush_pending_writes(self) -> None:
        """Await every outstanding TutorStore.append_async task."""
        if self._pending_writes:
            await asyncio.gather(*self._pending_writes, return_exceptions=True)

    def latest_thread_list(self) -> list[ThreadMeta]:
        """Return the cached thread list (as last broadcast)."""
        return list(self._thread_list)

    # -- OutputSink protocol --------------------------------------------------

    def on_raw_line(self, raw: str) -> None:
        self._log.write(raw + '\n')

    def on_explanation(self, raw: str, text: str) -> None:
        entry = TutorEntry(raw=raw, explanation=text)
        task = asyncio.create_task(self._tutor_store.append_async(entry))
        self._pending_writes.add(task)
        task.add_done_callback(self._pending_writes.discard)

        self._log.write(f'--- explanation for: {raw}\n{text}\n---\n')
        fragment = self._env.get_template('partials/line.html').render(
            entry=entry,
            threads=[],
            raw_escaped=html.escape(entry.raw),
            explanation_html=render_markdown(entry.explanation),
        )
        self._broadcast('explanation', fragment)

    def on_thread_chunk(self, thread_id: str, chunk: str) -> None:
        fragment = f'<span hx-swap-oob="beforeend:#msg-stream-{html.escape(thread_id)}">{html.escape(chunk)}</span>'
        self._broadcast('thread_chunk', fragment)

    def on_thread_done(self, thread_id: str, last_assistant: str) -> None:
        # Replace the streamed span container with a properly-rendered
        # .msg.assistant div. If there's no text (connect failure etc.) emit
        # an empty placeholder so the streamed ghost (if any) is still cleared.
        rendered = render_markdown(last_assistant) if last_assistant else ''
        fragment = (
            f'<div id="msg-stream-{html.escape(thread_id)}" '
            f'class="msg assistant" hx-swap-oob="outerHTML">{rendered}</div>'
        )
        self._broadcast('thread_done', fragment)

    def on_thread_list(self, threads: list[ThreadMeta]) -> None:
        self._thread_list = list(threads)
        fragment = self._env.get_template('partials/thread_list.html').render(threads=threads)
        self._broadcast('thread_list', fragment)

    def on_tutor_entry_removed(self, anchor_id: str) -> None:
        fragment = f'<div id="line-{html.escape(anchor_id)}" hx-swap-oob="delete"></div>'
        self._broadcast('tutor_entry_removed', fragment)

    def on_error(self, msg: str) -> None:
        self._log.write(f'[error] {msg}\n')
        fragment = self._env.get_template('partials/toast.html').render(message=msg)
        self._broadcast('error', fragment)

    # -- internal -------------------------------------------------------------

    def _broadcast(self, event: str, fragment: str) -> None:
        # SSE data: frames cannot contain raw newlines; strip them. It's safe
        # for HTML because whitespace between tags is not significant.
        payload = fragment.replace('\n', '').replace('\r', '')
        dead: list[asyncio.Queue[tuple[str, str]]] = []
        for q in self._subs:
            try:
                q.put_nowait((event, payload))
            except asyncio.QueueFull:
                self._log.write(f'[warn] dropping {event} for slow subscriber\n')
                dead.append(q)
        for q in dead:
            # A subscriber whose queue is full is almost certainly gone; drop it
            # so we don't keep logging the same overflow forever.
            self._subs.discard(q)
