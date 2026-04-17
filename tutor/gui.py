"""Textual TUI for oh-language-tutor."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast, override
from uuid import uuid4

from claude_agent_sdk import ClaudeAgentOptions
from markdown_it.token import Token
from rich.markdown import Markdown as RichMarkdown
from rich.theme import Theme
from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Input, Label, Static

from tutor.html_export import export_to_html
from tutor.markdown_util import emphasis_to_html
from tutor.prompts import build_system_prompt
from tutor.replay import connect_with_fallback
from tutor.session import load_saved_session_id
from tutor.thread_pool import FollowupThreadPool
from tutor.thread_store import ThreadStore
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
    format_created_at_utc,
)

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterable
    from typing import TextIO

    from textual.timer import Timer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MD_THEME = Theme(
    {
        'markdown.code': 'bold white',
        'markdown.code_block': 'white',
        'markdown.h2': 'bold underline white',
        'markdown.h3': 'bold white',
        'markdown.h4': 'italic white',
        'markdown.block_quote': 'italic white',
        'markdown.list': 'white',
        'markdown.item.number': 'bold white',
        'markdown.table.border': 'white',
        'markdown.table.header': 'bold white',
        'markdown.link': 'underline white',
        'markdown.strong': 'bold white',
        'markdown.emph': 'italic white',
    }
)


class _CJKMarkdown(RichMarkdown):
    """Markdown subclass with robust CJK emphasis handling.

    The emphasis preprocessor converts ``**text**`` / ``*text*`` to
    ``<strong>`` / ``<em>`` tags *before* markdown-it parses the text, so
    CommonMark's emphasis rules don't trip over CJK characters adjacent to
    the delimiters.  ``_flatten_tokens`` below then maps the resulting
    ``html_inline`` tokens back to strong/em tokens that Rich can style.
    """

    def __init__(self, markup: str, **kwargs: Any) -> None:
        super().__init__(emphasis_to_html(markup), **kwargs)

    @override
    def _flatten_tokens(self, tokens: Iterable[Token]) -> Iterable[Token]:  # type: ignore[override]
        _open: dict[str, str] = {'<strong>': 'strong', '<em>': 'em'}
        _close: dict[str, str] = {'</strong>': 'strong', '</em>': 'em'}
        for token in super()._flatten_tokens(tokens):
            if token.type != 'html_inline':
                yield token
                continue
            stripped = token.content.strip()
            if stripped in _open:
                tag = _open[stripped]
                yield Token(
                    type=f'{tag}_open',
                    tag=tag,
                    nesting=1,
                    attrs={},
                    map=None,
                    level=0,
                    children=None,
                    content='',
                    markup='**' if tag == 'strong' else '*',
                    info='',
                    meta={},
                    block=False,
                    hidden=False,
                )
            elif stripped in _close:
                tag = _close[stripped]
                yield Token(
                    type=f'{tag}_close',
                    tag=tag,
                    nesting=-1,
                    attrs={},
                    map=None,
                    level=0,
                    children=None,
                    content='',
                    markup='**' if tag == 'strong' else '*',
                    info='',
                    meta={},
                    block=False,
                    hidden=False,
                )
            else:
                yield token


def _rich_md(text: str) -> _CJKMarkdown:
    """Wrap text in a Rich Markdown renderable."""
    return _CJKMarkdown(text, style='white')


# ---------------------------------------------------------------------------
# Custom widgets
# ---------------------------------------------------------------------------


class _QuickButton(Button):
    """Button that skips the active-press animation.

    Textual's default Button adds the ``-active`` CSS class on every click,
    which triggers ``update_node_styles`` → ``stylesheet.update_nodes``.
    Setting ``active_effect_duration`` to zero avoids the extra style-update
    round-trips that stall the event loop in large DOMs.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.active_effect_duration: float = 0.0


