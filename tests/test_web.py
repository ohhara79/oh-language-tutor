"""Tests for ``tutor.web`` helpers and route handlers."""

from __future__ import annotations

import argparse
import asyncio
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx
import pytest

from tests.conftest import FakeClaudeSDKClient, make_assistant, make_result, make_text_delta
from tutor import web as web_mod
from tutor.thread_store import ThreadStore
from tutor.tutor_store import TutorStore
from tutor.types import ThreadMessage, ThreadMeta, TutorEntry
from tutor.web import (
    DirSession,
    LazyLog,
    WebContext,
    _close_session,
    _get_or_create_session,
    _make_lazy_log,
    _uvicorn_log_config,
    build_app,
    build_template_env,
    list_state_dirs,
    make_dir_session,
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


def test_thread_heading_skips_non_user_first_message():
    """Defensive: an assistant-first meta should still find the later user text."""
    meta = _meta(
        anchor_raw='anchor',
        messages=[
            ThreadMessage(role='assistant', text='greeting from claude'),
            ThreadMessage(role='user', text='actual user question'),
        ],
    )
    assert thread_heading(meta) == 'actual user question'


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

    async def clear_tutor_entry_explanation(self, anchor_id: str) -> None:
        self.deleted_tutor.append(f'clear:{anchor_id}')

    async def close_all(self) -> None:
        self.active.clear()
        self._active.clear()


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
    sink = WebSink(log=log, tutor_store=tutor_store, env=env, view_dir=state_dir.name)
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


def _client(ctx: WebContext) -> httpx.AsyncClient:
    """Build a test client against *ctx*'s app.

    The view dir is part of the URL path now, so the client carries no cookie
    and every test that hits a dir-scoped route builds the URL with ``_dir_url``.
    """
    app = build_app(ctx)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url='http://test')


def _dir_url(ctx: WebContext, suffix: str = '', *, dir_name: str | None = None) -> str:
    """Build a ``/tutor/<dir>{suffix}`` URL for a dir-scoped route.

    Defaults to the writing dir; tests that target a different dir pass
    *dir_name* explicitly.
    """
    name = ctx.writing_dir.name if dir_name is None else dir_name
    return f'/tutor/{quote(name, safe="")}{suffix}'


# -- picker ------------------------------------------------------------------


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


