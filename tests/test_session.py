"""Tests for ``tutor.session``."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from tutor.session import load_saved_session_id, save_session_id

if TYPE_CHECKING:
    from pathlib import Path


def _ns(
    state_dir: Path,
    *,
    new_session: bool = False,
    resume_id: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        state_dir=str(state_dir),
        new_session=new_session,
        resume_id=resume_id,
    )


def test_new_session_returns_none_even_if_file_exists(tmp_path: Path) -> None:
    (tmp_path / 'session.id').write_text('should-be-ignored\n', encoding='utf-8')
    assert load_saved_session_id(_ns(tmp_path, new_session=True)) is None


def test_resume_id_wins_over_session_file(tmp_path: Path) -> None:
    (tmp_path / 'session.id').write_text('on-disk\n', encoding='utf-8')
    assert load_saved_session_id(_ns(tmp_path, resume_id='explicit')) == 'explicit'


def test_missing_session_file_returns_none(tmp_path: Path) -> None:
    assert load_saved_session_id(_ns(tmp_path)) is None


def test_existing_session_file_read_and_stripped(tmp_path: Path) -> None:
    (tmp_path / 'session.id').write_text('sid-123\n', encoding='utf-8')
    assert load_saved_session_id(_ns(tmp_path)) == 'sid-123'


def test_empty_session_file_returns_none(tmp_path: Path) -> None:
    (tmp_path / 'session.id').write_text('', encoding='utf-8')
    assert load_saved_session_id(_ns(tmp_path)) is None


def test_save_session_id_creates_parent_and_trailing_newline(tmp_path: Path) -> None:
    target = tmp_path / 'nested' / 'deeper' / 'session.id'
    save_session_id(target, 'sid-xyz')
    assert target.read_text(encoding='utf-8') == 'sid-xyz\n'


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    save_session_id(tmp_path / 'session.id', 'roundtrip-sid')
    assert load_saved_session_id(_ns(tmp_path)) == 'roundtrip-sid'
