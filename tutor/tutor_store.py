"""On-disk persistence for left-pane tutor entries (raw lines + explanations)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from tutor.types import TutorEntry


class TutorStore:
    """Manages ``state/tutor.json`` — the accumulated stream of explained lines."""

    def __init__(self, path: Path) -> None:
        self._path: Path = path

    def load(self) -> list[TutorEntry]:
        """Read all entries from disk.  Returns ``[]`` on missing/corrupt file.

        Legacy entries without an ``id`` field are materialised with a fresh
        UUID so downstream code can always rely on a stable id. The new id is
        not persisted here — call :meth:`migrate` to rewrite the file once.
        """
        try:
            data = json.loads(self._path.read_text(encoding='utf-8'))
            return [
                TutorEntry(
                    raw=e['raw'],
                    explanation=e['explanation'],
                    id=e.get('id') or uuid4().hex,
                )
                for e in data
            ]
        except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError) as exc:
            if not isinstance(exc, FileNotFoundError):
                sys.stderr.write(f'[oh-language-tutor] corrupt tutor file {self._path}: {exc}\n')
            return []

    def append(self, entry: TutorEntry) -> None:
        """Append a single entry and write back atomically."""
        entries = self.load()
        entries.append(entry)
        self._write(entries)

    def delete(self, anchor_id: str) -> bool:
        """Remove the entry matching *anchor_id*. Returns False if not found."""
        entries = self.load()
        kept = [e for e in entries if e.id != anchor_id]
        if len(kept) == len(entries):
            return False
        self._write(kept)
        return True

    def index_of(self, anchor_id: str) -> int | None:
        """Return the current array position of *anchor_id*, or None."""
        for i, e in enumerate(self.load()):
            if e.id == anchor_id:
                return i
        return None

    def migrate(self) -> None:
        """Persist ids for any legacy entries that lack one. Idempotent."""
        try:
            raw = self._path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return
        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(data, list):
            return
        items: list[dict[str, Any]] = [i for i in data if isinstance(i, dict)]  # pyright: ignore[reportUnknownVariableType]
        dirty = False
        for item in items:
            if not item.get('id'):
                item['id'] = uuid4().hex
                dirty = True
        if dirty:
            entries = [TutorEntry(raw=str(i['raw']), explanation=str(i['explanation']), id=str(i['id'])) for i in items]
            self._write(entries)

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
