"""Tests for ``tutor.web`` helpers and route handlers."""

from __future__ import annotations

import argparse
import asyncio
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from tests.conftest import FakeClaudeSDKClient, make_assistant, make_result, make_text_delta
from tutor import web as web_mod
from tutor.thread_store import ThreadStore
from tutor.tutor_store import TutorStore
from tutor.types import ThreadMessage, ThreadMeta, TutorEntry
from tutor.web import (
    VIEW_COOKIE,
    DirSession,
    LazyLog,
    WebContext,
    _uvicorn_log_config,
    build_app,
    build_template_env,
    list_state_dirs,
    thread_heading,
)
from tutor.web_sink import WebSink

if TYPE_CHECKING:
    from pathlib import Path

    from tests.conftest import FakeClaudeSDKClientFactory


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


# -- list_state_dirs ---------------------------------------------------------


def test_list_state_dirs_returns_subdirs_sorted(tmp_path: Path):
    (tmp_path / 'b-dir').mkdir()
    (tmp_path / 'a-dir').mkdir()
    (tmp_path / 'c-file').write_text('not a dir')
    names = [p.name for p in list_state_dirs(tmp_path)]
    assert names == ['a-dir', 'b-dir']


def test_list_state_dirs_skips_hidden(tmp_path: Path):
    (tmp_path / 'visible').mkdir()
    (tmp_path / '.hidden').mkdir()
    assert [p.name for p in list_state_dirs(tmp_path)] == ['visible']


def test_list_state_dirs_missing_parent(tmp_path: Path):
    assert list_state_dirs(tmp_path / 'no-such-dir') == []


# -- Route handlers ----------------------------------------------------------


@dataclass
class _FakePool:
    """Minimal stand-in for FollowupThreadPool that records calls."""

    threads: dict[str, ThreadMeta]
    opened: list[tuple[str, str, str, str, str]]
    sent: list[tuple[str, str]]
    hidden: list[str]
    deleted: list[str]
    deleted_tutor: list[str]
    reopened: list[str]
    active: set[str]
    _active: dict[str, Any]  # satisfies `if thread_id not in session.pool._active` check

    def peek_meta(self, thread_id: str) -> ThreadMeta | None:
        return self.threads.get(thread_id)

    def list_threads(self) -> list[ThreadMeta]:
        return list(self.threads.values())

    async def open_thread(
        self,
        thread_id: str,
        anchor_id: str,
        *,
        source_language: str,
        target_language: str,
        level: str,
    ) -> None:
        self.opened.append((thread_id, anchor_id, source_language, target_language, level))
        self.threads[thread_id] = _meta(thread_id=thread_id, anchor_raw='x', anchor_id=anchor_id)
        self._active[thread_id] = object()

    async def reopen_thread(self, thread_id: str) -> None:
        self.reopened.append(thread_id)
        self._active[thread_id] = object()

    async def send_message(self, thread_id: str, text: str) -> None:
        self.sent.append((thread_id, text))

    async def hide_thread(self, thread_id: str) -> None:
        self.hidden.append(thread_id)

    async def hide_when_idle(self, thread_id: str) -> None:
        self.hidden.append(thread_id)

    async def delete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)
        self.threads.pop(thread_id, None)

    async def delete_tutor_entry(self, anchor_id: str) -> None:
        self.deleted_tutor.append(anchor_id)


