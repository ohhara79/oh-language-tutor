"""Textual TUI for oh-language-tutor."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, override
from uuid import uuid4

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
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
from tutor.session import load_saved_session_id
from tutor.thread_pool import FollowupThreadPool
from tutor.thread_store import ThreadStore
from tutor.tutor_store import TutorStore
from tutor.types import (
    Cmd,
    DeleteThreadCmd,
    HideThreadCmd,
    OpenThreadCmd,
    ReopenThreadCmd,
    SendMessageCmd,
    ThreadMeta,
    TutorEntry,
)

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterable
    from typing import TextIO


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


class LineBlock(Horizontal):
    """Displays a raw input line with an [Ask] button."""

    def __init__(self, raw: str, tutor_pos: int) -> None:
        super().__init__()
        self._raw: str = raw
        self._tutor_pos: int = tutor_pos

    @property
    def tutor_pos(self) -> int:
        return self._tutor_pos

    @override
    def compose(self) -> ComposeResult:
        yield Label(self._raw, classes='line-raw')
        yield Button(
            'Ask',
            id=f'ask-{self._tutor_pos}',
            classes='ask-btn',
            variant='primary',
            tooltip='Ask a follow-up question about this line',
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
            f'{anchor_short}  ({msgs} msgs, {self._meta.created_at[:10]})',
            classes='thread-list-label',
        )
        yield Button('Open', id=f'reopen-{self._meta.thread_id}', classes='thread-open-btn', variant='primary')
        yield Button('Del', id=f'delete-{self._meta.thread_id}', classes='thread-delete-btn', variant='primary')


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
        self._tutor_count: int = 0
        self._session_log: TextIO | None = log
        self._tutor_store: TutorStore | None = tutor_store
        self._thread_store: ThreadStore | None = thread_store
        self._state_dir: Path | None = state_dir
        self._streaming_label: Static | None = None
        self._streaming_text: str = ''

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
        self._refresh_thread_list()
        self.query_one('#thread-messages', ScrollableContainer).display = False
        self.query_one('#thread-input', Input).display = False
        self._restore_tutor_entries()
        self.call_after_refresh(self._scroll_panes_to_end)

    def _scroll_panes_to_end(self) -> None:
        """Scroll both panes to the bottom after layout is computed."""
        self.query_one('#stream-pane', ScrollableContainer).scroll_end(animate=False)
        self.query_one('#thread-list-container', ScrollableContainer).scroll_end(animate=False)

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
        stream = self.query_one('#stream-pane', ScrollableContainer)
        for tutor_pos, entry in enumerate(entries):
            stream.mount(LineBlock(entry.raw, tutor_pos))
            stream.mount(ExplanationBlock(entry.explanation))
        self._tutor_count = len(entries)

    # -- OutputSink implementation --------------------------------------------

    def on_raw_line(self, raw: str) -> None:
        if self._session_log:
            self._session_log.write(raw + '\n')
        placeholder = self.query('#stream-placeholder')
        if placeholder:
            placeholder.first().remove()

    def on_explanation(self, raw: str, text: str) -> None:
        if self._session_log:
            self._session_log.write(f'--- explanation for: {raw}\n')
            self._session_log.write(text + '\n')
            self._session_log.write('---\n')
        stream = self.query_one('#stream-pane', ScrollableContainer)
        tutor_pos = self._tutor_count
        stream.mount(LineBlock(raw, tutor_pos))
        at_bottom = stream.is_vertical_scroll_end
        stream.mount(ExplanationBlock(text))
        if at_bottom:
            stream.scroll_end(animate=False)
        if self._tutor_store is not None:
            self._tutor_store.append(TutorEntry(raw=raw, explanation=text))
            self._tutor_count += 1

    def on_thread_chunk(self, thread_id: str, chunk: str) -> None:
        if thread_id != self._current_thread_id:
            return
        container = self.query_one('#thread-messages', ScrollableContainer)
        if self._streaming_label is None:
            self._streaming_label = Static('', classes='thread-msg')
            container.mount(self._streaming_label)
        self._streaming_text += chunk
        self._streaming_label.update(_rich_md(self._streaming_text))
        container.scroll_end(animate=False)

    def on_thread_done(self, thread_id: str) -> None:
        if thread_id == self._current_thread_id:
            # Re-render with markdown formatting now that the full text is available.
            if self._streaming_label is not None and self._streaming_text:
                self._streaming_label.update(_rich_md(self._streaming_text))
            self._streaming_label = None
            self._streaming_text = ''
            inp = self.query_one('#thread-input', Input)
            inp.disabled = False
            inp.focus()

    def on_thread_list(self, threads: list[ThreadMeta]) -> None:  # noqa: ARG002
        self._refresh_thread_list()

    def on_error(self, msg: str) -> None:
        self.query_one('#status-bar', Label).update(f'Error: {msg}')

    # -- button handlers ------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        # Clear the "-active" CSS class so the button is immediately
        # reusable.  Textual removes it via a short timer, but moving
        # focus away (e.g. to the thread input) can prevent that timer
        # from firing, leaving the button stuck in pressed state.
        event.button.remove_class('-active')

        btn_id = event.button.id or ''
        if btn_id.startswith('ask-'):
            tutor_pos = int(btn_id.removeprefix('ask-'))
            self._open_new_thread(anchor_idx=tutor_pos)
        elif btn_id.startswith('reopen-'):
            tid = btn_id.removeprefix('reopen-')
            self._reopen_thread(tid)
        elif btn_id.startswith('delete-'):
            tid = btn_id.removeprefix('delete-')
            self._cmd_queue.put_nowait(DeleteThreadCmd(thread_id=tid))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == 'thread-input' and self._current_thread_id:
            text = event.value.strip()
            if not text:
                return
            event.input.value = ''
            event.input.disabled = True
            container = self.query_one('#thread-messages', ScrollableContainer)
            container.mount(Static(f'You: {text}', classes='thread-msg thread-msg-user'))
            container.scroll_end(animate=False)
            self._cmd_queue.put_nowait(SendMessageCmd(thread_id=self._current_thread_id, text=text))

    # -- thread management ----------------------------------------------------

    def _scroll_left_pane_to_anchor(self, anchor_idx: int) -> None:
        if anchor_idx < 0:
            return
        stream = self.query_one('#stream-pane', ScrollableContainer)
        for block in stream.query(LineBlock):
            if block.tutor_pos == anchor_idx:
                stream.scroll_to_widget(block, animate=False)
                return

    def _open_new_thread(self, anchor_idx: int) -> None:
        if self._current_thread_id:
            self._cmd_queue.put_nowait(HideThreadCmd(thread_id=self._current_thread_id))

        tid = str(uuid4())[:8]
        self._current_thread_id = tid
        self._thread_view_mode = 'conversation'
        self._cmd_queue.put_nowait(OpenThreadCmd(thread_id=tid, anchor_idx=anchor_idx))

        entries = self._tutor_store.load() if self._tutor_store is not None else []
        anchor_text = entries[anchor_idx].raw if 0 <= anchor_idx < len(entries) else f'line {anchor_idx}'
        self._show_conversation_mode()
        container = self.query_one('#thread-messages', ScrollableContainer)
        container.remove_children()
        container.mount(Static(f'Thread opened for: {anchor_text}', classes='thread-msg thread-msg-dim'))
        self._streaming_label = None
        self._streaming_text = ''

        inp = self.query_one('#thread-input', Input)
        inp.disabled = False
        inp.value = ''
        inp.focus()
        self._scroll_left_pane_to_anchor(anchor_idx)

    def _reopen_thread(self, thread_id: str) -> None:
        if self._current_thread_id:
            self._cmd_queue.put_nowait(HideThreadCmd(thread_id=self._current_thread_id))

        self._current_thread_id = thread_id
        self._thread_view_mode = 'conversation'
        self._cmd_queue.put_nowait(ReopenThreadCmd(thread_id=thread_id))

        if self._pool is None:
            return
        meta = self._pool.load_thread_meta(thread_id)
        if meta is None:
            return

        self._show_conversation_mode()

        container = self.query_one('#thread-messages', ScrollableContainer)
        container.remove_children()
        container.mount(Static(f'Thread: {meta.anchor_raw}', classes='thread-msg thread-msg-dim'))
        for msg in meta.messages:
            if msg.role == 'user':
                container.mount(Static(f'You: {msg.text}', classes='thread-msg thread-msg-user'))
            else:
                container.mount(Static(_rich_md(msg.text), classes='thread-msg'))
        container.scroll_end(animate=False)
        self._streaming_label = None
        self._streaming_text = ''

        inp = self.query_one('#thread-input', Input)
        inp.disabled = False
        inp.value = ''
        inp.focus()
        self._scroll_left_pane_to_anchor(meta.anchor_idx)

    def action_export_html(self) -> None:
        if self._tutor_store is None or self._thread_store is None or self._state_dir is None:
            return
        out = self._state_dir / 'tutor.html'
        status = self.query_one('#status-bar', Label)
        try:
            export_to_html(self._tutor_store, self._thread_store, out)
        except OSError as exc:
            status.update(f'Export failed: {exc}')
            return
        status.update(f'Exported to {out}')

    def action_hide_thread(self) -> None:
        if self._current_thread_id:
            self._cmd_queue.put_nowait(HideThreadCmd(thread_id=self._current_thread_id))
            self._current_thread_id = None
        self._thread_view_mode = 'list'
        self._show_list_mode()
        self._refresh_thread_list()

    def _show_conversation_mode(self) -> None:
        self.query_one('#thread-list-container', ScrollableContainer).display = False
        self.query_one('#thread-messages', ScrollableContainer).display = True
        self.query_one('#thread-input', Input).display = True

    def _show_list_mode(self) -> None:
        self.query_one('#thread-list-container', ScrollableContainer).display = True
        self.query_one('#thread-messages', ScrollableContainer).display = False
        self.query_one('#thread-input', Input).display = False

    def _refresh_thread_list(self) -> None:
        container = self.query_one('#thread-list-container', ScrollableContainer)
        container.remove_children()
        if self._pool is None:
            return
        threads = self._pool.list_threads()
        if not threads:
            container.mount(Label('[dim]No saved threads yet.[/dim]'))
        else:
            for meta in threads:
                container.mount(ThreadListItem(meta))
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

                async with ClaudeSDKClient(options=options) as client:

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

                    stdin_task = asyncio.create_task(_run_stdin())
                    dispatch_task = asyncio.create_task(_run_dispatch())

                    try:
                        await app.run_async()
                    finally:
                        stop_event.set()
                        stdin_task.cancel()
                        dispatch_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await stdin_task
                        with contextlib.suppress(asyncio.CancelledError):
                            await dispatch_task
                        await pool.close_all()

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
                await pool.open_thread(cmd.thread_id, cmd.anchor_idx)
            case ReopenThreadCmd():
                await pool.reopen_thread(cmd.thread_id)
            case SendMessageCmd():
                await pool.send_message(cmd.thread_id, cmd.text)
            case HideThreadCmd():
                await pool.hide_thread(cmd.thread_id)
            case DeleteThreadCmd():
                await pool.delete_thread(cmd.thread_id)


# ---------------------------------------------------------------------------
# GUI entry point
# ---------------------------------------------------------------------------


async def run_gui(args: argparse.Namespace) -> int:
    """Launch the Textual TUI."""
    return await OhLanguageTutorApp.launch(args)
