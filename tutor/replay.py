"""Replay helpers used when a thread Claude session resume fails."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO

    from tutor.types import OutputSink, ThreadMessage


REPLAY_MAX_TURNS = 100


def build_preamble(turns: list[tuple[str, str]]) -> str:
    """Compose a single user message that replays prior turns as text.

    *turns* is a list of ``(user_text, assistant_text)`` pairs.  The
    caller is responsible for trimming to ``REPLAY_MAX_TURNS`` before
    calling.

    Returns ``''`` for an empty list so the caller can skip replay
    without a special branch.
    """
    if not turns:
        return ''
    parts: list[str] = [
        'Here is our prior conversation. Please continue from where we left off.',
        '',
    ]
    for user_text, assistant_text in turns:
        parts.append(f'User: {user_text}')
        parts.append(f'Assistant: {assistant_text}')
        parts.append('')
    parts.append('(continue from here)')
    return '\n'.join(parts)


def pairs_from_thread(messages: list[ThreadMessage]) -> list[tuple[str, str]]:
    """Pair alternating user/assistant thread messages into ``(user, assistant)`` tuples.

    Unmatched trailing user messages (no assistant reply yet) are dropped.
    No trimming is applied — the caller is responsible for slicing to
    ``REPLAY_MAX_TURNS`` if desired.
    """
    pairs: list[tuple[str, str]] = []
    pending_user: str | None = None
    for msg in messages:
        if msg.role == 'user':
            pending_user = msg.text
        elif msg.role == 'assistant' and pending_user is not None:
            pairs.append((pending_user, msg.text))
            pending_user = None
    return pairs


def notify_fallback(log: TextIO, sink: OutputSink, *, total: int, replayed: int) -> None:
    """Emit a one-line notice to the session log and the UI sink."""
    msg = f'resume failed; replayed {replayed}/{total} turns into a new session'
    log.write(f'=== {msg} ===\n')
    sink.on_error(msg)