class LineBlock(Horizontal):
    """Displays a raw input line with [Ask] and [Del] buttons."""

    def __init__(self, raw: str, tutor_id: str) -> None:
        super().__init__()
        self._raw: str = raw
        self._tutor_id: str = tutor_id

    @property
    def tutor_id(self) -> str:
        return self._tutor_id

    @property
    def raw(self) -> str:
        return self._raw

    @override
    def compose(self) -> ComposeResult:
        yield Label(self._raw, classes='line-raw')
        yield _QuickButton(
            'ASK',
            id=f'ask-{self._tutor_id}',
            classes='ask-btn',
            variant='primary',
        )
        yield _QuickButton(
            'DEL',
            id=f'line-delete-{self._tutor_id}',
            classes='line-delete-btn',
            variant='error',
        )


class ExplanationBlock(Static):
    """Displays an explanation for a line."""

    def __init__(self, text: str) -> None:
        super().__init__(_rich_md(text), classes='explanation')


class ThreadListItem(Horizontal):
    """One row in the thread list."""

    def __init__(self, meta: ThreadMeta) -> None:
        super().__init__()
        self._meta: ThreadMeta = meta

    @override
    def compose(self) -> ComposeResult:
        anchor_short = self._meta.anchor_raw[:60]
        msgs = len(self._meta.messages)
        yield Label(
            f'{anchor_short}  ({msgs} msgs, {format_created_at_utc(self._meta.created_at)})',
            classes='thread-list-label',
        )
        yield _QuickButton('OPEN', id=f'reopen-{self._meta.thread_id}', classes='thread-open-btn', variant='primary')
        yield _QuickButton('DEL', id=f'delete-{self._meta.thread_id}', classes='thread-delete-btn', variant='error')


# ---------------------------------------------------------------------------
# Main TUI app
# ---------------------------------------------------------------------------

_APP_CSS = """
#stream-pane {
    width: 60%;
    height: 100%;
    border-right: solid $accent;
}
#thread-pane {
    width: 40%;
    height: 100%;
}
LineBlock {
    height: auto;
}
.line-raw {
    color: $text-muted;
    margin-bottom: 0;
    width: 1fr;
}
.ask-btn {
    min-width: 6;
    margin: 0 1;
}
.line-delete-btn {
    min-width: 5;
    margin: 0 1;
}
.line-delete-btn.armed {
    background: $warning;
    color: $text;
}
.explanation {
    margin: 0 2 1 2;
    color: $text;
}
ThreadListItem {
    height: auto;
}
.thread-list-label {
    width: 1fr;
}
.thread-open-btn {
    min-width: 6;
    margin: 0 1;
}
.thread-delete-btn {
    min-width: 5;
    margin: 0 1;
}
.thread-delete-btn.armed {
    background: $warning;
    color: $text;
}
#thread-input {
    dock: bottom;
    margin: 1;
}
#thread-messages {
    height: 1fr;
}
.thread-msg {
    margin: 0 0 1 0;
}
.thread-msg-dim {
    color: $text-muted;
}
.thread-msg-user {
    color: $accent;
}
#thread-list-container {
    height: 1fr;
}
#status-bar {
    dock: bottom;
    height: 1;
    background: $accent;
    color: $text;
    padding: 0 1;
}
"""


