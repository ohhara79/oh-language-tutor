"""Tests for ``tutor.web`` helpers and route handlers."""

from __future__ import annotations

import argparse
import asyncio
import io
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from tutor.thread_store import ThreadStore
from tutor.tutor_store import TutorStore
from tutor.types import ThreadMessage, ThreadMeta, TutorEntry
from tutor.web import WebContext, _uvicorn_log_config, build_app, build_template_env, thread_heading
from tutor.web_sink import WebSink

if TYPE_CHECKING:
    from pathlib import Path


# -- thread_heading ----------------------------------------------------------


def _meta(**kw: Any) -> ThreadMeta:
    defaults = dict(
        thread_id='t',
        anchor_raw='anchor-text',
        session_id='s',
        created_at='2026-04-18T00:00:00+00:00',
        anchor_id='a',
        messages=[],
    )
    defaults.update(kw)
    return ThreadMeta(**defaults)  # pyright: ignore[reportArgumentType]


def test_thread_heading_uses_first_user_message():
    meta = _meta(
        messages=[
            ThreadMessage(role='user', text='  what does it mean?  '),
            ThreadMessage(role='assistant', text='it means …'),
        ]
    )
    assert thread_heading(meta) == 'what does it mean?'


def test_thread_heading_picks_first_non_blank_line():
    meta = _meta(
        messages=[
            ThreadMessage(role='user', text='\n\n   first real line\nextra'),
        ]
    )
    assert thread_heading(meta) == 'first real line'


def test_thread_heading_falls_back_to_anchor_raw():
    meta = _meta(anchor_raw='fallback-anchor', messages=[])
    assert thread_heading(meta) == 'fallback-anchor'


def test_thread_heading_user_with_only_whitespace_falls_back():
    meta = _meta(anchor_raw='anchor', messages=[ThreadMessage(role='user', text='   \n\n')])
    assert thread_heading(meta) == 'anchor'


# -- build_template_env ------------------------------------------------------


def test_build_template_env_returns_environment_with_globals():
    env = build_template_env()
    assert 'render_markdown' in env.globals
    assert 'format_created_at_utc' in env.globals
    assert 'thread_heading' in env.globals
    tmpl = env.get_template('partials/line.html')
    assert tmpl is not None


# -- _uvicorn_log_config -----------------------------------------------------


def test_uvicorn_log_config_structure():
    cfg = _uvicorn_log_config()
    assert cfg['version'] == 1
    assert cfg['handlers']['default']['stream'] == 'ext://sys.stderr'
    for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
        assert cfg['loggers'][name]['level'] == 'WARNING'


# -- Route handlers ----------------------------------------------------------


@dataclass
class _FakePool:
    """Minimal stand-in for FollowupThreadPool that records calls."""

    threads: dict[str, ThreadMeta]
    opened: list[tuple[str, str]]
    sent: list[tuple[str, str]]
    hidden: list[str]
    deleted: list[str]
    deleted_tutor: list[str]
    reopened: list[str]
    active: set[str]
    _active: dict[str, Any]  # satisfies `if thread_id not in ctx.pool._active` check

    def peek_meta(self, thread_id: str) -> ThreadMeta | None:
        return self.threads.get(thread_id)

    def list_threads(self) -> list[ThreadMeta]:
        return list(self.threads.values())

    async def open_thread(self, thread_id: str, anchor_id: str) -> None:
        self.opened.append((thread_id, anchor_id))
        self.threads[thread_id] = _meta(thread_id=thread_id, anchor_raw='x', anchor_id=anchor_id)
        self._active[thread_id] = object()

    async def reopen_thread(self, thread_id: str) -> None:
        self.reopened.append(thread_id)
        self._active[thread_id] = object()

    async def send_message(self, thread_id: str, text: str) -> None:
        self.sent.append((thread_id, text))

    async def hide_thread(self, thread_id: str) -> None:
        self.hidden.append(thread_id)

    async def delete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)
        self.threads.pop(thread_id, None)

    async def delete_tutor_entry(self, anchor_id: str) -> None:
        self.deleted_tutor.append(anchor_id)