def _new_fake_pool() -> _FakePool:
    return _FakePool(
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


def _make_session(state_dir: Path, *, env: Any) -> tuple[DirSession, _FakePool]:
    """Build a DirSession backed by real stores + a real lazy log + a fake pool."""
    state_dir.mkdir(parents=True, exist_ok=True)
    log = LazyLog(state_dir / 'tutor.log', '=== test session start ===\n')
    tutor_store = TutorStore(state_dir / 'tutor.json')
    thread_store = ThreadStore(state_dir / 'threads')
    sink = WebSink(log=log, tutor_store=tutor_store, env=env)
    pool = _new_fake_pool()
    session = DirSession(
        state_dir=state_dir.resolve(),
        log=log,
        tutor_store=tutor_store,
        thread_store=thread_store,
        sink=sink,
        pool=pool,  # pyright: ignore[reportArgumentType]
    )
    return session, pool


def _read_log(session: DirSession) -> str:
    """Read the on-disk contents of a session's lazy log; ``''`` if not opened."""
    log_path = session.state_dir / 'tutor.log'
    if not log_path.exists():
        return ''
    return log_path.read_text(encoding='utf-8')


def _build_ctx(tmp_path: Path, *, extras_text: str | None = None) -> tuple[WebContext, _FakePool]:
    """Build a single-session context whose writing dir is *tmp_path*."""
    # Put the writing dir as a subdir of tmp_path so list_state_dirs can find it.
    writing_dir = tmp_path / 'writing'
    args = argparse.Namespace(
        state_dir=str(writing_dir),
        explain_model='test-model',
        ask_model='test-model',
        web_host='127.0.0.1',
        web_port=8000,
    )
    env = build_template_env()
    session, pool = _make_session(writing_dir, env=env)
    session.tutor_store.append(TutorEntry(raw='hi', explanation='meaning', id='a-1'))

    ctx = WebContext(
        args=args,
        filter_re=None,
        stop_event=asyncio.Event(),
        writing_dir=writing_dir.resolve(),
        discovery_parent=tmp_path.resolve(),
        sessions={writing_dir.resolve(): session},
        writing_session=session,
        extras_text=extras_text,
        env=env,
        version='test-v',
    )
    return ctx, pool


_AUDIENCE_FORM = {
    'source_language': 'English',
    'target_language': 'Korean',
    'level': 'intermediate',
}


def _client(ctx: WebContext, *, view_dir: str | None = None) -> httpx.AsyncClient:
    """Build a test client with the view-state cookie pre-set.

    Defaults to the writing dir's basename so route tests can hit cookie-gated
    endpoints directly. Pass ``view_dir=''`` to send a request with no cookie.
    """
    app = build_app(ctx)
    transport = httpx.ASGITransport(app=app)
    cookies: dict[str, str] = {}
    name = ctx.writing_dir.name if view_dir is None else view_dir
    if name:
        cookies[VIEW_COOKIE] = name
    return httpx.AsyncClient(transport=transport, base_url='http://test', cookies=cookies)


# -- picker / open_state_dir -------------------------------------------------


async def test_get_root_renders_picker_with_writing_badge(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    # Also create a sibling dir so the picker has more than one option.
    (tmp_path / 'other').mkdir()
    async with _client(ctx) as client:
        r = await client.get('/')
    assert r.status_code == 200
    body = r.text
    assert 'writing' in body  # the writing dir
    assert 'other' in body  # the sibling
    assert 'writes here' in body  # badge on the writing dir


async def test_get_root_renders_when_no_dirs_present(tmp_path: Path):
    # WebContext with discovery_parent that contains no subdirs.
    ctx, _ = _build_ctx(tmp_path)
    shutil.rmtree(ctx.writing_dir)
    async with _client(ctx) as client:
        r = await client.get('/')
    assert r.status_code == 200
    assert 'No tutor data' in r.text


async def test_post_open_state_dir_sets_cookie_and_redirects(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    (tmp_path / 'other').mkdir()
    async with _client(ctx, view_dir='') as client:
        r = await client.post('/commands/open_state_dir', data={'dir_name': 'other'})
    assert r.status_code == 303
    assert r.headers['location'] == '/tutor'
    assert r.cookies.get(VIEW_COOKIE) == 'other'


async def test_post_open_state_dir_rejects_unknown_dir(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx, view_dir='') as client:
        r = await client.post(
            '/commands/open_state_dir',
            data={'dir_name': 'no-such-dir'},
        )
    assert r.status_code == 400


async def test_post_open_state_dir_rejects_traversal(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx, view_dir='') as client:
        r = await client.post(
            '/commands/open_state_dir',
            data={'dir_name': '../../etc'},
        )
    assert r.status_code == 400


async def test_get_tutor_without_cookie_redirects_to_picker(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx, view_dir='') as client:
        r = await client.get('/tutor', follow_redirects=False)
    assert r.status_code == 303
    assert r.headers['location'] == '/'


async def test_get_tutor_with_invalid_cookie_redirects_to_picker(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx, view_dir='no-such-dir') as client:
        r = await client.get('/tutor', follow_redirects=False)
    assert r.status_code == 303


# -- /tutor index (cookie-routed) --------------------------------------------


async def test_get_tutor_renders_entries(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.get('/tutor')
    assert r.status_code == 200
    body = r.text
    assert 'id="cfg-source-language"' not in body
    assert 'id="cfg-level"' not in body
    assert 'hi' in body  # pre-existing tutor entry
    assert 'Switch dataset' in body  # header link
    assert 'writing' in body  # current view-dir name shown


async def test_get_tutor_marks_non_writing_view(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    # Add a second dir + session, point cookie at it.
    other_dir = tmp_path / 'other'
    other_session, _other_pool = _make_session(other_dir, env=ctx.env)
    other_session.tutor_store.append(TutorEntry(raw='from-other', id='o-1'))
    ctx.sessions[other_dir.resolve()] = other_session
    async with _client(ctx, view_dir='other') as client:
        r = await client.get('/tutor')
    assert r.status_code == 200
    body = r.text
    assert 'from-other' in body  # other dir's content
    # Writing-dir entry a-1/'meaning' should not appear in the other dir's view.
    assert 'meaning' not in body
    assert 'data-entry-id="a-1"' not in body
    assert 'stdin lines stream into' in body  # banner notes the split


async def test_get_tutor_renders_per_line_controls_on_unexplained_entries(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    ctx.writing_session.tutor_store.append(TutorEntry(raw='unexplained line', id='u-9'))
    async with _client(ctx) as client:
        r = await client.get('/tutor')
    body = r.text
    assert 'class="cfg-source-language"' in body
    assert 'class="cfg-target-language"' in body
    assert 'class="cfg-level"' in body


# -- threads / commands ------------------------------------------------------


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


async def test_get_thread_without_cookie_returns_400(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx, view_dir='') as client:
        r = await client.get('/threads/t-1')
    assert r.status_code == 400


async def test_post_open_thread_uses_audience_frozen_on_entry(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    ctx.writing_session.tutor_store.delete('a-1')
    ctx.writing_session.tutor_store.append(
        TutorEntry(
            raw='hi',
            explanation='meaning',
            id='a-1',
            source_language='Spanish',
            target_language='Korean',
            level='advanced',
        ),
    )
    async with _client(ctx) as client:
        r = await client.post('/commands/open_thread', data={'anchor_id': 'a-1'})
    assert r.status_code == 200
    assert len(pool.opened) == 1
    _tid, anchor_id, src, tgt, level = pool.opened[0]
    assert anchor_id == 'a-1'
    assert (src, tgt, level) == ('Spanish', 'Korean', 'advanced')


async def test_post_open_thread_legacy_entry_falls_back_to_defaults(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post('/commands/open_thread', data={'anchor_id': 'a-1'})
    assert r.status_code == 200
    _tid, _aid, src, tgt, level = pool.opened[0]
    assert (src, tgt, level) == ('English', 'Korean', 'intermediate')


async def test_post_open_thread_unknown_entry_returns_404(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post('/commands/open_thread', data={'anchor_id': 'missing'})
    assert r.status_code == 404


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


# -- explain ----------------------------------------------------------------


async def test_post_explain_unknown_entry_returns_404(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(
            '/commands/explain',
            data={'entry_id': 'missing', **_AUDIENCE_FORM},
        )
    assert r.status_code == 404


async def test_post_explain_rejects_invalid_level(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(
            '/commands/explain',
            data={'entry_id': 'a-1', **_AUDIENCE_FORM, 'level': 'fluent'},
        )
    assert r.status_code == 400


async def test_post_explain_rejects_empty_audience(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(
            '/commands/explain',
            data={'entry_id': 'a-1', **_AUDIENCE_FORM, 'source_language': '   '},
        )
    assert r.status_code == 400


async def test_post_explain_already_explained_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _ = _build_ctx(tmp_path)
    called = False

    def factory(*, options: Any = None) -> FakeClaudeSDKClient:
        nonlocal called
        called = True
        msg = 'should not be called'
        raise AssertionError(msg)

    monkeypatch.setattr(web_mod, 'ClaudeSDKClient', factory)
    async with _client(ctx) as client:
        r = await client.post(
            '/commands/explain',
            data={'entry_id': 'a-1', **_AUDIENCE_FORM},
        )
    assert r.status_code == 200
    assert called is False
    assert 'meaning' in r.text  # explained partial


async def test_post_explain_happy_path(
    tmp_path: Path,
    fake_client_factory: FakeClaudeSDKClientFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _ = _build_ctx(tmp_path)
    ctx.writing_session.tutor_store.append(TutorEntry(raw='target raw', id='u-1'))
    fake_client_factory.push(
        FakeClaudeSDKClient(
            [
                [
                    make_text_delta('the '),
                    make_text_delta('explanation'),
                    make_assistant('the explanation'),
                    make_result('sid'),
                ]
            ]
        ),
    )
    monkeypatch.setattr(web_mod, 'ClaudeSDKClient', fake_client_factory)

    async with _client(ctx) as client:
        r = await client.post(
            '/commands/explain',
            data={'entry_id': 'u-1', **_AUDIENCE_FORM},
        )
        assert r.status_code == 200
        assert 'id="explain-stream-u-1"' in r.text
        assert 'Explaining' in r.text
        await ctx.writing_session.sink.flush_pending_writes()

    [stored_explained] = [e for e in ctx.writing_session.tutor_store.load() if e.id == 'u-1']
    assert stored_explained.explanation == 'the explanation'
    assert stored_explained.source_language == 'English'
    assert stored_explained.target_language == 'Korean'
    assert stored_explained.level == 'intermediate'

    assert len(fake_client_factory.constructed) == 1
    [sent_msg] = fake_client_factory.constructed[0].queries
    assert 'target raw' in sent_msg
    assert 'hi' in sent_msg
    [opts] = fake_client_factory.option_calls
    assert 'English' in opts.system_prompt
    assert 'Korean' in opts.system_prompt
    assert 'intermediate' in opts.system_prompt


async def test_post_explain_empty_response_logs_error_and_keeps_unexplained(
    tmp_path: Path,
    fake_client_factory: FakeClaudeSDKClientFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _ = _build_ctx(tmp_path)
    ctx.writing_session.tutor_store.append(TutorEntry(raw='target', id='u-2'))
    fake_client_factory.push(
        FakeClaudeSDKClient([[make_assistant(''), make_result('sid')]]),
    )
    monkeypatch.setattr(web_mod, 'ClaudeSDKClient', fake_client_factory)

    async with _client(ctx) as client:
        r = await client.post(
            '/commands/explain',
            data={'entry_id': 'u-2', **_AUDIENCE_FORM},
        )
        assert r.status_code == 200
        await ctx.writing_session.sink.flush_pending_writes()

    assert 'empty response' in _read_log(ctx.writing_session)
    [stored] = [e for e in ctx.writing_session.tutor_store.load() if e.id == 'u-2']
    assert stored.explanation is None


async def test_post_explain_client_failure_logs_error(
    tmp_path: Path,
    fake_client_factory: FakeClaudeSDKClientFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _ = _build_ctx(tmp_path)
    ctx.writing_session.tutor_store.append(TutorEntry(raw='target', id='u-3'))
    fake_client_factory.push(FakeClaudeSDKClient(raise_on_query=RuntimeError('boom')))
    monkeypatch.setattr(web_mod, 'ClaudeSDKClient', fake_client_factory)

    async with _client(ctx) as client:
        r = await client.post(
            '/commands/explain',
            data={'entry_id': 'u-3', **_AUDIENCE_FORM},
        )
        assert r.status_code == 200
        await ctx.writing_session.sink.flush_pending_writes()

    log_text = _read_log(ctx.writing_session)
    assert 'explain failed' in log_text
    assert 'boom' in log_text
    [stored] = [e for e in ctx.writing_session.tutor_store.load() if e.id == 'u-3']
    assert stored.explanation is None


async def test_post_explain_uses_context_window(
    tmp_path: Path,
    fake_client_factory: FakeClaudeSDKClientFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _ = _build_ctx(tmp_path)
    ctx.writing_session.tutor_store.append(TutorEntry(raw='ctx-1', id='c1'))
    ctx.writing_session.tutor_store.append(TutorEntry(raw='ctx-2', id='c2'))
    ctx.writing_session.tutor_store.append(TutorEntry(raw='target', id='u-4'))
    fake_client_factory.push(
        FakeClaudeSDKClient([[make_assistant('explained'), make_result('sid')]]),
    )
    monkeypatch.setattr(web_mod, 'ClaudeSDKClient', fake_client_factory)

    async with _client(ctx) as client:
        r = await client.post(
            '/commands/explain',
            data={'entry_id': 'u-4', **_AUDIENCE_FORM},
        )
        assert r.status_code == 200
        await ctx.writing_session.sink.flush_pending_writes()

    sent = fake_client_factory.constructed[0].queries[0]
    assert 'ctx-1' in sent
    assert 'ctx-2' in sent
    assert 'target' in sent
    assert 'hi' in sent


# -- SSE / two-dir isolation -------------------------------------------------


async def test_events_endpoint_returns_sse_response(tmp_path: Path):
    """GET /events responds 200 with SSE content-type."""
    ctx, pool = _build_ctx(tmp_path)
    pool.threads['t-1'] = _meta(thread_id='t-1', anchor_raw='x')
    ctx.stop_event.set()

    async with _client(ctx) as client:
        r = await client.get('/events')
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('text/event-stream')
    assert b': connected' in r.content
    assert b'event: thread_list' in r.content


async def test_events_requires_view_cookie(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx, view_dir='') as client:
        r = await client.get('/events')
    assert r.status_code == 400


# -- Laziness: browse-only picks leave the dir clean --------------------------


async def test_get_tutor_does_not_create_log_or_threads_dir(tmp_path: Path):
    """Hitting /tutor on a brand-new dir reads only; it must not touch disk."""
    ctx, _ = _build_ctx(tmp_path)
    # Build a fresh, untouched DirSession for a sibling dir. Use the same
    # path-based LazyLog as production.
    other_dir = tmp_path / 'untouched'
    other_dir.mkdir()
    other_session, _ = _make_session(other_dir, env=ctx.env)
    ctx.sessions[other_dir.resolve()] = other_session

    # Sanity: no log file, no threads/ before the request.
    assert not (other_dir / 'tutor.log').exists()
    assert not (other_dir / 'threads').exists()

    async with _client(ctx, view_dir='untouched') as client:
        r = await client.get('/tutor')
    assert r.status_code == 200

    # Reading is a read; nothing on disk should have appeared.
    assert not (other_dir / 'tutor.log').exists()
    assert not (other_dir / 'threads').exists()
    assert not other_session.log.opened


async def test_lazy_log_creates_file_on_first_write(tmp_path: Path):
    log = LazyLog(tmp_path / 'tutor.log', '=== header ===\n')
    assert not log.opened
    assert not (tmp_path / 'tutor.log').exists()
    log.write('first line\n')
    assert log.opened
    assert (tmp_path / 'tutor.log').exists()
    text = (tmp_path / 'tutor.log').read_text(encoding='utf-8')
    assert text == '=== header ===\nfirst line\n'


async def test_writing_sink_does_not_emit_to_view_dir_subscribers(tmp_path: Path):
    """Two-dir SSE isolation: a subscriber on dir B does not receive writes that the writing-dir sink emits."""
    ctx, _ = _build_ctx(tmp_path)
    # Materialize a second DirSession and put it in the cache.
    other_dir = tmp_path / 'other'
    other_session, _ = _make_session(other_dir, env=ctx.env)
    ctx.sessions[other_dir.resolve()] = other_session

    # Subscribe to the OTHER session's sink, then emit on the WRITING session.
    q = other_session.sink.subscribe()
    try:
        ctx.writing_session.sink.on_entry_appended(TutorEntry(raw='new-line', id='x-1'))
        # The other-dir subscriber should see nothing.
        assert q.empty()
    finally:
        other_session.sink.unsubscribe(q)
