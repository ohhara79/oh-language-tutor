"""Shared dataclasses, protocols, and command types for oh-language-tutor."""

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

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
    """One stdin line persisted for left-pane restoration.

    ``explanation`` is None until the user clicks Explain in the UI.
    """

    raw: str
    explanation: str | None = None
    id: str = field(default_factory=lambda: uuid4().hex)


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
    anchor_id: str = ''  # TutorEntry.id; empty for orphan threads whose anchor entry was deleted
    messages: list[ThreadMessage] = field(default_factory=list)


def format_created_at_utc(created_at: str) -> str:
    """Format a stored ISO-8601 UTC timestamp as 'YYYY-MM-DD HH:MM:SS UTC'."""
    return datetime.datetime.fromisoformat(created_at).astimezone(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')


# ---------------------------------------------------------------------------
# Output sink protocol
# ---------------------------------------------------------------------------


class OutputSink(Protocol):
    """Interface between the core loop and the UI layer."""

    def on_raw_line(self, raw: str) -> None:
        """A new raw line arrived from stdin (passthrough display)."""
        ...

    def on_entry_appended(self, entry: TutorEntry) -> None:
        """A new stdin line was persisted as an unexplained entry."""
        ...

    def on_entry_explained(self, entry: TutorEntry) -> None:
        """An entry's explanation was produced and persisted."""
        ...

    def on_thread_chunk(self, thread_id: str, chunk: str) -> None:
        """A streaming text chunk arrived from a followup thread response."""
        ...

    def on_thread_done(self, thread_id: str, last_assistant: str) -> None:
        """A followup thread response finished streaming.

        ``last_assistant`` is the full assistant text that was just persisted
        (may be empty on error paths). Sinks that rendered raw streaming
        chunks in place use it to swap in a properly-formatted replacement.
        """
        ...

    def on_thread_list(self, threads: list[ThreadMeta]) -> None:
        """The full list of saved threads is available."""
        ...

    def on_tutor_entry_removed(self, anchor_id: str) -> None:
        """A left-pane tutor entry was deleted; the UI should drop it."""
        ...

    def on_error(self, msg: str) -> None:
        """An error occurred that the UI should display."""
        ...


# ---------------------------------------------------------------------------
# Command channel payloads (TUI -> core loop)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OpenThreadCmd:
    """Open a new followup thread anchored to a specific line."""

    thread_id: str
    anchor_id: str  # TutorEntry.id — persisted on ThreadMeta


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


@dataclass(frozen=True, slots=True)
class DeleteTutorEntryCmd:
    """Delete a left-pane tutor entry and cascade-delete its threads."""

    anchor_id: str


Cmd = OpenThreadCmd | ReopenThreadCmd | SendMessageCmd | HideThreadCmd | DeleteThreadCmd | DeleteTutorEntryCmd
