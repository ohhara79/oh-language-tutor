"""Web-mode entry point: FastAPI + HTMX + SSE over localhost."""

from __future__ import annotations

import asyncio
import contextlib
import re
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import uvicorn
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    StreamEvent,
    TextBlock,
)
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
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
_STREAM_PAGE_N = 500


@dataclass
class WebContext:
    """Shared runtime state for the web server."""

    args: argparse.Namespace
    log: TextIO
    filter_re: re.Pattern[str] | None
    stop_event: asyncio.Event
    tutor_store: TutorStore
    thread_store: ThreadStore
    sink: WebSink
    pool: FollowupThreadPool
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


async def _stream_explain(
    ctx: WebContext,
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
    buf: list[str] = []
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(user_msg)
            async for msg in client.receive_response():
                if isinstance(msg, StreamEvent):
                    delta = text_delta(msg)
                    if delta:
                        ctx.sink.on_explain_chunk(entry.id, delta)
                elif isinstance(msg, AssistantMessage):
                    buf.extend(b.text for b in msg.content if isinstance(b, TextBlock))
    except Exception as exc:  # noqa: BLE001
        ctx.sink.on_error(f'explain failed: {exc}')
        ctx.sink.on_explain_aborted(entry)
        return
    explanation = ''.join(buf).strip()
    if not explanation:
        ctx.sink.on_error('explain produced empty response')
        ctx.sink.on_explain_aborted(entry)
        return
    await ctx.tutor_store.update_explanation_async(
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
    ctx.sink.on_entry_explained(updated)


def build_app(ctx: WebContext) -> FastAPI:
    """Construct the FastAPI app with all routes closed over *ctx*."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.mount('/static', StaticFiles(directory=str(_STATIC_DIR)), name='static')

    @app.get('/', response_class=HTMLResponse)
    async def index() -> HTMLResponse:  # pyright: ignore[reportUnusedFunction]
        entries, has_more = ctx.tutor_store.load_tail(_STREAM_PAGE_N)
        oldest_id = entries[0].id if entries else None
        threads = ctx.thread_store.list_threads()
        html_body = ctx.env.get_template('index.html').render(
            entries=entries,
            has_more=has_more,
            oldest_id=oldest_id,
            page_n=_STREAM_PAGE_N,
            threads=threads,
            version=ctx.version,
        )
        return HTMLResponse(content=html_body)

    @app.get('/partials/older', response_class=HTMLResponse)
    async def older(  # pyright: ignore[reportUnusedFunction]
        before: str,
        n: int = _STREAM_PAGE_N,
    ) -> HTMLResponse:
        result = ctx.tutor_store.load_before(before, n)
        if result is None:
            raise HTTPException(status_code=404, detail='cursor not found')
        older_entries, has_more = result
        new_oldest_id = older_entries[0].id if older_entries else before
        html_body = ctx.env.get_template('partials/older_lines.html').render(
            entries=older_entries,
            has_more=has_more,
            oldest_id=new_oldest_id,
            page_n=n,
        )
        return HTMLResponse(content=html_body)

    @app.get('/events')
    async def events(request: Request) -> StreamingResponse:  # pyright: ignore[reportUnusedFunction]
        q = ctx.sink.subscribe()

        async def gen() -> AsyncIterator[bytes]:
            try:
                yield b': connected\n\n'
                # Push the current thread list immediately so new subscribers
                # don't have to wait for the next state change to render it.
                initial_threads = ctx.sink.latest_thread_list() or ctx.pool.list_threads()
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
                ctx.sink.unsubscribe(q)

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
    async def get_thread(thread_id: str) -> HTMLResponse:  # pyright: ignore[reportUnusedFunction]
        meta = ctx.pool.peek_meta(thread_id)
        if meta is None:
            raise HTTPException(status_code=404, detail='thread not found')
        # Ensure the pool has this thread marked active so subsequent send_message
        # reuses session state.
        if thread_id not in ctx.pool._active:  # noqa: SLF001
            await ctx.pool.reopen_thread(thread_id)
        html_body = ctx.env.get_template('partials/thread_conversation.html').render(meta=meta)
        return HTMLResponse(content=html_body)

    @app.post('/commands/open_thread', response_class=HTMLResponse)
    async def open_thread(  # pyright: ignore[reportUnusedFunction]
        anchor_id: Annotated[str, Form()],
    ) -> HTMLResponse:
        entry = next((e for e in ctx.tutor_store.load() if e.id == anchor_id), None)
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
        await ctx.pool.open_thread(
            thread_id,
            anchor_id,
            source_language=source_language,
            target_language=target_language,
            level=level,
        )
        meta = ctx.pool.peek_meta(thread_id)
        if meta is None:
            raise HTTPException(status_code=500, detail='thread open failed')
        ctx.sink.on_thread_list(ctx.pool.list_threads())
        html_body = ctx.env.get_template('partials/thread_conversation.html').render(meta=meta)
        return HTMLResponse(content=html_body)

    @app.post('/commands/send_message', response_class=HTMLResponse)
    async def send_message(  # pyright: ignore[reportUnusedFunction]
        thread_id: Annotated[str, Form()],
        text: Annotated[str, Form()],
    ) -> HTMLResponse:
        await ctx.pool.send_message(thread_id, text)
        html_body = ctx.env.get_template('partials/send_message_result.html').render(
            thread_id=thread_id,
            text=text,
        )
        return HTMLResponse(content=html_body)

    @app.post('/commands/hide_thread')
    async def hide_thread(  # pyright: ignore[reportUnusedFunction]
        thread_id: Annotated[str, Form()],
    ) -> Response:
        await ctx.pool.hide_when_idle(thread_id)
        return Response(status_code=204)

    @app.post('/commands/delete_thread', response_class=HTMLResponse)
    async def delete_thread(  # pyright: ignore[reportUnusedFunction]
        thread_id: Annotated[str, Form()],
    ) -> HTMLResponse:
        await ctx.pool.delete_thread(thread_id)
        return HTMLResponse(
            content=(
                '<p class="empty">Thread deleted.</p><div id="thread-topbar-actions" hx-swap-oob="innerHTML"></div>'
            ),
        )

    @app.post('/commands/delete_tutor_entry')
    async def delete_tutor_entry(  # pyright: ignore[reportUnusedFunction]
        anchor_id: Annotated[str, Form()],
    ) -> Response:
        await ctx.pool.delete_tutor_entry(anchor_id)
        return Response(status_code=204)

    @app.post('/commands/clear_explanation')
    async def clear_explanation(  # pyright: ignore[reportUnusedFunction]
        anchor_id: Annotated[str, Form()],
    ) -> Response:
        await ctx.pool.clear_tutor_entry_explanation(anchor_id)
        return Response(status_code=204)

    @app.post('/commands/explain', response_class=HTMLResponse)
    async def explain(  # pyright: ignore[reportUnusedFunction]
        entry_id: Annotated[str, Form()],
        source_language: Annotated[str, Form()],
        target_language: Annotated[str, Form()],
        level: Annotated[str, Form()],
    ) -> HTMLResponse:
        _validate_audience(source_language, target_language, level)
        entries = ctx.tutor_store.load()
        idx = next((i for i, e in enumerate(entries) if e.id == entry_id), -1)
        if idx < 0:
            raise HTTPException(status_code=404, detail='entry not found')
        target = entries[idx]
        if target.explanation is not None:
            return HTMLResponse(content=ctx.sink.render_line(target, active=True))
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
                ctx,
                target,
                user_msg,
                options,
                source_language=source_language,
                target_language=target_language,
                level=level,
            ),
        )
        ctx.sink.track_explain(task)
        return HTMLResponse(content=ctx.sink.render_line(target, streaming=True))

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


async def run_web(args: argparse.Namespace) -> int:
    """Run the browser UI. Serves a FastAPI app on localhost."""
    try:
        filter_re = re.compile(args.filter_regex) if args.filter_regex else None
    except re.PatternError as exc:
        msg = f'oh-language-tutor: invalid --filter-regex: {exc}'
        raise SystemExit(msg) from exc

    extras_text = read_extras_system_prompt(args.extra_system_prompt) if args.extra_system_prompt else None

    state_dir = Path(args.state_dir).expanduser()
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / 'tutor.log'

    stop_event = asyncio.Event()

    with log_path.open('a', encoding='utf-8', buffering=1) as log:
        log.write(
            f'\n=== session start explain_model={args.explain_model} '
            f'ask_model={args.ask_model} '
            f'bind={args.web_host}:{args.web_port} ===\n',
        )

        tutor_store = TutorStore(state_dir / 'tutor.json')
        thread_store = ThreadStore(state_dir / 'threads')
        env = build_template_env()
        sink = WebSink(log=log, tutor_store=tutor_store, env=env)

        pool = FollowupThreadPool(
            model=args.ask_model,
            sink=sink,
            store=thread_store,
            tutor_store=tutor_store,
            log=log,
        )

        ctx = WebContext(
            args=args,
            log=log,
            filter_re=filter_re,
            stop_event=stop_event,
            tutor_store=tutor_store,
            thread_store=thread_store,
            sink=sink,
            pool=pool,
            extras_text=extras_text,
            env=env,
            version=str(int(time.time())),
        )

        # Warm the sink's cached thread list so the first /events subscriber
        # sees it without waiting for a state change.
        sink.on_thread_list(pool.list_threads())

        stdin_task = asyncio.create_task(
            stdin_loop(sink, filter_re, stop_event),
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
            await pool.close_all()
            await sink.flush_pending_writes()
            log.write('=== session end ===\n')

    return 0
