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

    from tutor.types import OutputSink


async def stdin_loop(
    sink: OutputSink,
    filter_re: re.Pattern[str] | None,
    stop_event: asyncio.Event,
    *,
    input_file: IO[str] | None = None,
) -> None:
    """Read stdin, persist each surviving line as an unexplained entry."""
    source = input_file or sys.stdin
    last_kept: str | None = None

    while not stop_event.is_set():
        raw = await asyncio.to_thread(source.readline)
        if not raw:
            return
        raw_line = raw.rstrip('\n')

        sink.on_raw_line(raw_line)

        line = raw_line
        if filter_re:
            m = filter_re.search(raw_line)
            if not m:
                continue
            if filter_re.groups and m.group(1) is not None:
                line = m.group(1)
        if not line.strip():
            continue
        if line == last_kept:
            continue
        last_kept = line

        sink.on_entry_appended(TutorEntry(raw=line))
