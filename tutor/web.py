"""Web-mode entry point: FastAPI + HTMX + SSE over localhost."""

from __future__ import annotations

import asyncio
import contextlib
import io
import re
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, override

import uvicorn
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    StreamEvent,
    TextBlock,
)
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from tutor.core import stdin_loop
from tutor.markdown_util import render_markdown
from tutor.prompts import (
    EXPLAIN_CONTEXT_K,
    LEVELS,
    PromptTooLargeError,
    build_explain_user_message,
    build_system_prompt,
    read_extras_system_prompt,
)
from tutor.stream_util import text_delta
from tutor.thread_pool import FollowupThreadPool
from tutor.thread_store import ThreadStore, new_thread_id
from tutor.tutor_store import TutorStore
from tutor.types import ThreadMeta, TutorEntry, format_created_at_utc
from tutor.web_sink import WebSink

if TYPE_CHECKING:
    import argparse
    from collections.abc import AsyncIterator
    from typing import TextIO

_TEMPLATES_DIR = Path(__file__).parent / 'templates'
_STATIC_DIR = Path(__file__).parent / 'static'
# Cookie name used to remember which state dir the browser is currently
# viewing. Set by ``POST /commands/open_state_dir`` and read by every other
# route that needs to resolve a ``DirSession``.
VIEW_COOKIE = 'view_state_dir'


class LazyLog(io.TextIOBase):
    """Append-mode log writer that defers opening the file until first write.

    Browsing a tutor-data directory in the UI shouldn't dirty it on disk —
    so we wrap the per-dir ``tutor.log`` in this lazy adapter. The header
    line (``=== session start ... ===``) is buffered as the first thing to
    write, so it only lands on disk when something else needs to write
    too. ``flush`` and ``close`` are no-ops while unopened, so the
    shutdown path can call them unconditionally.
    """

    def __init__(self, path: Path, header: str) -> None:
        super().__init__()
        self._path: Path = path
        self._header: str = header
        self._fp: TextIO | None = None

    @property
    def opened(self) -> bool:
        return self._fp is not None

    def _ensure_open(self) -> TextIO:
        if self._fp is None:
            self._fp = self._path.open('a', encoding='utf-8', buffering=1)
            self._fp.write(self._header)
        return self._fp

    @override
    def write(self, s: str) -> int:
        return self._ensure_open().write(s)

    @override
    def flush(self) -> None:
        if self._fp is not None:
            self._fp.flush()

    @override
    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None
        super().close()


@dataclass
class DirSession:
    """Per-state-dir bundle: stores, sink, pool, and a lazy log handle.

    Each tutor-data directory the app touches gets its own ``DirSession``.
    The writing dir's session is created eagerly at startup; any additional
    dirs are materialized lazily the first time the user picks them. The
    log handle inside is also lazy — see :class:`LazyLog`.
    """

    state_dir: Path
    log: LazyLog
    tutor_store: TutorStore
    thread_store: ThreadStore
    sink: WebSink
    pool: FollowupThreadPool


@dataclass
class WebContext:
    """Shared runtime state for the web server.

    ``writing_session`` is bound at startup and never moves — stdin always
    writes there. ``sessions`` caches every ``DirSession`` materialized
    during the process lifetime; entries are reused on cookie revisits.
    """

    args: argparse.Namespace
    filter_re: re.Pattern[str] | None
    stop_event: asyncio.Event
    writing_dir: Path
    discovery_parent: Path
    sessions: dict[Path, DirSession]
    writing_session: DirSession
    extras_text: str | None  # appended to every per-request system prompt
    env: Environment
    version: str  # cache-buster for static assets


def _validate_audience(source_language: str, target_language: str, level: str) -> None:
    """Reject bad audience inputs from the request payload."""
    if not source_language.strip() or not target_language.strip():
        raise HTTPException(
            status_code=400,
            detail='source_language and target_language must be non-empty',
        )
    if level not in LEVELS:
        raise HTTPException(status_code=400, detail=f'invalid level: {level!r}')


def thread_heading(meta: ThreadMeta) -> str:
    """Pick the one-line heading shown for a thread in the thread list.

    Uses the thread's first user message, so threads sharing an anchor line are
    distinguishable. Falls back to ``anchor_raw`` for a just-opened thread that
    has not received a user message yet.
    """
    for m in meta.messages:
        if m.role == 'user':
            for line in m.text.splitlines():
                stripped = line.strip()
                if stripped:
                    return stripped
            break
    return meta.anchor_raw


