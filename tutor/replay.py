"""Replay helpers used when a Claude session resume fails.

All fallback-related behaviour lives here.  To remove the feature,
delete this module and the short call to ``connect_with_fallback`` in
``terminal.py`` / ``gui.py`` and the ``except`` / retry block in
``thread_pool.send_message`` that import from it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from claude_agent_sdk import ClaudeSDKClient

if TYPE_CHECKING:
    from typing import TextIO

    from claude_agent_sdk import ClaudeAgentOptions

    from tutor.types import OutputSink, ThreadMessage, TutorEntry


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


async def connect_with_fallback(
    primary: ClaudeAgentOptions,
    *,
    fresh: ClaudeAgentOptions,
    tutor_entries: list[TutorEntry],
    sink: OutputSink,
    log: TextIO,
) -> ClaudeSDKClient:
    """Enter a ``ClaudeSDKClient`` session, falling back and replaying on resume failure.

    Try to enter ``ClaudeSDKClient(primary)``.  If that fails and
    *primary* was a resume attempt (``primary.resume is not None``),
    retry with *fresh*, replay the last ``REPLAY_MAX_TURNS`` entries of
    *tutor_entries* as a single preamble message, and emit a one-line
    fallback notice via ``notify_fallback``.

    If *primary* was not a resume attempt, any failure is raised
    verbatim (no fallback, no replay).

    The caller is responsible for calling ``__aexit__`` on the returned
    client when done.
    """
    client = ClaudeSDKClient(options=primary)
    try:
        await client.__aenter__()
    except Exception:
        if primary.resume is None:
            raise
    else:
        return client

    fresh_client = ClaudeSDKClient(options=fresh)
    await fresh_client.__aenter__()
    all_pairs = [(e.raw, e.explanation) for e in tutor_entries]
    pairs = all_pairs[-REPLAY_MAX_TURNS:]
    if pairs:
        preamble = build_preamble(pairs)
        await fresh_client.query(preamble)
        async for _ in fresh_client.receive_response():
            pass
    notify_fallback(log, sink, total=len(all_pairs), replayed=len(pairs))
    return fresh_client
