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
    TextBlock,
)
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from tutor.core import stdin_loop
from tutor.markdown_util import render_markdown
from tutor.prompts import EXPLAIN_CONTEXT_K, build_explain_user_message, build_system_prompt
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
_STREAM_PAGE_N = 50


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
    explain_options: ClaudeAgentOptions
    env: Environment
    version: str  # cache-buster for static assets


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


async def _run_explain(options: ClaudeAgentOptions, user_msg: str) -> str:
    """Run one short-lived Claude session and return the joined assistant text."""
    buf: list[str] = []
    async with ClaudeSDKClient(options=options) as client:
        await client.query(user_msg)
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                buf.extend(b.text for b in msg.content if isinstance(b, TextBlock))
    return ''.join(buf).strip()


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
            source_language=ctx.args.source_language,
            target_language=ctx.args.target_language,
            level=ctx.args.level,
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
        thread_id = new_thread_id()
        await ctx.pool.open_thread(thread_id, anchor_id)
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

    @app.post('/commands/explain', response_class=HTMLResponse)
    async def explain(  # pyright: ignore[reportUnusedFunction]
        entry_id: Annotated[str, Form()],
    ) -> HTMLResponse:
        entries = ctx.tutor_store.load()
        idx = next((i for i, e in enumerate(entries) if e.id == entry_id), -1)
        if idx < 0:
            raise HTTPException(status_code=404, detail='entry not found')
        target = entries[idx]
        if target.explanation is not None:
            return HTMLResponse(content=ctx.sink.render_line(target))
        context_raws = [e.raw for e in entries[max(0, idx - EXPLAIN_CONTEXT_K) : idx]]
        user_msg = build_explain_user_message(target.raw, context_raws)
        try:
            explanation = await _run_explain(ctx.explain_options, user_msg)
        except Exception as exc:
            ctx.sink.on_error(f'explain failed: {exc}')
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if not explanation:
            ctx.sink.on_error('explain produced empty response')
            raise HTTPException(status_code=502, detail='empty explanation')
        await ctx.tutor_store.update_explanation_async(entry_id, explanation)
        updated = TutorEntry(raw=target.raw, explanation=explanation, id=target.id)
        ctx.sink.on_entry_explained(updated)
        return HTMLResponse(content=ctx.sink.render_line(updated))

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

    system_prompt = build_system_prompt(args)

    state_dir = Path(args.state_dir).expanduser()
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / 'tutor.log'

    explain_options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=args.explain_model,
        allowed_tools=[],
    )

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
            source_language=args.source_language,
            target_language=args.target_language,
            level=args.level,
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
            explain_options=explain_options,
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