class OhLanguageTutorApp(App['OhLanguageTutorApp']):
    """Interactive Textual TUI for oh-language-tutor."""

    CSS: ClassVar[str] = _APP_CSS
    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [  # pyright: ignore[reportIncompatibleVariableOverride]
        ('escape', 'hide_thread', 'Hide thread'),
        ('ctrl+e', 'export_html', 'Export HTML'),
        ('q', 'quit', 'Quit'),
    ]

    _current_thread_id: reactive[str | None] = reactive(None)
    _thread_view_mode: reactive[str] = reactive('list')  # 'list' | 'conversation'

    def __init__(
        self,
        *,
        pool: FollowupThreadPool | None,
        cmd_queue: asyncio.Queue[Cmd],
        log: TextIO | None = None,
        tutor_store: TutorStore | None = None,
        thread_store: ThreadStore | None = None,
        state_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self._pool: FollowupThreadPool | None = pool
        self._cmd_queue: asyncio.Queue[Cmd] = cmd_queue
        self._session_log: TextIO | None = log
        self._tutor_store: TutorStore | None = tutor_store
        self._thread_store: ThreadStore | None = thread_store
        self._state_dir: Path | None = state_dir
        self._streaming_label: Static | None = None
        self._streaming_text: str = ''
        self._pending_errors: list[str] = []
        self._delete_arming_id: str | None = None
        self._thread_delete_arming_id: str | None = None
        self._delete_arming_timer: Timer | None = None
        self._thread_delete_arming_timer: Timer | None = None
        self._line_blocks: dict[str, LineBlock] = {}
        self._pending_writes: set[asyncio.Task[None]] = set()
        # Hot widget references, populated in on_mount so click and
        # streaming handlers don't walk the ~3.7k-node DOM for each update.
        # Access before on_mount would raise AttributeError on .display etc.
        self._stream_pane: ScrollableContainer = cast('ScrollableContainer', None)
        self._thread_list_container: ScrollableContainer = cast('ScrollableContainer', None)
        self._thread_messages: ScrollableContainer = cast('ScrollableContainer', None)
        self._thread_input: Input = cast('Input', None)
        self._status_bar: Label = cast('Label', None)

    @override
    def compose(self) -> ComposeResult:
        yield Header(icon='*')
        with Horizontal():
            with ScrollableContainer(id='stream-pane'):
                yield Label('Waiting for input...', id='stream-placeholder')
            with Vertical(id='thread-pane'):
                with ScrollableContainer(id='thread-list-container'):
                    pass
                with ScrollableContainer(id='thread-messages'):
                    pass
                yield Input(placeholder='Ask a question...', id='thread-input')
        yield Label('Listening...', id='status-bar')
        yield Footer()

    def on_mount(self) -> None:
        """Load thread list and restore left-pane entries on startup."""
        self.console.push_theme(_MD_THEME)
        self._stream_pane = self.query_one('#stream-pane', ScrollableContainer)
        self._thread_list_container = self.query_one('#thread-list-container', ScrollableContainer)
        self._thread_messages = self.query_one('#thread-messages', ScrollableContainer)
        self._thread_input = self.query_one('#thread-input', Input)
        self._status_bar = self.query_one('#status-bar', Label)
        self._refresh_thread_list()
        self._thread_messages.display = False
        self._thread_input.display = False
        self._restore_tutor_entries()
        self.call_after_refresh(self._scroll_panes_to_end)
        if self._pending_errors:
            last = self._pending_errors[-1]
            self._pending_errors.clear()
            self._status_bar.update(f'Error: {last}')

    def _scroll_panes_to_end(self) -> None:
        """Scroll both panes to the bottom after layout is computed."""
        self._stream_pane.scroll_end(animate=False)
        self._thread_list_container.scroll_end(animate=False)

    async def on_unmount(self) -> None:
        """Await any outstanding async disk writes so nothing is lost on quit."""
        if self._pending_writes:
            await asyncio.gather(*self._pending_writes, return_exceptions=True)

    def _restore_tutor_entries(self) -> None:
        """Populate left pane from saved tutor.json entries."""
        if self._tutor_store is None:
            return
        entries = self._tutor_store.load()
        if not entries:
            return
        placeholder = self.query('#stream-placeholder')
        if placeholder:
            placeholder.first().remove()
        stream = self._stream_pane
        widgets: list[Any] = []
        for entry in entries:
            lb = LineBlock(entry.raw, entry.id)
            self._line_blocks[entry.id] = lb
            widgets.append(lb)
            widgets.append(ExplanationBlock(entry.explanation))
        stream.mount_all(widgets)

    # -- OutputSink implementation --------------------------------------------

    def on_raw_line(self, raw: str) -> None:
        if self._session_log:
            self._session_log.write(raw + '\n')
        self.call_later(self._apply_raw_line)

    def _apply_raw_line(self) -> None:
        placeholder = self.query('#stream-placeholder')
        if placeholder:
            placeholder.first().remove()

    def on_explanation(self, raw: str, text: str) -> None:
        if self._session_log:
            self._session_log.write(f'--- explanation for: {raw}\n')
            self._session_log.write(text + '\n')
            self._session_log.write('---\n')
        entry = TutorEntry(raw=raw, explanation=text)
        if self._tutor_store is not None:
            task = asyncio.create_task(self._tutor_store.append_async(entry))
            self._pending_writes.add(task)
            task.add_done_callback(self._pending_writes.discard)
        self.call_later(self._apply_explanation, raw, text, entry.id)

    def _apply_explanation(self, raw: str, text: str, entry_id: str) -> None:
        stream = self._stream_pane
        at_bottom = stream.is_vertical_scroll_end
        lb = LineBlock(raw, entry_id)
        self._line_blocks[entry_id] = lb
        stream.mount_all([lb, ExplanationBlock(text)])
        if at_bottom:
            stream.scroll_end(animate=False)

    def on_thread_chunk(self, thread_id: str, chunk: str) -> None:
        self.call_later(self._apply_thread_chunk, thread_id, chunk)

    def _apply_thread_chunk(self, thread_id: str, chunk: str) -> None:
        if thread_id != self._current_thread_id:
            return
        container = self._thread_messages
        if self._streaming_label is None:
            self._streaming_label = Static('', classes='thread-msg')
            container.mount(self._streaming_label)
        self._streaming_text += chunk
        # Plain-text during streaming; _apply_thread_done re-renders as
        # markdown once the reply completes. Avoids O(N²) markdown parses.
        self._streaming_label.update(self._streaming_text)
        container.scroll_end(animate=False)

    def on_thread_done(self, thread_id: str, last_assistant: str) -> None:  # noqa: ARG002
        self.call_later(self._apply_thread_done, thread_id)

    def _apply_thread_done(self, thread_id: str) -> None:
        if thread_id == self._current_thread_id:
            # Re-render with markdown formatting now that the full text is available.
            if self._streaming_label is not None and self._streaming_text:
                self._streaming_label.update(_rich_md(self._streaming_text))
            self._streaming_label = None
            self._streaming_text = ''
            inp = self._thread_input
            inp.disabled = False
            inp.focus()

    def on_thread_list(self, threads: list[ThreadMeta]) -> None:  # noqa: ARG002
        self.call_later(self._refresh_thread_list)

    def on_tutor_entry_removed(self, anchor_id: str) -> None:
        self.call_later(self._apply_tutor_entry_removed, anchor_id)

    def _apply_tutor_entry_removed(self, anchor_id: str) -> None:
        if not anchor_id:
            return
        if self._delete_arming_id == anchor_id:
            self._disarm_delete()
        block = self._line_blocks.pop(anchor_id, None)
        if block is None:
            return
        stream = self._stream_pane
        siblings = list(stream.children)
        try:
            pos = siblings.index(block)
        except ValueError:
            block.remove()
            return
        block.remove()
        if pos < len(siblings) - 1:
            explanation = siblings[pos + 1]
            if isinstance(explanation, ExplanationBlock):
                explanation.remove()

    def on_error(self, msg: str) -> None:
        if not self._screen_stack:
            self._pending_errors.append(msg)
            return
        self.call_later(self._apply_error, msg)

    def _apply_error(self, msg: str) -> None:
        self._status_bar.update(f'Error: {msg}')

    # -- button handlers ------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ''
        if btn_id.startswith('ask-'):
            anchor_id = btn_id.removeprefix('ask-')
            self._disarm_delete()
            self._disarm_thread_delete()
            parent = event.button.parent
            anchor_raw = parent.raw if isinstance(parent, LineBlock) else ''
            self._open_new_thread(anchor_id=anchor_id, anchor_raw=anchor_raw)
        elif btn_id.startswith('line-delete-'):
            anchor_id = btn_id.removeprefix('line-delete-')
            self._disarm_thread_delete()
            self._handle_line_delete_press(anchor_id, event.button)
        elif btn_id.startswith('reopen-'):
            tid = btn_id.removeprefix('reopen-')
            self._disarm_delete()
            self._disarm_thread_delete()
            self._reopen_thread(tid)
        elif btn_id.startswith('delete-'):
            tid = btn_id.removeprefix('delete-')
            self._disarm_delete()
            self._handle_thread_delete_press(tid, event.button)

    def _handle_line_delete_press(self, anchor_id: str, button: Button) -> None:
        if self._delete_arming_id == anchor_id:
            self._disarm_delete()
            self._cmd_queue.put_nowait(DeleteTutorEntryCmd(anchor_id=anchor_id))
            return
        self._disarm_delete()
        self._delete_arming_id = anchor_id
        button.label = 'CFM?'
        button.add_class('armed')
        self._delete_arming_timer = self.set_timer(3.0, lambda aid=anchor_id: self._disarm_delete_if(aid))

    def _disarm_delete_if(self, anchor_id: str) -> None:
        if self._delete_arming_id == anchor_id:
            self._disarm_delete()

    def _disarm_delete(self) -> None:
        if self._delete_arming_timer is not None:
            self._delete_arming_timer.stop()
            self._delete_arming_timer = None
        arming = self._delete_arming_id
        if arming is None:
            return
        self._delete_arming_id = None
        btns = self.query(f'#line-delete-{arming}').results(Button)
        for btn in btns:
            btn.label = 'DEL'
            btn.remove_class('armed')
            break

    def _handle_thread_delete_press(self, thread_id: str, button: Button) -> None:
        if self._thread_delete_arming_id == thread_id:
            self._disarm_thread_delete()
            self._cmd_queue.put_nowait(DeleteThreadCmd(thread_id=thread_id))
            return
        self._disarm_thread_delete()
        self._thread_delete_arming_id = thread_id
        button.label = 'CFM?'
        button.add_class('armed')
        self._thread_delete_arming_timer = self.set_timer(3.0, lambda tid=thread_id: self._disarm_thread_delete_if(tid))

    def _disarm_thread_delete_if(self, thread_id: str) -> None:
        if self._thread_delete_arming_id == thread_id:
            self._disarm_thread_delete()

    def _disarm_thread_delete(self) -> None:
        if self._thread_delete_arming_timer is not None:
            self._thread_delete_arming_timer.stop()
            self._thread_delete_arming_timer = None
        arming = self._thread_delete_arming_id
        if arming is None:
            return
        self._thread_delete_arming_id = None
        btns = self.query(f'#delete-{arming}').results(Button)
        for btn in btns:
            btn.label = 'DEL'
            btn.remove_class('armed')
            break

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == 'thread-input' and self._current_thread_id:
            text = event.value.strip()
            if not text:
                return
            event.input.value = ''
            event.input.disabled = True
            container = self._thread_messages
            container.mount(Static(f'You: {text}', classes='thread-msg thread-msg-user'))
            container.scroll_end(animate=False)
            self._cmd_queue.put_nowait(SendMessageCmd(thread_id=self._current_thread_id, text=text))

    # -- thread management ----------------------------------------------------

    def _scroll_left_pane_to_anchor_id(self, anchor_id: str) -> None:
        """Scroll the left pane so *anchor_id* is visible.

        The actual scroll is deferred via ``call_after_refresh`` so that
        ``scroll_to_widget`` runs after the next layout pass — otherwise it
        would force ``compositor.full_map`` to be rebuilt synchronously
        (``reflow_visible`` sets ``_full_map_invalidated``), which lays out
        every widget in the pane and stalls the event loop for ~1 s.
        """
        block = self._line_blocks.get(anchor_id)
        if block is not None:
            self.call_after_refresh(self._stream_pane.scroll_to_widget, block, animate=False)

    def _open_new_thread(self, anchor_id: str, anchor_raw: str = '') -> None:
        if self._current_thread_id:
            self._cmd_queue.put_nowait(HideThreadCmd(thread_id=self._current_thread_id))

        ts = datetime.now(UTC).strftime('%Y%m%d%H%M%S')
        tid = f'tutor_thread_{ts}_{uuid4().hex[:8]}'
        self._current_thread_id = tid
        self._thread_view_mode = 'conversation'
        self._cmd_queue.put_nowait(OpenThreadCmd(thread_id=tid, anchor_id=anchor_id))

        anchor_text = anchor_raw or f'line {anchor_id[:8]}'
        self._show_conversation_mode()
        container = self._thread_messages
        container.remove_children()
        container.mount(Static(f'Thread opened for: {anchor_text}', classes='thread-msg thread-msg-dim'))
        self._streaming_label = None
        self._streaming_text = ''

        inp = self._thread_input
        inp.disabled = False
        inp.value = ''
        inp.focus()
        self._scroll_left_pane_to_anchor_id(anchor_id)

    def _reopen_thread(self, thread_id: str) -> None:
        # Fast path: re-showing the already-active thread (e.g. after
        # Escape). The backend state is intact and the conversation
        # container already holds the messages — just unhide it.
        if self._current_thread_id == thread_id:
            self._thread_view_mode = 'conversation'
            self._show_conversation_mode()
            inp = self._thread_input
            if self._streaming_label is None:
                inp.disabled = False
            inp.focus()
            if self._pool is not None:
                meta = self._pool.peek_meta(thread_id)
                if meta is not None:
                    self._scroll_left_pane_to_anchor_id(meta.anchor_id)
            return

        if self._current_thread_id:
            self._cmd_queue.put_nowait(HideThreadCmd(thread_id=self._current_thread_id))

        self._current_thread_id = thread_id
        self._thread_view_mode = 'conversation'
        self._cmd_queue.put_nowait(ReopenThreadCmd(thread_id=thread_id))

        if self._pool is None:
            return
        meta = self._pool.peek_meta(thread_id)
        if meta is None:
            return

        self._show_conversation_mode()

        container = self._thread_messages
        container.remove_children()
        widgets: list[Any] = [Static(f'Thread: {meta.anchor_raw}', classes='thread-msg thread-msg-dim')]
        for msg in meta.messages:
            if msg.role == 'user':
                widgets.append(Static(f'You: {msg.text}', classes='thread-msg thread-msg-user'))
            else:
                widgets.append(Static(_rich_md(msg.text), classes='thread-msg'))
        container.mount_all(widgets)
        container.scroll_end(animate=False)
        self._streaming_label = None
        self._streaming_text = ''

        inp = self._thread_input
        inp.disabled = False
        inp.value = ''
        inp.focus()
        self._scroll_left_pane_to_anchor_id(meta.anchor_id)

    def action_export_html(self) -> None:
        if self._tutor_store is None or self._thread_store is None or self._state_dir is None:
            return
        out = self._state_dir / 'tutor.html'
        status = self._status_bar
        try:
            export_to_html(self._tutor_store, self._thread_store, out)
        except OSError as exc:
            status.update(f'Export failed: {exc}')
            return
        status.update(f'Exported to {out}')

    def action_hide_thread(self) -> None:
        # Toggle to the list view but keep the backend thread (and any
        # in-flight streaming task) alive. The user can return to the same
        # thread without losing an in-progress reply.
        self._thread_view_mode = 'list'
        self._show_list_mode()
        self._refresh_thread_list()

    def _show_conversation_mode(self) -> None:
        self._thread_list_container.display = False
        self._thread_messages.display = True
        self._thread_input.display = True

    def _show_list_mode(self) -> None:
        self._thread_list_container.display = True
        self._thread_messages.display = False
        self._thread_input.display = False

    def _refresh_thread_list(self) -> None:
        self._disarm_thread_delete()
        container = self._thread_list_container
        container.remove_children()
        if self._pool is None:
            return
        threads = self._pool.list_threads()
        if not threads:
            container.mount(Label('[dim]No saved threads yet.[/dim]'))
        else:
            container.mount_all([ThreadListItem(meta) for meta in threads])
            container.scroll_end(animate=False)

    # -- launch ---------------------------------------------------------------

    @staticmethod
    async def launch(args: argparse.Namespace) -> int:
        """Set up all components and run the TUI."""
        try:
            filter_re = re.compile(args.filter_regex) if args.filter_regex else None
        except re.PatternError as exc:
            msg = f'oh-language-tutor: invalid --filter-regex: {exc}'
            raise SystemExit(msg) from exc
        system_prompt = build_system_prompt(args)
        resume_id = load_saved_session_id(args)

        state_dir = Path(args.state_dir).expanduser()
        state_dir.mkdir(parents=True, exist_ok=True)
        log_path = state_dir / 'tutor.log'
        session_path = state_dir / 'session.id'

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=args.model,
            allowed_tools=[],
            resume=resume_id,
        )
        options_fresh = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=args.model,
            allowed_tools=[],
            resume=None,
        )

        stop_event = asyncio.Event()

        # When stdin is a pipe (e.g. ``scummvm | tutor --gui``), Textual
        # needs the real terminal on stdin for keyboard/mouse input.  Save
        # the piped fd and redirect stdin to /dev/tty so both can coexist.
        pipe_file = None
        if not sys.stdin.isatty():
            pipe_fd = os.dup(sys.stdin.fileno())
            pipe_file = os.fdopen(pipe_fd, 'r', encoding='utf-8', errors='replace')
            tty = open('/dev/tty', encoding='utf-8')  # noqa: ASYNC230, SIM115, PTH123
            os.dup2(tty.fileno(), sys.stdin.fileno())
            tty.close()

        try:
            with log_path.open('a', encoding='utf-8', buffering=1) as log:
                log.write(f'\n=== session start model={args.model} resume={resume_id or "-"} ===\n')

                store = ThreadStore(log_path.parent / 'threads')
                tutor_store = TutorStore(log_path.parent / 'tutor.json')
                cmd_queue: asyncio.Queue[Cmd] = asyncio.Queue()

                app = OhLanguageTutorApp(
                    pool=None,
                    cmd_queue=cmd_queue,
                    log=log,
                    tutor_store=tutor_store,
                    thread_store=store,
                    state_dir=state_dir,
                )

                pool = FollowupThreadPool(
                    model=args.model,
                    sink=app,
                    store=store,
                    tutor_store=tutor_store,
                    log=log,
                    source_language=args.source_language,
                    target_language=args.target_language,
                    level=args.level,
                )
                app._pool = pool

                from tutor.core import stdin_loop  # noqa: PLC0415

                client = await connect_with_fallback(
                    options,
                    fresh=options_fresh,
                    tutor_entries=tutor_store.load() if resume_id else [],
                    sink=app,
                    log=log,
                )
                try:

                    async def _run_stdin() -> None:
                        await stdin_loop(
                            client,
                            app,
                            filter_re,
                            stop_event,
                            session_path,
                            use_thread=True,
                            input_file=pipe_file,
                        )
                        stop_event.set()

                    async def _run_dispatch() -> None:
                        await _dispatch_commands(cmd_queue, pool, stop_event)

                    # Only read from stdin when a pipe is feeding us dialog.
                    # With no pipe, stdin is the tty and reading it would race
                    # with Textual's own input driver, dropping key/mouse events.
                    stdin_task = asyncio.create_task(_run_stdin()) if pipe_file is not None else None
                    dispatch_task = asyncio.create_task(_run_dispatch())

                    try:
                        await app.run_async()
                    finally:
                        stop_event.set()
                        if stdin_task is not None:
                            stdin_task.cancel()
                        dispatch_task.cancel()
                        if stdin_task is not None:
                            with contextlib.suppress(asyncio.CancelledError):
                                await stdin_task
                        with contextlib.suppress(asyncio.CancelledError):
                            await dispatch_task
                        await pool.close_all()
                finally:
                    await client.__aexit__(None, None, None)

                log.write('=== session end ===\n')
        finally:
            if pipe_file is not None:
                pipe_file.close()

        return 0