def _build_ctx(tmp_path: Path) -> tuple[WebContext, _FakePool]:
    args = argparse.Namespace(
        source_language='Korean',
        target_language='English',
        level='intermediate',
        state_dir=str(tmp_path),
    )
    log = io.StringIO()
    tutor_store = TutorStore(tmp_path / 'tutor.json')
    tutor_store.append(TutorEntry(raw='hi', explanation='meaning', id='a-1'))
    thread_store = ThreadStore(tmp_path / 'threads')
    env = build_template_env()
    sink = WebSink(log=log, tutor_store=tutor_store, env=env)

    pool = _FakePool(
        threads={},
        opened=[],
        sent=[],
        hidden=[],
        deleted=[],
        deleted_tutor=[],
        reopened=[],
        active=set(),
        _active={},
    )

    stop = asyncio.Event()
    ctx = WebContext(
        args=args,
        log=log,
        filter_re=None,
        session_path=tmp_path / 'session.id',
        stop_event=stop,
        tutor_store=tutor_store,
        thread_store=thread_store,
        sink=sink,
        pool=pool,  # pyright: ignore[reportArgumentType]
        client=None,  # pyright: ignore[reportArgumentType]
        env=env,
        version='test-v',
    )
    return ctx, pool


def _client(ctx: WebContext) -> httpx.AsyncClient:
    app = build_app(ctx)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url='http://test')


async def test_get_index_returns_html_with_metadata(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.get('/')
    assert r.status_code == 200
    body = r.text
    assert 'Korean' in body
    assert 'English' in body
    assert 'intermediate' in body
    assert 'hi' in body  # pre-existing tutor entry


async def test_get_thread_404_when_missing(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.get('/threads/nope')
    assert r.status_code == 404


async def test_get_thread_reopens_and_renders(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    pool.threads['t-1'] = _meta(thread_id='t-1', anchor_raw='hi', anchor_id='a-1')
    async with _client(ctx) as client:
        r = await client.get('/threads/t-1')
    assert r.status_code == 200
    assert 't-1' in r.text
    assert pool.reopened == ['t-1']


async def test_post_open_thread_creates_and_broadcasts(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post('/commands/open_thread', data={'anchor_id': 'a-1'})
    assert r.status_code == 200
    assert len(pool.opened) == 1
    assert pool.opened[0][1] == 'a-1'


async def test_post_send_message_fragment_and_pool_called(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(
            '/commands/send_message',
            data={'thread_id': 't-1', 'text': 'howdy'},
        )
    assert r.status_code == 200
    assert pool.sent == [('t-1', 'howdy')]
    assert 'howdy' in r.text


async def test_post_hide_thread_returns_204(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post('/commands/hide_thread', data={'thread_id': 't-1'})
    assert r.status_code == 204
    assert pool.hidden == ['t-1']


async def test_post_delete_thread_returns_html(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post('/commands/delete_thread', data={'thread_id': 't-1'})
    assert r.status_code == 200
    assert 'deleted' in r.text.lower()
    assert pool.deleted == ['t-1']


async def test_post_delete_tutor_entry_returns_204(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post('/commands/delete_tutor_entry', data={'anchor_id': 'a-1'})
    assert r.status_code == 204
    assert pool.deleted_tutor == ['a-1']


async def test_events_endpoint_returns_sse_response(tmp_path: Path):
    """GET /events responds 200 with SSE content-type. The generator body is
    exercised indirectly via the other tests that hit subscribe/broadcast
    paths; covering the blocking loop itself needs a real running server."""
    ctx, pool = _build_ctx(tmp_path)
    pool.threads['t-1'] = _meta(thread_id='t-1', anchor_raw='x')
    # Pre-set stop_event so the generator's loop exits immediately after
    # emitting the initial frames.
    ctx.stop_event.set()

    app = build_app(ctx)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/events')
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('text/event-stream')
    assert b': connected' in r.content
    assert b'event: thread_list' in r.content