def build_template_env() -> Environment:
    """Construct the Jinja2 environment used by both initial render and SSE fragments."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(enabled_extensions=('html',)),
    )
    globals_: dict[str, Any] = env.globals
    globals_['render_markdown'] = render_markdown
    globals_['format_created_at_utc'] = format_created_at_utc
    globals_['thread_heading'] = thread_heading
    return env


def list_state_dirs(parent: Path) -> list[Path]:
    """Return direct subdirectories of *parent*, sorted by name.

    Hidden dirs (leading ``.``) and non-directory entries are skipped. Any
    direct subdir is treated as a candidate tutor-data dir whether or not it
    already contains ``tutor.json`` — picking an empty dir is a legitimate
    way to start a fresh session.
    """
    if not parent.exists() or not parent.is_dir():
        return []
    return sorted(
        (p for p in parent.iterdir() if p.is_dir() and not p.name.startswith('.')),
        key=lambda p: p.name,
    )


def _make_lazy_log(state_dir: Path, args: argparse.Namespace) -> LazyLog:
    """Build a :class:`LazyLog` for ``state_dir/tutor.log`` (no file created yet)."""
    header = (
        f'\n=== session start explain_model={args.explain_model} '
        f'ask_model={args.ask_model} '
        f'bind={args.web_host}:{args.web_port} ===\n'
    )
    return LazyLog(state_dir / 'tutor.log', header)


def make_dir_session(state_dir: Path, args: argparse.Namespace, env: Environment) -> DirSession:
    """Create a fresh ``DirSession`` for *state_dir*, creating the dir if missing."""
    state_dir.mkdir(parents=True, exist_ok=True)
    log = _make_lazy_log(state_dir, args)
    tutor_store = TutorStore(state_dir / 'tutor.json')
    thread_store = ThreadStore(state_dir / 'threads')
    sink = WebSink(log=log, tutor_store=tutor_store, env=env)
    pool = FollowupThreadPool(
        model=args.ask_model,
        sink=sink,
        store=thread_store,
        tutor_store=tutor_store,
        log=log,
    )
    # Warm the sink's cached thread list so the first /events subscriber on
    # this dir sees it without waiting for a state change.
    sink.on_thread_list(pool.list_threads())
    return DirSession(
        state_dir=state_dir,
        log=log,
        tutor_store=tutor_store,
        thread_store=thread_store,
        sink=sink,
        pool=pool,
    )


def _get_or_create_session(ctx: WebContext, state_dir: Path) -> DirSession:
    """Return the cached ``DirSession`` for *state_dir*, creating one if needed."""
    key = state_dir.resolve()
    cached = ctx.sessions.get(key)
    if cached is not None:
        return cached
    session = make_dir_session(key, ctx.args, ctx.env)
    ctx.sessions[key] = session
    return session


def _resolve_view_session(ctx: WebContext, request: Request) -> DirSession | None:
    """Return the ``DirSession`` named by the view-state cookie, or ``None``.

    Defends against path traversal: the cookie value must be a plain basename
    matching a real direct subdir of ``ctx.discovery_parent``.
    """
    cookie_val = request.cookies.get(VIEW_COOKIE)
    if not cookie_val:
        return None
    if '/' in cookie_val or '\\' in cookie_val or cookie_val.startswith('.'):
        return None
    valid_names = {p.name for p in list_state_dirs(ctx.discovery_parent)}
    if cookie_val not in valid_names:
        return None
    return _get_or_create_session(ctx, ctx.discovery_parent / cookie_val)


async def _stream_explain(
    session: DirSession,
    args: argparse.Namespace,
    entry: TutorEntry,
    user_msg: str,
    options: ClaudeAgentOptions,
    *,
    source_language: str,
    target_language: str,
    level: str,
) -> None:
    """Run one short-lived Claude session, streaming chunks to the UI.

    Lives past the originating HTTP request so a client disconnect doesn't
    lose the in-progress explanation. On success, persists the explanation
    together with the audience under which it was produced (so subsequent
    Ask threads can reuse it) and broadcasts the finalized line. On
    failure, rolls the line back to its unexplained state via
    :meth:`WebSink.on_explain_aborted` so the user can retry.
    """
    _ = args  # currently unused; kept for symmetry with the call site
    buf: list[str] = []
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(user_msg)
            async for msg in client.receive_response():
                if isinstance(msg, StreamEvent):
                    delta = text_delta(msg)
                    if delta:
                        session.sink.on_explain_chunk(entry.id, delta)
                elif isinstance(msg, AssistantMessage):
                    buf.extend(b.text for b in msg.content if isinstance(b, TextBlock))
    except Exception as exc:  # noqa: BLE001
        session.sink.on_error(f'explain failed: {exc}')
        session.sink.on_explain_aborted(entry)
        return
    explanation = ''.join(buf).strip()
    if not explanation:
        session.sink.on_error('explain produced empty response')
        session.sink.on_explain_aborted(entry)
        return
    await session.tutor_store.update_explanation_async(
        entry.id,
        explanation,
        source_language=source_language,
        target_language=target_language,
        level=level,
    )
    updated = TutorEntry(
        raw=entry.raw,
        explanation=explanation,
        id=entry.id,
        source_language=source_language,
        target_language=target_language,
        level=level,
    )
    session.sink.on_entry_explained(updated)


def _require_view_session(ctx: WebContext, request: Request) -> DirSession:
    """Resolve the view session or raise 400 — for command/data routes.

    Page routes that should send the user back to the picker on a missing
    cookie should call ``_resolve_view_session`` directly and return a
    redirect; this helper is for routes that should never be hit without a
    cookie (POST commands, partials, SSE).
    """
    session = _resolve_view_session(ctx, request)
    if session is None:
        raise HTTPException(status_code=400, detail='no view state dir selected')
    return session


def build_app(ctx: WebContext) -> FastAPI:
    """Construct the FastAPI app with all routes closed over *ctx*."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.mount('/static', StaticFiles(directory=str(_STATIC_DIR)), name='static')

    @app.get('/', response_class=HTMLResponse)
    async def picker(request: Request) -> HTMLResponse:  # pyright: ignore[reportUnusedFunction]
        dirs = list_state_dirs(ctx.discovery_parent)
        current = request.cookies.get(VIEW_COOKIE) or ctx.writing_dir.name
        html_body = ctx.env.get_template('picker.html').render(
            dirs=[d.name for d in dirs],
            writing_dir=ctx.writing_dir.name,
            current_view=current,
            version=ctx.version,
        )
        return HTMLResponse(content=html_body)

    @app.post('/commands/open_state_dir')
    async def open_state_dir(  # pyright: ignore[reportUnusedFunction]
        dir_name: Annotated[str, Form()],
    ) -> Response:
        valid_names = {p.name for p in list_state_dirs(ctx.discovery_parent)}
        if dir_name not in valid_names:
            raise HTTPException(status_code=400, detail=f'unknown state dir: {dir_name!r}')
        response = RedirectResponse(url='/tutor', status_code=303)
        response.set_cookie(VIEW_COOKIE, dir_name, samesite='lax', httponly=False)
        return response

    @app.get('/tutor', response_class=HTMLResponse)
    async def index(request: Request) -> Response:  # pyright: ignore[reportUnusedFunction]
        session = _resolve_view_session(ctx, request)
        if session is None:
            return RedirectResponse(url='/', status_code=303)
        entries = session.tutor_store.load()
        threads = session.thread_store.list_threads()
        html_body = ctx.env.get_template('index.html').render(
            entries=entries,
            threads=threads,
            version=ctx.version,
            view_dir=session.state_dir.name,
        )
        return HTMLResponse(content=html_body)

    @app.get('/events')
    async def events(request: Request) -> StreamingResponse:  # pyright: ignore[reportUnusedFunction]
        session = _require_view_session(ctx, request)
        q = session.sink.subscribe()

        async def gen() -> AsyncIterator[bytes]:
            try:
                yield b': connected\n\n'
                # Push the current thread list immediately so new subscribers
                # don't have to wait for the next state change to render it.
                initial_threads = session.sink.latest_thread_list() or session.pool.list_threads()
                if initial_threads:
                    fragment = ctx.env.get_template('partials/thread_list.html').render(
                        threads=initial_threads,
                    )
                    fragment = fragment.replace('\n', '').replace('\r', '')
                    yield f'event: thread_list\ndata: {fragment}\n\n'.encode()
                while not ctx.stop_event.is_set():
                    if await request.is_disconnected():
                        break
                    try:
                        event, payload = await asyncio.wait_for(q.get(), timeout=15.0)
                    except TimeoutError:
                        yield b': ping\n\n'
                        continue
                    yield f'event: {event}\ndata: {payload}\n\n'.encode()
            finally:
                session.sink.unsubscribe(q)

        return StreamingResponse(
            gen(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            },
        )

    @app.get('/threads/{thread_id}', response_class=HTMLResponse)
    async def get_thread(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        thread_id: str,
    ) -> HTMLResponse:
        session = _require_view_session(ctx, request)
        meta = session.pool.peek_meta(thread_id)
        if meta is None:
            raise HTTPException(status_code=404, detail='thread not found')
        # Ensure the pool has this thread marked active so subsequent send_message
        # reuses session state.
        if thread_id not in session.pool._active:  # noqa: SLF001
            await session.pool.reopen_thread(thread_id)
        html_body = ctx.env.get_template('partials/thread_conversation.html').render(meta=meta)
        return HTMLResponse(content=html_body)

    @app.post('/commands/open_thread', response_class=HTMLResponse)
    async def open_thread(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        anchor_id: Annotated[str, Form()],
    ) -> HTMLResponse:
        session = _require_view_session(ctx, request)
        entry = next((e for e in session.tutor_store.load() if e.id == anchor_id), None)
        if entry is None:
            raise HTTPException(status_code=404, detail='entry not found')
        # Audience is frozen on the entry at Explain time. Legacy entries
        # written before this field existed fall back to the hardcoded
        # English/Korean/intermediate default so old streams stay openable.
        source_language = entry.source_language or 'English'
        target_language = entry.target_language or 'Korean'
        level = entry.level or 'intermediate'
        _validate_audience(source_language, target_language, level)
        thread_id = new_thread_id()
        await session.pool.open_thread(
            thread_id,
            anchor_id,
            source_language=source_language,
            target_language=target_language,
            level=level,
        )
        meta = session.pool.peek_meta(thread_id)
        if meta is None:
            raise HTTPException(status_code=500, detail='thread open failed')
        session.sink.on_thread_list(session.pool.list_threads())
        html_body = ctx.env.get_template('partials/thread_conversation.html').render(meta=meta)
        return HTMLResponse(content=html_body)

    @app.post('/commands/send_message', response_class=HTMLResponse)
    async def send_message(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        thread_id: Annotated[str, Form()],
        text: Annotated[str, Form()],
    ) -> HTMLResponse:
        session = _require_view_session(ctx, request)
        await session.pool.send_message(thread_id, text)
        html_body = ctx.env.get_template('partials/send_message_result.html').render(
            thread_id=thread_id,
            text=text,
        )
        return HTMLResponse(content=html_body)

    @app.post('/commands/hide_thread')
    async def hide_thread(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        thread_id: Annotated[str, Form()],
    ) -> Response:
        session = _require_view_session(ctx, request)
        await session.pool.hide_when_idle(thread_id)
        return Response(status_code=204)

    @app.post('/commands/delete_thread', response_class=HTMLResponse)
    async def delete_thread(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        thread_id: Annotated[str, Form()],
    ) -> HTMLResponse:
        session = _require_view_session(ctx, request)
        await session.pool.delete_thread(thread_id)
        return HTMLResponse(
            content=(
                '<p class="empty">Thread deleted.</p><div id="thread-topbar-actions" hx-swap-oob="innerHTML"></div>'
            ),
        )

    @app.post('/commands/delete_tutor_entry')
    async def delete_tutor_entry(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        anchor_id: Annotated[str, Form()],
    ) -> Response:
        session = _require_view_session(ctx, request)
        await session.pool.delete_tutor_entry(anchor_id)
        return Response(status_code=204)

    @app.post('/commands/clear_explanation')
    async def clear_explanation(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        anchor_id: Annotated[str, Form()],
    ) -> Response:
        session = _require_view_session(ctx, request)
        await session.pool.clear_tutor_entry_explanation(anchor_id)
        return Response(status_code=204)

    @app.post('/commands/explain', response_class=HTMLResponse)
    async def explain(  # pyright: ignore[reportUnusedFunction]
        request: Request,
        entry_id: Annotated[str, Form()],
        source_language: Annotated[str, Form()],
        target_language: Annotated[str, Form()],
        level: Annotated[str, Form()],
    ) -> HTMLResponse:
        session = _require_view_session(ctx, request)
        _validate_audience(source_language, target_language, level)
        entries = session.tutor_store.load()
        idx = next((i for i, e in enumerate(entries) if e.id == entry_id), -1)
        if idx < 0:
            raise HTTPException(status_code=404, detail='entry not found')
        target = entries[idx]
        if target.explanation is not None:
            return HTMLResponse(content=session.sink.render_line(target, active=True))
        try:
            system_prompt = build_system_prompt(
                source_language,
                target_language,
                level,
                ctx.extras_text,
            )
        except PromptTooLargeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=ctx.args.explain_model,
            allowed_tools=[],
            include_partial_messages=True,
        )
        context_raws = [e.raw for e in entries[max(0, idx - EXPLAIN_CONTEXT_K) : idx]]
        user_msg = build_explain_user_message(target.raw, context_raws)
        task = asyncio.create_task(
            _stream_explain(
                session,
                ctx.args,
                target,
                user_msg,
                options,
                source_language=source_language,
                target_language=target_language,
                level=level,
            ),
        )
        session.sink.track_explain(task)
        return HTMLResponse(content=session.sink.render_line(target, streaming=True))

    return app


