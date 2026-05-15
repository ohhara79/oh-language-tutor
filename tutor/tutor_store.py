"""On-disk persistence for left-pane tutor entries (raw lines + explanations)."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from tutor.types import TutorEntry


class TutorStore:
    """Manages ``state/tutor.json`` — the accumulated stream of explained lines."""

    def __init__(self, path: Path) -> None:
        self._path: Path = path
        self._cached_entries: list[TutorEntry] | None = None
        self._cached_key: tuple[float, int] | None = None
        self._write_lock: asyncio.Lock | None = None

    def _get_write_lock(self) -> asyncio.Lock:
        if self._write_lock is None:
            self._write_lock = asyncio.Lock()
        return self._write_lock

    def load(self) -> list[TutorEntry]:
        """Read all entries from disk.  Returns ``[]`` on missing/corrupt file.

        Memoized by (mtime, size) so repeated calls in the same UI click
        (e.g. ``_open_new_thread`` + ``pool.open_thread``) don't reparse
        hundreds of KB of JSON.  An external edit will change the stat
        key and trigger a fresh parse.
        """
        try:
            st = self._path.stat()
        except FileNotFoundError:
            self._cached_entries = []
            self._cached_key = None
            return []

        key = (st.st_mtime, st.st_size)
        if self._cached_entries is not None and self._cached_key == key:
            return list(self._cached_entries)

        try:
            data = json.loads(self._path.read_text(encoding='utf-8'))
            entries = [TutorEntry(raw=e['raw'], explanation=e.get('explanation'), id=e['id']) for e in data]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            sys.stderr.write(f'[oh-language-tutor] corrupt tutor file {self._path}: {exc}\n')
            return []

        self._cached_entries = entries
        self._cached_key = key
        return list(entries)

    def append(self, entry: TutorEntry) -> None:
        """Append a single entry and write back atomically."""
        entries = self.load()
        entries.append(entry)
        self._write(entries)

    async def append_async(self, entry: TutorEntry) -> None:
        """Async variant that runs the disk write on a worker thread."""
        async with self._get_write_lock():
            entries = self.load()
            entries.append(entry)
            await asyncio.to_thread(self._write, entries)

    def delete(self, anchor_id: str) -> bool:
        """Remove the entry matching *anchor_id*. Returns False if not found."""
        entries = self.load()
        kept = [e for e in entries if e.id != anchor_id]
        if len(kept) == len(entries):
            return False
        self._write(kept)
        return True

    async def delete_async(self, anchor_id: str) -> bool:
        """Async variant that runs the disk write on a worker thread."""
        async with self._get_write_lock():
            entries = self.load()
            kept = [e for e in entries if e.id != anchor_id]
            if len(kept) == len(entries):
                return False
            await asyncio.to_thread(self._write, kept)
            return True

    async def update_explanation_async(self, entry_id: str, explanation: str) -> bool:
        """Set the explanation for *entry_id*. Returns False if not found."""
        async with self._get_write_lock():
            entries = self.load()
            for e in entries:
                if e.id == entry_id:
                    e.explanation = explanation
                    await asyncio.to_thread(self._write, entries)
                    return True
            return False

    def index_of(self, anchor_id: str) -> int | None:
        """Return the current array position of *anchor_id*, or None."""
        for i, e in enumerate(self.load()):
            if e.id == anchor_id:
                return i
        return None

    def load_tail(self, n: int) -> tuple[list[TutorEntry], bool]:
        """Return the last *n* entries plus a ``has_more`` flag."""
        entries = self.load()
        if n <= 0 or not entries:
            return ([], False)
        tail = entries[-n:]
        return (tail, len(entries) > n)

    def load_before(self, anchor_id: str, n: int) -> tuple[list[TutorEntry], bool] | None:
        """Entries immediately older than *anchor_id*, oldest-first.

        Returns ``None`` if *anchor_id* is not present; the caller should
        translate that to a 404.
        """
        entries = self.load()
        idx = next((i for i, e in enumerate(entries) if e.id == anchor_id), None)
        if idx is None:
            return None
        start = max(0, idx - n)
        return (entries[start:idx], start > 0)

    def _write(self, entries: list[TutorEntry]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [{'id': e.id, 'raw': e.raw, 'explanation': e.explanation} for e in entries]
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=self._path.parent,
            suffix='.tmp',
            delete=False,
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp.name)
        tmp_path.rename(self._path)
        try:
            st = self._path.stat()
        except FileNotFoundError:
            self._cached_entries = None
            self._cached_key = None
            return
        self._cached_entries = list(entries)
        self._cached_key = (st.st_mtime, st.st_size)