async def test_get_root_renders_picker_rows_as_links(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    (tmp_path / 'other').mkdir()
    async with _client(ctx) as client:
        r = await client.get('/')
    assert r.status_code == 200
    assert f'href="{_dir_url(ctx, dir_name="other")}"' in r.text


async def test_picker_link_supports_non_ascii_name(tmp_path: Path):
    # State-dir names with non-ASCII characters (e.g. Chinese) must be
    # percent-encoded in the picker link and resolve to the right session when
    # the browser follows it.
    ctx, _ = _build_ctx(tmp_path)
    cjk_name = '老友记.S01E01'
    (tmp_path / cjk_name).mkdir()
    href = _dir_url(ctx, dir_name=cjk_name)
    async with _client(ctx) as client:
        r = await client.get('/')
        assert f'href="{href}"' in r.text
        r2 = await client.get(href)
    assert r2.status_code == 200
    assert cjk_name in r2.text


async def test_get_tutor_unknown_dir_redirects_to_picker(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.get('/tutor/no-such-dir', follow_redirects=False)
    assert r.status_code == 303
    assert r.headers['location'] == '/'


# -- /tutor/{dir_name} index -------------------------------------------------


async def test_get_tutor_renders_entries(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.get(_dir_url(ctx))
    assert r.status_code == 200
    body = r.text
    assert 'id="cfg-source-language"' not in body
    assert 'id="cfg-level"' not in body
    assert 'hi' in body  # pre-existing tutor entry
    assert 'href="/"' in body  # header title links to picker
    assert 'writing' in body  # current view-dir name shown
    assert 'data-state-dir="writing"' in body  # JS dataset-name source


async def test_get_tutor_marks_non_writing_view(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    # Add a second dir + session and request it directly via its path.
    other_dir = tmp_path / 'other'
    other_session, _other_pool = _make_session(other_dir, env=ctx.env)
    other_session.tutor_store.append(TutorEntry(raw='from-other', id='o-1'))
    ctx.sessions[other_dir.resolve()] = other_session
    async with _client(ctx) as client:
        r = await client.get(_dir_url(ctx, dir_name='other'))
    assert r.status_code == 200
    body = r.text
    assert 'from-other' in body  # other dir's content
    # Writing-dir entry a-1/'meaning' should not appear in the other dir's view.
    assert 'meaning' not in body
    assert 'data-entry-id="a-1"' not in body
    assert '>other</a>' in body  # header title shows the non-writing view dir


async def test_get_tutor_renders_per_line_controls_on_unexplained_entries(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    ctx.writing_session.tutor_store.append(TutorEntry(raw='unexplained line', id='u-9'))
    async with _client(ctx) as client:
        r = await client.get(_dir_url(ctx))
    body = r.text
    assert 'class="cfg-source-language"' in body
    assert 'class="cfg-target-language"' in body
    assert 'class="cfg-level"' in body


# -- threads / commands ------------------------------------------------------


async def test_get_thread_404_when_missing(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.get(_dir_url(ctx, '/threads/nope'))
    assert r.status_code == 404


async def test_get_thread_reopens_and_renders(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    pool.threads['t-1'] = _meta(thread_id='t-1', anchor_raw='hi', anchor_id='a-1')
    async with _client(ctx) as client:
        r = await client.get(_dir_url(ctx, '/threads/t-1'))
    assert r.status_code == 200
    assert 't-1' in r.text
    assert pool.reopened == ['t-1']


async def test_get_thread_unknown_dir_returns_404(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.get('/tutor/no-such-dir/threads/t-1')
    assert r.status_code == 404


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
        r = await client.post(_dir_url(ctx, '/commands/open_thread'), data={'anchor_id': 'a-1'})
    assert r.status_code == 200
    assert len(pool.opened) == 1
    _tid, anchor_id, src, tgt, level = pool.opened[0]
    assert anchor_id == 'a-1'
    assert (src, tgt, level) == ('Spanish', 'Korean', 'advanced')


async def test_post_open_thread_legacy_entry_falls_back_to_defaults(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(_dir_url(ctx, '/commands/open_thread'), data={'anchor_id': 'a-1'})
    assert r.status_code == 200
    _tid, _aid, src, tgt, level = pool.opened[0]
    assert (src, tgt, level) == ('English', 'Korean', 'intermediate')


async def test_post_open_thread_returns_500_when_pool_emits_no_meta(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)

    async def silent_open(  # type: ignore[no-untyped-def]
        thread_id: str,
        anchor_id: str,
        *,
        source_language: str,
        target_language: str,
        level: str,
    ) -> None:
        # Record the open but DON'T register meta — simulates open_thread that
        # errored internally (e.g., anchor not found in tutor_store).
        pool.opened.append((thread_id, anchor_id, source_language, target_language, level))

    pool.open_thread = silent_open  # type: ignore[method-assign]

    async with _client(ctx) as client:
        r = await client.post(_dir_url(ctx, '/commands/open_thread'), data={'anchor_id': 'a-1'})
    assert r.status_code == 500


async def test_post_open_thread_unknown_entry_returns_404(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(_dir_url(ctx, '/commands/open_thread'), data={'anchor_id': 'missing'})
    assert r.status_code == 404


async def test_post_send_message_fragment_and_pool_called(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(
            _dir_url(ctx, '/commands/send_message'),
            data={'thread_id': 't-1', 'text': 'howdy'},
        )
    assert r.status_code == 200
    assert pool.sent == [('t-1', 'howdy')]
    assert 'howdy' in r.text


async def test_post_hide_thread_returns_204(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(_dir_url(ctx, '/commands/hide_thread'), data={'thread_id': 't-1'})
    assert r.status_code == 204
    assert pool.hidden == ['t-1']


async def test_post_delete_thread_returns_html(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(_dir_url(ctx, '/commands/delete_thread'), data={'thread_id': 't-1'})
    assert r.status_code == 200
    assert 'deleted' in r.text.lower()
    assert pool.deleted == ['t-1']


async def test_post_delete_tutor_entry_returns_204(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(_dir_url(ctx, '/commands/delete_tutor_entry'), data={'anchor_id': 'a-1'})
    assert r.status_code == 204
    assert pool.deleted_tutor == ['a-1']


# -- explain ----------------------------------------------------------------


async def test_post_explain_unknown_entry_returns_404(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(
            _dir_url(ctx, '/commands/explain'),
            data={'entry_id': 'missing', **_AUDIENCE_FORM},
        )
    assert r.status_code == 404


async def test_post_explain_rejects_invalid_level(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(
            _dir_url(ctx, '/commands/explain'),
            data={'entry_id': 'a-1', **_AUDIENCE_FORM, 'level': 'fluent'},
        )
    assert r.status_code == 400


async def test_post_explain_rejects_empty_audience(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(
            _dir_url(ctx, '/commands/explain'),
            data={'entry_id': 'a-1', **_AUDIENCE_FORM, 'source_language': '   '},
        )
    assert r.status_code == 400


async def test_post_explain_rejects_language_mismatch(
    tmp_path: Path,
    fake_client_factory: FakeClaudeSDKClientFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _ = _build_ctx(tmp_path)
    ctx.writing_session.tutor_store.append(TutorEntry(raw='안녕하세요', id='u-mm'))
    # Trip-wire: the explain pipeline must not reach the Claude client.
    monkeypatch.setattr(web_mod, 'ClaudeSDKClient', fake_client_factory)

    async with _client(ctx) as client:
        r = await client.post(
            _dir_url(ctx, '/commands/explain'),
            data={'entry_id': 'u-mm', **_AUDIENCE_FORM},  # source_language='English'
        )
    # 200 with an HTMX-swappable line that carries an inline error and the
    # Explain form so the user can retry after fixing the menu setting.
    assert r.status_code == 200
    assert 'id="line-u-mm"' in r.text
    assert 'line-error' in r.text
    assert 'Korean' in r.text
    assert 'English' in r.text
    assert '/commands/explain' in r.text  # Explain form still present
    # Entry stays unexplained, and no Claude session was ever constructed.
    [stored] = [e for e in ctx.writing_session.tutor_store.load() if e.id == 'u-mm']
    assert stored.explanation is None
    assert fake_client_factory.constructed == []


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
            _dir_url(ctx, '/commands/explain'),
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
            _dir_url(ctx, '/commands/explain'),
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


async def test_post_explain_japanese_injects_kyujitai_ground_truth(
    tmp_path: Path,
    fake_client_factory: FakeClaudeSDKClientFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _ = _build_ctx(tmp_path)
    # 弁護士 carries an ambiguous shinjitai (弁 → 辨|瓣|辯|辮) plus two
    # unmapped kanji; the converter must emit a bracketed template.
    ctx.writing_session.tutor_store.append(TutorEntry(raw='弁護士', id='u-jp'))
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
            _dir_url(ctx, '/commands/explain'),
            data={'entry_id': 'u-jp', **_AUDIENCE_FORM, 'source_language': 'Japanese'},
        )
        assert r.status_code == 200
        await ctx.writing_session.sink.flush_pending_writes()

    [opts] = fake_client_factory.option_calls
    assert 'GROUND TRUTH FOR THE TARGET LINE:' in opts.system_prompt
    # The unambiguous chars are pre-substituted, the ambiguous one becomes a bracket group.
    assert '[辨|瓣|辯|辮]護士' in opts.system_prompt
    # Per-kanji mappings for vocab — 弁 is the only mapped kanji in 弁護士.
    assert 'Per-kanji kyūjitai mappings' in opts.system_prompt
    assert '弁 → 辨 / 瓣 / 辯 / 辮' in opts.system_prompt


async def test_post_explain_non_japanese_omits_kyujitai_ground_truth(
    tmp_path: Path,
    fake_client_factory: FakeClaudeSDKClientFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _ = _build_ctx(tmp_path)
    ctx.writing_session.tutor_store.append(TutorEntry(raw='学校', id='u-ko'))
    fake_client_factory.push(
        FakeClaudeSDKClient([[make_assistant('explanation'), make_result('sid')]]),
    )
    monkeypatch.setattr(web_mod, 'ClaudeSDKClient', fake_client_factory)

    async with _client(ctx) as client:
        r = await client.post(
            _dir_url(ctx, '/commands/explain'),
            data={'entry_id': 'u-ko', **_AUDIENCE_FORM, 'source_language': 'Chinese'},
        )
        assert r.status_code == 200
        await ctx.writing_session.sink.flush_pending_writes()

    [opts] = fake_client_factory.option_calls
    assert 'GROUND TRUTH FOR THE TARGET LINE:' not in opts.system_prompt


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
            _dir_url(ctx, '/commands/explain'),
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
            _dir_url(ctx, '/commands/explain'),
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
            _dir_url(ctx, '/commands/explain'),
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
    """GET /tutor/<dir>/events responds 200 with SSE content-type."""
    ctx, pool = _build_ctx(tmp_path)
    pool.threads['t-1'] = _meta(thread_id='t-1', anchor_raw='x')
    ctx.stop_event.set()

    async with _client(ctx) as client:
        r = await client.get(_dir_url(ctx, '/events'))
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('text/event-stream')
    assert b': connected' in r.content
    assert b'event: thread_list' in r.content


async def test_events_unknown_dir_returns_404(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.get('/tutor/no-such-dir/events')
    assert r.status_code == 404


# -- Laziness: browse-only picks leave the dir clean --------------------------


async def test_get_tutor_does_not_create_log_or_threads_dir(tmp_path: Path):
    """Hitting /tutor/<dir> on a brand-new dir reads only; it must not touch disk."""
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

    async with _client(ctx) as client:
        r = await client.get(_dir_url(ctx, dir_name='untouched'))
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


# -- /commands/clear_explanation --------------------------------------------


async def test_post_clear_explanation_returns_204_and_calls_pool(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post(_dir_url(ctx, '/commands/clear_explanation'), data={'anchor_id': 'a-1'})
    assert r.status_code == 204
    assert pool.deleted_tutor == ['clear:a-1']


async def test_post_clear_explanation_unknown_dir_returns_404(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.post('/tutor/no-such-dir/commands/clear_explanation', data={'anchor_id': 'a-1'})
    assert r.status_code == 404


# -- explain extras gating / PromptTooLargeError -----------------------------


async def test_post_explain_oversized_extras_returns_400(
    tmp_path: Path,
    fake_client_factory: FakeClaudeSDKClientFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    from tutor.prompts import MAX_SYSTEM_PROMPT_BYTES

    ctx, _ = _build_ctx(tmp_path, extras_text='A' * (MAX_SYSTEM_PROMPT_BYTES + 1))
    ctx.writing_session.tutor_store.append(TutorEntry(raw='target', id='u-pt'))
    monkeypatch.setattr(web_mod, 'ClaudeSDKClient', fake_client_factory)

    async with _client(ctx) as client:
        r = await client.post(
            _dir_url(ctx, '/commands/explain'),
            data={'entry_id': 'u-pt', **_AUDIENCE_FORM},
        )
    assert r.status_code == 400
    assert 'execve per-arg cap' in r.text


_EXTRAS_MARKER = 'ADDITIONAL SOURCE-SPECIFIC CONTEXT:'


async def test_post_explain_writing_dir_includes_extras(
    tmp_path: Path,
    fake_client_factory: FakeClaudeSDKClientFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _ = _build_ctx(tmp_path, extras_text='SHOW-NOTES-XYZ')
    ctx.writing_session.tutor_store.append(TutorEntry(raw='target', id='u-w'))
    fake_client_factory.push(
        FakeClaudeSDKClient([[make_assistant('explained'), make_result('sid')]]),
    )
    monkeypatch.setattr(web_mod, 'ClaudeSDKClient', fake_client_factory)

    async with _client(ctx) as client:
        r = await client.post(
            _dir_url(ctx, '/commands/explain'),
            data={'entry_id': 'u-w', **_AUDIENCE_FORM},
        )
        assert r.status_code == 200
        await ctx.writing_session.sink.flush_pending_writes()

    [opts] = fake_client_factory.option_calls
    assert _EXTRAS_MARKER in opts.system_prompt
    assert 'SHOW-NOTES-XYZ' in opts.system_prompt


async def test_post_explain_sibling_dir_omits_extras(
    tmp_path: Path,
    fake_client_factory: FakeClaudeSDKClientFactory,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _ = _build_ctx(tmp_path, extras_text='SHOW-NOTES-XYZ')
    sibling_dir = tmp_path / 'other'
    sibling_session = _get_or_create_session(ctx, sibling_dir)
    sibling_session.tutor_store.append(TutorEntry(raw='target', id='u-s'))
    fake_client_factory.push(
        FakeClaudeSDKClient([[make_assistant('explained'), make_result('sid')]]),
    )
    monkeypatch.setattr(web_mod, 'ClaudeSDKClient', fake_client_factory)

    async with _client(ctx) as client:
        r = await client.post(
            _dir_url(ctx, '/commands/explain', dir_name='other'),
            data={'entry_id': 'u-s', **_AUDIENCE_FORM},
        )
        assert r.status_code == 200
        await sibling_session.sink.flush_pending_writes()

    [opts] = fake_client_factory.option_calls
    assert _EXTRAS_MARKER not in opts.system_prompt
    assert 'SHOW-NOTES-XYZ' not in opts.system_prompt


# -- LazyLog edges -----------------------------------------------------------


async def test_lazy_log_flush_before_open_is_noop(tmp_path: Path):
    log = LazyLog(tmp_path / 'tutor.log', '=== header ===\n')
    log.flush()  # must not error or open the file
    assert not (tmp_path / 'tutor.log').exists()


async def test_lazy_log_flush_after_write_flushes(tmp_path: Path):
    log = LazyLog(tmp_path / 'tutor.log', '=== header ===\n')
    log.write('payload\n')
    log.flush()
    log.close()
    assert (tmp_path / 'tutor.log').read_text(encoding='utf-8').endswith('payload\n')


async def test_lazy_log_close_before_open_is_noop(tmp_path: Path):
    log = LazyLog(tmp_path / 'tutor.log', '=== header ===\n')
    log.close()  # must not error
    assert not (tmp_path / 'tutor.log').exists()


async def test_lazy_log_repeat_writes_reuse_handle(tmp_path: Path):
    log = LazyLog(tmp_path / 'tutor.log', '=== header ===\n')
    log.write('one\n')
    log.write('two\n')
    log.close()
    text = (tmp_path / 'tutor.log').read_text(encoding='utf-8')
    assert text == '=== header ===\none\ntwo\n'


# -- get_thread already-active branch ---------------------------------------


async def test_get_thread_already_active_skips_reopen(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    pool.threads['t-1'] = _meta(thread_id='t-1', anchor_raw='hi', anchor_id='a-1')
    pool._active['t-1'] = object()  # mark already-active
    async with _client(ctx) as client:
        r = await client.get(_dir_url(ctx, '/threads/t-1'))
    assert r.status_code == 200
    assert pool.reopened == []  # short-circuit kept reopen from firing


# -- writing_sink_does_not_emit_to_view_dir_subscribers ---------------------


# -- make_dir_session / _get_or_create_session ------------------------------


def test_make_dir_session_creates_dir_and_wires_components(tmp_path: Path):
    state_dir = tmp_path / 'fresh'
    assert not state_dir.exists()
    args = argparse.Namespace(
        explain_model='m',
        ask_model='m',
        web_host='127.0.0.1',
        web_port=8000,
    )
    env = build_template_env()
    session = make_dir_session(state_dir, args, env)
    assert state_dir.exists()
    assert isinstance(session.log, LazyLog)
    assert session.state_dir == state_dir
    # Warming the thread list shouldn't dirty disk on its own.
    assert not (state_dir / 'tutor.log').exists()


def test_get_or_create_session_returns_cached(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    first = _get_or_create_session(ctx, ctx.writing_dir)
    second = _get_or_create_session(ctx, ctx.writing_dir)
    assert first is second  # cache hit returns the same DirSession


def test_get_or_create_session_creates_new_for_unknown_dir(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    other = tmp_path / 'novel'
    session = _get_or_create_session(ctx, other)
    assert session.state_dir == other.resolve()
    assert other.resolve() in ctx.sessions


# -- path-segment defenses --------------------------------------------------


async def test_get_tutor_with_dot_prefix_dir_redirects(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    async with _client(ctx) as client:
        r = await client.get('/tutor/.hidden', follow_redirects=False)
    assert r.status_code == 303
    assert r.headers['location'] == '/'


async def test_get_tutor_with_encoded_slash_dir_rejects(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    # ``%2F`` decodes to a literal slash inside the path segment, which the
    # traversal defense rejects (redirect-to-picker or 404 depending on how the
    # router resolves it). Either is fine — what matters is it does not load a
    # session for an attacker-controlled path.
    async with _client(ctx) as client:
        r = await client.get('/tutor/a%2Fb', follow_redirects=False)
    assert r.status_code in {303, 404}


# -- _make_lazy_log ---------------------------------------------------------


def test_make_lazy_log_includes_args_in_header(tmp_path: Path):
    args = argparse.Namespace(
        explain_model='ex-model',
        ask_model='as-model',
        web_host='1.2.3.4',
        web_port=9000,
    )
    log = _make_lazy_log(tmp_path, args)
    log.write('first\n')
    log.close()
    text = (tmp_path / 'tutor.log').read_text(encoding='utf-8')
    assert 'explain_model=ex-model' in text
    assert 'ask_model=as-model' in text
    assert 'bind=1.2.3.4:9000' in text


# -- _close_session ---------------------------------------------------------


async def test_close_session_skips_end_banner_when_log_unopened(tmp_path: Path):
    ctx, pool = _build_ctx(tmp_path)
    # Throw away any prior writes that the fixture's append() may have produced.
    log_path = ctx.writing_session.state_dir / 'tutor.log'
    if log_path.exists():
        log_path.unlink()
    # Reset the lazy log so .opened starts False.
    ctx.writing_session.log = LazyLog(log_path, '=== fresh ===\n')
    # Replace pool with a minimal-async-compatible stub
    await _close_session(ctx.writing_session)
    # Log file should never have been touched.
    assert not log_path.exists()
    _ = pool  # suppress unused-var lint


async def test_close_session_writes_end_banner_when_log_opened(tmp_path: Path):
    ctx, _ = _build_ctx(tmp_path)
    log_path = ctx.writing_session.state_dir / 'tutor.log'
    # Force-open by writing something first.
    ctx.writing_session.log.write('mid\n')
    await _close_session(ctx.writing_session)
    text = log_path.read_text(encoding='utf-8')
    assert '=== session end ===' in text


# -- events with no initial threads + ping --------------------------------


async def test_events_emits_ping_on_idle_then_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _ = _build_ctx(tmp_path)
    # No threads in fake pool, so initial_threads block (418->424) is skipped.

    # Drive the 15.0-second wait_for to TimeoutError immediately so a ping
    # frame is emitted. The second call sets stop so the loop exits.
    calls: list[int] = []

    async def fake_wait_for(coro: Any, timeout: float = 0.0) -> tuple[str, str]:  # noqa: ASYNC109
        _ = timeout
        coro.close()  # avoid "coroutine was never awaited" warning
        calls.append(1)
        if len(calls) >= 2:
            ctx.stop_event.set()
        raise TimeoutError

    monkeypatch.setattr('tutor.web.asyncio.wait_for', fake_wait_for)

    async with _client(ctx) as client:
        r = await client.get(_dir_url(ctx, '/events'))
    assert r.status_code == 200
    assert b': ping' in r.content
    # No initial thread_list frame because pool.list_threads() is empty.
    assert b'event: thread_list' not in r.content


# -- writing_sink_does_not_emit_to_view_dir_subscribers ---------------------


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
