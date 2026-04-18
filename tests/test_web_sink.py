"""Tests for ``tutor.web_sink``."""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING

from tutor.tutor_store import TutorStore
from tutor.types import ThreadMessage, ThreadMeta
from tutor.web_sink import _SUBSCRIBER_QUEUE_MAX, WebSink

if TYPE_CHECKING:
    from pathlib import Path

    from jinja2 import Environment


def _sink(tmp_path: Path, env: Environment) -> tuple[WebSink, io.StringIO, TutorStore]:
    log = io.StringIO()
    store = TutorStore(tmp_path / 'tutor.json')
    return WebSink(log=log, tutor_store=store, env=env), log, store


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


async def test_on_explanation_persists_and_broadcasts(tmp_path: Path, jinja_env: Environment):
    sink, log, store = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    sink.on_explanation('raw', 'the *meaning*')
    await sink.flush_pending_writes()

    event, fragment = await q.get()
    assert event == 'explanation'
    assert 'class="line"' in fragment
    assert 'raw' in fragment
    assert '--- explanation for: raw' in log.getvalue()

    entries = store.load()
    assert len(entries) == 1
    assert entries[0].raw == 'raw'


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
    assert 'id="msg-stream-tid"' in fragment
    assert '<strong>bold</strong>' in fragment


async def test_on_thread_done_empty_text_empty_placeholder(tmp_path: Path, jinja_env: Environment):
    sink, _, _ = _sink(tmp_path, jinja_env)
    q = sink.subscribe()
    sink.on_thread_done('tid', '')
    event, fragment = await q.get()
    assert event == 'thread_done'
    assert 'id="msg-stream-tid"' in fragment
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