def _uvicorn_log_config() -> dict[str, Any]:
    """Route uvicorn logs to stderr so stdout (where the user may tail their pipe) stays clean."""
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'default': {'format': '%(levelname)s: %(message)s'},
        },
        'handlers': {
            'default': {
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stderr',
                'formatter': 'default',
            },
        },
        'loggers': {
            'uvicorn': {'handlers': ['default'], 'level': 'WARNING', 'propagate': False},
            'uvicorn.error': {'handlers': ['default'], 'level': 'WARNING', 'propagate': False},
            'uvicorn.access': {'handlers': ['default'], 'level': 'WARNING', 'propagate': False},
        },
    }


async def _close_session(session: DirSession) -> None:
    """Flush and tear down one ``DirSession``'s resources.

    The end banner is written only when the lazy log was actually opened by
    some prior activity. Writing it unconditionally would force-open the
    file just to record the session end, defeating the laziness.
    """
    await session.pool.close_all()
    await session.sink.flush_pending_writes()
    if session.log.opened:
        session.log.write('=== session end ===\n')
    with contextlib.suppress(Exception):
        session.log.close()


async def run_web(args: argparse.Namespace) -> int:
    """Run the browser UI. Serves a FastAPI app on localhost."""
    try:
        filter_re = re.compile(args.filter_regex) if args.filter_regex else None
    except re.PatternError as exc:
        msg = f'oh-language-tutor: invalid --filter-regex: {exc}'
        raise SystemExit(msg) from exc

    extras_text = read_extras_system_prompt(args.extra_system_prompt) if args.extra_system_prompt else None

    writing_dir = Path(args.state_dir).expanduser().resolve()
    discovery_parent = writing_dir.parent

    stop_event = asyncio.Event()
    env = build_template_env()

    sessions: dict[Path, DirSession] = {}
    writing_session = make_dir_session(writing_dir, args, env)
    sessions[writing_dir] = writing_session

    ctx = WebContext(
        args=args,
        filter_re=filter_re,
        stop_event=stop_event,
        writing_dir=writing_dir,
        discovery_parent=discovery_parent,
        sessions=sessions,
        writing_session=writing_session,
        extras_text=extras_text,
        env=env,
        version=str(int(time.time())),
    )

    stdin_task = asyncio.create_task(
        stdin_loop(writing_session.sink, filter_re, stop_event),
    )

    app = build_app(ctx)
    config = uvicorn.Config(
        app,
        host=args.web_host,
        port=args.web_port,
        log_level='warning',
        access_log=False,
        log_config=_uvicorn_log_config(),
    )
    server = uvicorn.Server(config)
    # Disable uvicorn's own SIGINT/SIGTERM handlers so our handler below
    # drives shutdown; the attribute is present at runtime even though
    # basedpyright can't see it on Server's public API.
    server.install_signal_handlers = False  # pyright: ignore[reportAttributeAccessIssue]

    def _handle_sigint() -> None:
        stop_event.set()
        server.should_exit = True

    loop = asyncio.get_running_loop()
    with contextlib.suppress(NotImplementedError):
        loop.add_signal_handler(signal.SIGINT, _handle_sigint)

    sys.stderr.write(
        f'[oh-language-tutor] web UI at http://{args.web_host}:{args.web_port}\n',
    )

    try:
        await server.serve()
    finally:
        stop_event.set()
        stdin_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await stdin_task
        for session in list(ctx.sessions.values()):
            await _close_session(session)

    return 0
