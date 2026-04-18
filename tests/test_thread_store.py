"""Tests for ``tutor.thread_store``."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from tutor.thread_store import ThreadStore, new_thread_id
from tutor.types import ThreadMessage, ThreadMeta

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _meta(
    thread_id: str,
    *,
    anchor_id: str = 'anchor-x',
    anchor_raw: str = 'anchor line',
    session_id: str = 'sid-1',
    created_at: str = '2026-04-18T12:00:00+00:00',
    messages: list[ThreadMessage] | None = None,
) -> ThreadMeta:
    return ThreadMeta(
        thread_id=thread_id,
        anchor_raw=anchor_raw,
        session_id=session_id,
        created_at=created_at,
        anchor_id=anchor_id,
        messages=messages or [],
    )


def test_new_thread_id_format() -> None:
    tid = new_thread_id()
    assert re.fullmatch(r'tutor_thread_\d{14}_[0-9a-f]{8}', tid)


def test_new_thread_id_unique() -> None:
    ids = {new_thread_id() for _ in range(20)}
    assert len(ids) == 20


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    meta = _meta(
        'tutor_thread_20260418120000_deadbeef',
        messages=[
            ThreadMessage(role='user', text='hi'),
            ThreadMessage(role='assistant', text='hello'),
        ],
    )
    store.save_thread(meta)

    loaded = store.load_thread(meta.thread_id)
    assert loaded is not None
    assert loaded.thread_id == meta.thread_id
    assert loaded.anchor_id == meta.anchor_id
    assert loaded.anchor_raw == meta.anchor_raw
    assert loaded.session_id == meta.session_id
    assert loaded.created_at == meta.created_at
    assert loaded.messages == meta.messages


def test_load_missing_thread_returns_none(tmp_path: Path) -> None:
    assert ThreadStore(tmp_path).load_thread('does-not-exist') is None


def test_list_threads_sorted_by_created_at_ascending(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save_thread(_meta('t-b', created_at='2026-04-18T13:00:00+00:00'))
    store.save_thread(_meta('t-a', created_at='2026-04-18T10:00:00+00:00'))
    store.save_thread(_meta('t-c', created_at='2026-04-18T15:00:00+00:00'))

    ids = [m.thread_id for m in store.list_threads()]
    assert ids == ['t-a', 't-b', 't-c']


def test_delete_thread_removes_file(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save_thread(_meta('t-1'))
    store.delete_thread('t-1')
    assert store.load_thread('t-1') is None


def test_delete_thread_missing_is_safe(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.delete_thread('never-existed')  # must not raise
    store.delete_thread('never-existed')  # and still safe on second call


def test_delete_by_anchor_id_removes_matches(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save_thread(_meta('t-1', anchor_id='anchor-a'))
    store.save_thread(_meta('t-2', anchor_id='anchor-a'))
    store.save_thread(_meta('t-3', anchor_id='anchor-b'))

    deleted = store.delete_by_anchor_id('anchor-a')
    assert sorted(deleted) == ['t-1', 't-2']

    remaining = [m.thread_id for m in store.list_threads()]
    assert remaining == ['t-3']


def test_delete_by_anchor_id_no_matches_returns_empty(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save_thread(_meta('t-1', anchor_id='keep'))
    assert store.delete_by_anchor_id('nothing-matches') == []
    assert len(store.list_threads()) == 1


def test_delete_by_anchor_id_empty_string_returns_empty(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    store.save_thread(_meta('t-1', anchor_id=''))
    assert store.delete_by_anchor_id('') == []
    # orphan threads with empty anchor must remain
    assert len(store.list_threads()) == 1


def test_corrupt_thread_json_is_skipped_with_warning(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = ThreadStore(tmp_path)
    store.save_thread(_meta('good-one'))
    (tmp_path / 'broken.json').write_text('not json', encoding='utf-8')

    threads = store.list_threads()
    assert [m.thread_id for m in threads] == ['good-one']
    captured = capsys.readouterr()
    assert 'corrupt thread file' in captured.err


async def test_save_thread_async_roundtrip(tmp_path: Path) -> None:
    store = ThreadStore(tmp_path)
    meta = _meta('t-async', messages=[ThreadMessage(role='user', text='q')])
    await store.save_thread_async(meta)

    loaded = store.load_thread('t-async')
    assert loaded is not None
    assert loaded.messages == meta.messages