# ---------------------------------------------------------------------------
# GUI command dispatcher
# ---------------------------------------------------------------------------


async def _dispatch_commands(
    queue: asyncio.Queue[Cmd],
    pool: FollowupThreadPool,
    stop_event: asyncio.Event,
) -> None:
    """Read commands from the GUI and dispatch to the thread pool."""
    while not stop_event.is_set():
        try:
            cmd = await asyncio.wait_for(queue.get(), timeout=0.1)
        except TimeoutError:
            continue
        match cmd:
            case OpenThreadCmd():
                await pool.open_thread(cmd.thread_id, cmd.anchor_id)
            case ReopenThreadCmd():
                await pool.reopen_thread(cmd.thread_id)
            case SendMessageCmd():
                await pool.send_message(cmd.thread_id, cmd.text)
            case HideThreadCmd():
                await pool.hide_thread(cmd.thread_id)
            case DeleteThreadCmd():
                await pool.delete_thread(cmd.thread_id)
            case DeleteTutorEntryCmd():
                await pool.delete_tutor_entry(cmd.anchor_id)


# ---------------------------------------------------------------------------
# GUI entry point
# ---------------------------------------------------------------------------


async def run_gui(args: argparse.Namespace) -> int:
    """Launch the Textual TUI."""
    return await OhLanguageTutorApp.launch(args)
