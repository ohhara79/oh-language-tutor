"""Shared stdin processing pipeline.

Reads stdin lines and emits unexplained TutorEntry events. Explanations are
requested on-demand from the web UI; no Claude call happens here.
"""

from __future__ import annotations

import asyncio
import sys
from typing import IO, TYPE_CHECKING

from tutor.types import TutorEntry

if TYPE_CHECKING:
    import re
    from collections.abc import AsyncIterator

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
    input_file:
        An explicit file object to read from instead of ``sys.stdin``.
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
    sink: OutputSink,
    filter_re: re.Pattern[str] | None,
    stop_event: asyncio.Event,
    *,
    use_thread: bool = False,
    input_file: IO[str] | None = None,
) -> None:
    """Read stdin, persist each surviving line as an unexplained entry."""
    last_kept: str | None = None

    async for raw_line in _stdin_line_stream(use_thread=use_thread, input_file=input_file):
        if stop_event.is_set():
            break

        sink.on_raw_line(raw_line)

        if filter_re and not filter_re.search(raw_line):
            continue
        if not raw_line.strip():
            continue
        if raw_line == last_kept:
            continue
        last_kept = raw_line

        sink.on_entry_appended(TutorEntry(raw=raw_line))
