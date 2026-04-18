"""Shared stdin processing pipeline used by both terminal and TUI modes."""

from __future__ import annotations

import asyncio
import sys
from typing import IO, TYPE_CHECKING

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

from tutor.session import save_session_id

if TYPE_CHECKING:
    import re
    from collections.abc import AsyncIterator
    from pathlib import Path

    from tutor.types import OutputSink


# ---------------------------------------------------------------------------
# Async stdin reader
# ---------------------------------------------------------------------------


async def _stdin_line_stream(
    *,
    use_thread: bool = False,
    input_file: IO[str] | None = None,
) -> AsyncIterator[str]:
    """Async generator yielding one stripped line per stdin line, until EOF.

    Parameters
    ----------
    use_thread:
        When ``True`` stdin is read in a background thread via blocking I/O
        so that the file-descriptor is **not** switched to non-blocking mode.
        This avoids ``BlockingIOError`` in Textual's input driver which
        shares the same event-loop.
    input_file:
        An explicit file object to read from instead of ``sys.stdin``.  Used
        in TUI mode where ``sys.stdin`` has been redirected to ``/dev/tty``
        for Textual, and the original piped input is read from a saved fd.
    """
    source = input_file or sys.stdin
    if use_thread:
        loop = asyncio.get_running_loop()
        while True:
            raw = await loop.run_in_executor(None, source.readline)
            if not raw:
                return
            yield raw.rstrip('\n')
    else:
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, source)
        while True:
            raw = await reader.readline()
            if not raw:
                return
            yield raw.decode('utf-8', errors='replace').rstrip('\n')


# ---------------------------------------------------------------------------
# Main stdin processing loop
# ---------------------------------------------------------------------------


async def stdin_loop(
    client: ClaudeSDKClient,
    sink: OutputSink,
    filter_re: re.Pattern[str] | None,
    stop_event: asyncio.Event,
    session_path: Path,
    *,
    use_thread: bool = False,
    input_file: IO[str] | None = None,
) -> None:
    """Read stdin, query Claude, emit events to the sink."""
    last_sent: str | None = None
    saved_session_id = False

    async for raw_line in _stdin_line_stream(use_thread=use_thread, input_file=input_file):
        if stop_event.is_set():
            break

        sink.on_raw_line(raw_line)

        if filter_re and not filter_re.search(raw_line):
            continue
        if not raw_line.strip():
            continue
        if raw_line == last_sent:
            continue
        last_sent = raw_line

        buf: list[str] = []
        try:
            await client.query(raw_line)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    buf.extend(block.text for block in msg.content if isinstance(block, TextBlock))
                elif isinstance(msg, ResultMessage) and not saved_session_id:
                    try:
                        save_session_id(session_path, msg.session_id)
                        saved_session_id = True
                    except OSError as exc:
                        sink.on_error(f'could not save session id: {exc}')
        except Exception as exc:  # noqa: BLE001
            sink.on_error(f'query failed: {exc}')
            continue

        response = ''.join(buf).strip()
        if not response:
            continue
        sink.on_explanation(raw_line, response)
