"""On-disk persistence for followup thread metadata."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from tutor.types import ThreadMessage, ThreadMeta


def new_thread_id() -> str:
    """Generate a new thread id in the canonical ``tutor_thread_<UTC>_<hex>`` form.

    The sortable UTC timestamp prefix (``YYYYMMDDHHMMSS``) means thread files on
    disk list in chronological order; the 8-char hex suffix prevents collisions
    within the same second.
    """
    ts = datetime.now(UTC).strftime('%Y%m%d%H%M%S')
    return f'tutor_thread_{ts}_{uuid4().hex[:8]}'


class ThreadStore:
    """Manages per-thread JSON files in ``state/threads/``."""

    def __init__(self, threads_dir: Path) -> None:
        self._dir: Path = threads_dir
        self._write_lock: asyncio.Lock | None = None

    def _get_write_lock(self) -> asyncio.Lock:
        if self._write_lock is None:
            self._write_lock = asyncio.Lock()
        return self._write_lock

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def list_threads(self) -> list[ThreadMeta]:
        """Read all thread JSON files, sorted by created_at descending."""
        self._ensure_dir()
        threads: list[ThreadMeta] = []
        for p in self._dir.glob('*.json'):
            meta = self._load_file(p)
            if meta is not None:
                threads.append(meta)
        threads.sort(key=lambda t: t.created_at)
        return threads

    def load_thread(self, thread_id: str) -> ThreadMeta | None:
        """Load a single thread by id, or None if missing/corrupt."""
        return self._load_file(self._path(thread_id))

    def save_thread(self, meta: ThreadMeta) -> None:
        """Write (or overwrite) a thread JSON file atomically."""
        self._ensure_dir()
        data: dict[str, Any] = {
            'thread_id': meta.thread_id,
            'anchor_id': meta.anchor_id,
            'anchor_raw': meta.anchor_raw,
            'session_id': meta.session_id,
            'created_at': meta.created_at,
            'messages': [{'role': m.role, 'text': m.text} for m in meta.messages],
        }
        self._write(self._path(meta.thread_id), data)

    async def save_thread_async(self, meta: ThreadMeta) -> None:
        """Async variant that runs the disk write on a worker thread."""
        async with self._get_write_lock():
            await asyncio.to_thread(self.save_thread, meta)

    def delete_thread(self, thread_id: str) -> None:
        """Remove a thread JSON file from disk."""
        p = self._path(thread_id)
        p.unlink(missing_ok=True)

    def delete_by_anchor_id(self, anchor_id: str) -> list[str]:
        """Delete every thread file whose anchor_id matches. Returns deleted thread_ids."""
        if not anchor_id:
            return []
        deleted: list[str] = []
        self._ensure_dir()
        for p in self._dir.glob('*.json'):
            meta = self._load_file(p)
            if meta is not None and meta.anchor_id == anchor_id:
                p.unlink(missing_ok=True)
                deleted.append(meta.thread_id)
        return deleted

    def _path(self, thread_id: str) -> Path:
        return self._dir / f'{thread_id}.json'

    def _write(self, target: Path, data: dict[str, Any]) -> None:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=self._dir,
            suffix='.tmp',
            delete=False,
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp.name)
        tmp_path.rename(target)

    def _load_file(self, path: Path) -> ThreadMeta | None:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            messages = [ThreadMessage(role=m['role'], text=m['text']) for m in data.get('messages', [])]
            return ThreadMeta(
                thread_id=data['thread_id'],
                anchor_raw=data['anchor_raw'],
                session_id=data['session_id'],
                created_at=data['created_at'],
                anchor_id=data['anchor_id'],
                messages=messages,
            )
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
            sys.stderr.write(f'[oh-language-tutor] corrupt thread file {path}: {exc}\n')
            return None
