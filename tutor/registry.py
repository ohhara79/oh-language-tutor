"""In-memory line registry for tracking processed stdin lines."""

from __future__ import annotations

from collections import deque

from tutor.types import LineRecord


class LineRegistry:
    """Ordered collection of :class:`LineRecord` objects.

    Allows the GUI to refer to lines by index and threads to pull
    recent context for system-prompt injection.
    """

    def __init__(self) -> None:
        self._deque: deque[LineRecord] = deque()
        self._index: dict[int, LineRecord] = {}
        self._next_idx: int = 0

    def add_line(self, raw: str) -> int:
        """Register a new raw line and return its index."""
        idx = self._next_idx
        self._next_idx += 1
        record = LineRecord(idx=idx, raw=raw)
        self._deque.append(record)
        self._index[idx] = record
        return idx

    def set_explanation(self, idx: int, text: str) -> None:
        """Attach an explanation to a previously registered line."""
        rec = self._index.get(idx)
        if rec is not None:
            rec.explanation = text

    def recent(self, n: int = 20) -> list[LineRecord]:
        """Return the last *n* lines (oldest first)."""
        items = list(self._deque)
        return items[-n:]

    def get(self, idx: int) -> LineRecord | None:
        """Look up a line by its index."""
        return self._index.get(idx)
