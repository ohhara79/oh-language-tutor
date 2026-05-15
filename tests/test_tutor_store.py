"""Tests for ``tutor.tutor_store.TutorStore``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tutor.tutor_store import TutorStore
from tutor.types import TutorEntry

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _store(tmp_path: Path) -> TutorStore:
    return TutorStore(tmp_path / 'tutor.json')


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    assert _store(tmp_path).load() == []


def test_append_then_load_preserves_fields(tmp_path: Path) -> None:
    store = _store(tmp_path)
    entry = TutorEntry(raw='raw line', explanation='the explanation', id='fixed-id-1')
    store.append(entry)

    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].id == 'fixed-id-1'
    assert loaded[0].raw == 'raw line'
    assert loaded[0].explanation == 'the explanation'


def test_append_twice_preserves_order(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(TutorEntry(raw='first', explanation='e1', id='id-1'))
    store.append(TutorEntry(raw='second', explanation='e2', id='id-2'))

    loaded = store.load()
    assert [e.id for e in loaded] == ['id-1', 'id-2']


def test_delete_known_id_returns_true_and_removes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(TutorEntry(raw='a', explanation='e', id='keep'))
    store.append(TutorEntry(raw='b', explanation='e', id='drop'))

    assert store.delete('drop') is True
    assert [e.id for e in store.load()] == ['keep']


def test_delete_unknown_id_returns_false(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(TutorEntry(raw='a', explanation='e', id='x'))
    assert store.delete('not-there') is False
    assert len(store.load()) == 1


def test_index_of(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(TutorEntry(raw='a', explanation='e', id='first'))
    store.append(TutorEntry(raw='b', explanation='e', id='second'))

    assert store.index_of('first') == 0
    assert store.index_of('second') == 1
    assert store.index_of('missing') is None


def test_corrupt_json_returns_empty_and_warns(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / 'tutor.json'
    path.write_text('this is not JSON', encoding='utf-8')
    store = TutorStore(path)

    assert store.load() == []
    captured = capsys.readouterr()
    assert 'corrupt tutor file' in captured.err


def test_atomic_write_leaves_no_tmp_files(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(TutorEntry(raw='a', explanation='e', id='x'))
    stragglers = list(tmp_path.glob('*.tmp'))
    assert stragglers == []


async def test_append_async_roundtrip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    await store.append_async(TutorEntry(raw='async-raw', explanation='async-e', id='async-1'))
    loaded = store.load()
    assert [e.id for e in loaded] == ['async-1']


async def test_delete_async_removes_entry(tmp_path: Path) -> None:
    store = _store(tmp_path)
    await store.append_async(TutorEntry(raw='a', explanation='e', id='to-delete'))
    deleted = await store.delete_async('to-delete')
    assert deleted is True
    assert store.load() == []


async def test_delete_async_unknown_id_returns_false(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert await store.delete_async('nope') is False


def test_load_tolerates_null_explanation(tmp_path: Path) -> None:
    path = tmp_path / 'tutor.json'
    path.write_text(
        '[{"id": "u-1", "raw": "unexplained", "explanation": null}]',
        encoding='utf-8',
    )
    store = TutorStore(path)
    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].explanation is None


def test_load_tolerates_missing_explanation_key(tmp_path: Path) -> None:
    path = tmp_path / 'tutor.json'
    path.write_text('[{"id": "u-1", "raw": "unexplained"}]', encoding='utf-8')
    store = TutorStore(path)
    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].explanation is None


async def test_update_explanation_async_sets_explanation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    await store.append_async(TutorEntry(raw='raw', id='to-explain'))
    updated = await store.update_explanation_async('to-explain', 'the meaning')
    assert updated is True
    loaded = store.load()
    assert loaded[0].explanation == 'the meaning'


async def test_update_explanation_async_unknown_returns_false(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert await store.update_explanation_async('missing', 'x') is False
