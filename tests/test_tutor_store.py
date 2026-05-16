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


async def test_update_explanation_async_sets_explanation_and_audience(tmp_path: Path) -> None:
    store = _store(tmp_path)
    await store.append_async(TutorEntry(raw='raw', id='to-explain'))
    updated = await store.update_explanation_async(
        'to-explain',
        'the meaning',
        source_language='English',
        target_language='Korean',
        level='advanced',
    )
    assert updated is True
    [loaded] = store.load()
    assert loaded.explanation == 'the meaning'
    assert loaded.source_language == 'English'
    assert loaded.target_language == 'Korean'
    assert loaded.level == 'advanced'


async def test_update_explanation_async_unknown_returns_false(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = await store.update_explanation_async(
        'missing',
        'x',
        source_language='English',
        target_language='Korean',
        level='intermediate',
    )
    assert result is False


def test_load_tolerates_missing_audience_keys(tmp_path: Path) -> None:
    path = tmp_path / 'tutor.json'
    path.write_text(
        '[{"id": "legacy-1", "raw": "old line", "explanation": "old meaning"}]',
        encoding='utf-8',
    )
    store = TutorStore(path)
    [loaded] = store.load()
    assert loaded.explanation == 'old meaning'
    assert loaded.source_language is None
    assert loaded.target_language is None
    assert loaded.level is None


def test_append_then_load_preserves_audience(tmp_path: Path) -> None:
    store = _store(tmp_path)
    entry = TutorEntry(
        raw='raw',
        explanation='e',
        id='id-1',
        source_language='Spanish',
        target_language='Korean',
        level='beginner',
    )
    store.append(entry)
    [loaded] = store.load()
    assert loaded.source_language == 'Spanish'
    assert loaded.target_language == 'Korean'
    assert loaded.level == 'beginner'


async def test_clear_explanation_async_resets_explanation_and_audience(tmp_path: Path) -> None:
    store = _store(tmp_path)
    await store.append_async(
        TutorEntry(
            raw='raw',
            explanation='meaning',
            id='id-1',
            source_language='English',
            target_language='Korean',
            level='intermediate',
        ),
    )
    cleared = await store.clear_explanation_async('id-1')
    assert cleared is True
    [loaded] = store.load()
    assert loaded.raw == 'raw'  # raw line preserved
    assert loaded.explanation is None
    assert loaded.source_language is None
    assert loaded.target_language is None
    assert loaded.level is None


async def test_clear_explanation_async_unknown_returns_false(tmp_path: Path) -> None:
    store = _store(tmp_path)
    await store.append_async(TutorEntry(raw='r', explanation='e', id='other'))
    assert await store.clear_explanation_async('missing') is False
    # Existing entry untouched
    [loaded] = store.load()
    assert loaded.explanation == 'e'


def test_load_before_returns_older_entries_oldest_first(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(5):
        store.append(TutorEntry(raw=f'r-{i}', id=f'id-{i}'))
    result = store.load_before('id-3', 2)
    assert result is not None
    older, has_more = result
    assert [e.id for e in older] == ['id-1', 'id-2']
    assert has_more is True


def test_load_before_at_start_reports_no_more(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(3):
        store.append(TutorEntry(raw=f'r-{i}', id=f'id-{i}'))
    result = store.load_before('id-2', 10)
    assert result is not None
    older, has_more = result
    assert [e.id for e in older] == ['id-0', 'id-1']
    assert has_more is False


def test_load_before_first_entry_returns_empty(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(TutorEntry(raw='r-0', id='id-0'))
    store.append(TutorEntry(raw='r-1', id='id-1'))
    result = store.load_before('id-0', 5)
    assert result is not None
    older, has_more = result
    assert older == []
    assert has_more is False


def test_load_before_unknown_returns_none(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(TutorEntry(raw='r', id='id-1'))
    assert store.load_before('missing', 5) is None


def test_load_uses_stat_cache_on_repeated_reads(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(TutorEntry(raw='r', id='id-1'))
    first = store.load()
    second = store.load()
    # Both reads see the same content but the cached path returns a copy,
    # not the same list — confirm equality not identity.
    assert [e.id for e in first] == [e.id for e in second]
    assert first is not second  # load() returns a fresh list each call


def test_load_tail_zero_returns_empty(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(TutorEntry(raw='r', id='id-1'))
    tail, has_more = store.load_tail(0)
    assert tail == []
    assert has_more is False


def test_load_tail_with_has_more_flag(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(5):
        store.append(TutorEntry(raw=f'r-{i}', id=f'id-{i}'))
    tail, has_more = store.load_tail(2)
    assert [e.id for e in tail] == ['id-3', 'id-4']
    assert has_more is True


def test_load_tail_n_exceeds_total_no_more(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(TutorEntry(raw='r', id='only'))
    tail, has_more = store.load_tail(10)
    assert [e.id for e in tail] == ['only']
    assert has_more is False
