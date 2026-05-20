"""Tests for ``tutor.web_sink``."""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING

from tutor.tutor_store import TutorStore
from tutor.types import ThreadMessage, ThreadMeta, TutorEntry
from tutor.web_sink import _SUBSCRIBER_QUEUE_MAX, WebSink

if TYPE_CHECKING:
    from pathlib import Path

    from jinja2 import Environment


def _sink(tmp_path: Path, env: Environment) -> tuple[WebSink, io.StringIO, TutorStore]:
    log = io.StringIO()
    store = TutorStore(tmp_path / 'tutor.json')
    return WebSink(log=log, tutor_store=store, env=env, view_dir='test-dir'), log, store


# -- subscription management ------------------------------------------------


def test_subscribe_returns_queue_added_to_subs(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    assert isinstance(q, asyncio.Queue)
    sink.unsubscribe(q)
    # Broadcasts after unsubscribe don't queue anything
    sink.on_raw_line('line')  # no broadcast
    assert q.empty()


async def test_broadcast_delivers_to_all_subscribers(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    q1 = sink.subscribe()
    q2 = sink.subscribe()
    sink.on_error('something')
    ev1, frag1 = await q1.get()
    ev2, frag2 = await q2.get()
    assert ev1 == ev2 == 'error'
    assert frag1 == frag2
    assert '\n' not in frag1 and '\r' not in frag1
    assert 'something' in frag1


# -- protocol methods --------------------------------------------------------


def test_on_raw_line_writes_log_only_no_broadcast(tmp_path: Path, jinja_env: Environment):
    sink, log, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    sink.on_raw_line('hello')
    assert log.getvalue() == 'hello\n'
    assert q.empty()


async def test_on_entry_appended_persists_and_broadcasts(tmp_path: Path, jinja_env: Environment):
    sink, _, store = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    entry = TutorEntry(raw='raw line', id='id-1')
    sink.on_entry_appended(entry)
    await sink.flush_pending_writes()

    event, fragment = await q.get()
    assert event == 'entry_appended'
    assert 'class="line"' in fragment
    assert 'id="line-id-1"' in fragment
    assert 'raw line' in fragment
    assert 'Explain' in fragment  # unexplained variant shows Explain button

    entries = store.load()
    assert len(entries) == 1
    assert entries[0].raw == 'raw line'
    assert entries[0].explanation is None


async def test_on_entry_explained_broadcasts_oob_swap(tmp_path: Path, jinja_env: Environment):
    sink, log, store = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    entry = TutorEntry(raw='raw', explanation='the *meaning*', id='id-2')
    sink.on_entry_explained(entry)

    event, fragment = await q.get()
    assert event == 'entry_explained'
    assert 'id="line-id-2"' in fragment
    assert 'hx-swap-oob="outerHTML"' in fragment
    assert '--- explanation for: raw' in log.getvalue()
    # Sink should not persist on its own — endpoint owns persistence.
    assert store.load() == []


async def test_on_thread_chunk_broadcasts_escaped_fragment(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    sink.on_thread_chunk('tid-1', '<script>x</script>')
    event, fragment = await q.get()
    assert event == 'thread_chunk'
    assert 'msg-stream-tid-1' in fragment
    assert '&lt;script&gt;' in fragment
    assert '<script>x</script>' not in fragment


async def test_on_thread_done_with_text_renders_markdown(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    sink.on_thread_done('tid', '**bold**')
    event, fragment = await q.get()
    assert event == 'thread_done'
    assert 'hx-swap-oob="outerHTML:#msg-stream-tid"' in fragment
    assert '<strong>bold</strong>' in fragment


async def test_on_thread_done_empty_text_empty_placeholder(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    sink.on_thread_done('tid', '')
    event, fragment = await q.get()
    assert event == 'thread_done'
    assert 'hx-swap-oob="outerHTML:#msg-stream-tid"' in fragment
    assert fragment.endswith('></div>')


async def test_on_thread_list_caches_and_broadcasts(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    meta = ThreadMeta(
        thread_id='t1',
        anchor_raw='hi',
        session_id='s1',
        created_at='2026-04-18T00:00:00+00:00',
        anchor_id='a1',
        messages=[ThreadMessage(role='user', text='what?')],
    )
    sink.on_thread_list([meta])
    event, _ = await q.get()
    assert event == 'thread_list'
    assert [m.thread_id for m in sink.latest_thread_list()] == ['t1']


async def test_on_tutor_entry_removed_broadcasts_delete_oob(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    sink.on_tutor_entry_removed('anchor-xyz')
    event, fragment = await q.get()
    assert event == 'tutor_entry_removed'
    assert 'id="line-anchor-xyz"' in fragment
    assert 'hx-swap-oob="delete"' in fragment


async def test_on_error_renders_toast(tmp_path: Path, jinja_env: Environment):
    sink, log, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    sink.on_error('bad thing')
    event, fragment = await q.get()
    assert event == 'error'
    assert 'toast' in fragment
    assert 'bad thing' in fragment
    assert '[error] bad thing' in log.getvalue()


# -- render_line -------------------------------------------------------------


def test_render_line_unexplained_shows_explain_button(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    html = sink.render_line(TutorEntry(raw='raw', id='x'))
    assert 'Explain' in html
    assert 'Ask' not in html


def test_render_line_explained_shows_ask_button(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    html = sink.render_line(TutorEntry(raw='raw', explanation='meaning', id='x'))
    assert 'Ask' in html
    assert 'Explain' not in html
    assert 'meaning' in html


async def test_on_explain_chunk_broadcasts_escaped_fragment(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    sink.on_explain_chunk('e-1', '<b>x</b>')
    event, fragment = await q.get()
    assert event == 'explain_chunk'
    assert 'explain-stream-e-1' in fragment
    assert '&lt;b&gt;x&lt;/b&gt;' in fragment
    assert '<b>x</b>' not in fragment


async def test_on_explain_aborted_emits_oob_unexplained_variant(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    entry = TutorEntry(raw='raw', id='aborted-1')
    sink.on_explain_aborted(entry)
    event, fragment = await q.get()
    assert event == 'explain_aborted'
    assert 'id="line-aborted-1"' in fragment
    assert 'hx-swap-oob="outerHTML"' in fragment
    assert 'Explain' in fragment  # reverted to unexplained variant


async def test_on_entry_explanation_cleared_emits_oob_unexplained(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    entry = TutorEntry(raw='raw line', id='cleared-1')
    sink.on_entry_explanation_cleared(entry)
    event, fragment = await q.get()
    assert event == 'entry_explanation_cleared'
    assert 'id="line-cleared-1"' in fragment
    assert 'hx-swap-oob="outerHTML"' in fragment
    assert 'Explain' in fragment


async def test_flush_pending_writes_no_outstanding_is_noop(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    # No pending tasks — should return immediately without raising.
    await sink.flush_pending_writes()


async def test_track_explain_clears_when_done(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)

    async def quick() -> None:
        return None

    task = asyncio.create_task(quick())
    sink.track_explain(task)
    # Internal state: pending set tracks the task
    assert task in sink._pending_explains
    await sink.flush_pending_writes()
    # Done-callback removes it
    assert task not in sink._pending_explains


# -- subscriber backpressure -------------------------------------------------


def test_slow_subscriber_dropped_when_queue_full(tmp_path: Path, jinja_env: Environment):
    sink, log, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    # Fill the queue to capacity without draining
    for i in range(_SUBSCRIBER_QUEUE_MAX):
        q.put_nowait(('filler', str(i)))
    # Next broadcast triggers QueueFull → subscriber dropped + logged
    sink.on_error('overflow')
    assert '[warn] dropping error for slow subscriber' in log.getvalue()
    # Second broadcast shows the dropped subscriber is no longer in set
    log.truncate(0)
    log.seek(0)
    sink.on_error('again')
    assert '[warn] dropping' not in log.getvalue()
