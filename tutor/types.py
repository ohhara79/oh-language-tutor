"""Shared dataclasses, protocols, and command types for oh-language-tutor."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

# ---------------------------------------------------------------------------
# Line registry record
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LineRecord:
    """One processed line from the stdin stream."""

    idx: int
    raw: str
    explanation: str | None = None
    timestamp: float = field(default_factory=time.monotonic)


@dataclass(slots=True)
class TutorEntry:
    """One explained line persisted for left-pane restoration."""

    line_idx: int
    raw: str
    explanation: str


# ---------------------------------------------------------------------------
# Thread persistence
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ThreadMessage:
    """One turn in a followup thread conversation."""

    role: str  # "user" | "assistant"
    text: str


@dataclass(slots=True)
class ThreadMeta:
    """Persisted metadata for a followup thread."""

    thread_id: str
    anchor_raw: str
    session_id: str
    created_at: str  # ISO-8601 datetime string
    messages: list[ThreadMessage] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Output sink protocol
# ---------------------------------------------------------------------------


class OutputSink(Protocol):
    """Interface between the core loop and the UI layer."""

    def on_raw_line(self, raw: str) -> None:
        """A new raw line arrived from stdin (passthrough display)."""
        ...

    def on_explanation(self, line_idx: int, raw: str, text: str) -> None:
        """An explanation was produced for a line."""
        ...

    def on_thread_chunk(self, thread_id: str, chunk: str) -> None:
        """A streaming text chunk arrived from a followup thread response."""
        ...

    def on_thread_done(self, thread_id: str) -> None:
        """A followup thread response finished streaming."""
        ...

    def on_thread_list(self, threads: list[ThreadMeta]) -> None:
        """The full list of saved threads is available."""
        ...

    def on_error(self, msg: str) -> None:
        """An error occurred that the UI should display."""
        ...


# ---------------------------------------------------------------------------
# Command channel payloads (GUI -> core loop)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OpenThreadCmd:
    """Open a new followup thread anchored to a specific line."""

    thread_id: str
    anchor_idx: int


@dataclass(frozen=True, slots=True)
class ReopenThreadCmd:
    """Reopen a previously saved thread from disk."""

    thread_id: str


@dataclass(frozen=True, slots=True)
class SendMessageCmd:
    """Send a user message to an open followup thread."""

    thread_id: str
    text: str


@dataclass(frozen=True, slots=True)
class HideThreadCmd:
    """Hide the active thread (disconnect session, keep metadata on disk)."""

    thread_id: str


@dataclass(frozen=True, slots=True)
class DeleteThreadCmd:
    """Permanently delete a thread (disconnect + remove from disk)."""

    thread_id: str


Cmd = OpenThreadCmd | ReopenThreadCmd | SendMessageCmd | HideThreadCmd | DeleteThreadCmd
