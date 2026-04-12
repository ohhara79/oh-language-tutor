"""Core stdin loop and command dispatcher."""

from __future__ import annotations

import asyncio
import contextlib
import re
import signal
import sys
from pathlib import Path
from typing import IO, TYPE_CHECKING

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

from tutor.prompts import build_system_prompt
from tutor.registry import LineRegistry
from tutor.session import load_saved_session_id, save_session_id
from tutor.sink import TerminalSink, ansi_enabled
from tutor.types import (
    Cmd,
    DeleteThreadCmd,
    HideThreadCmd,
    OpenThreadCmd,
    ReopenThreadCmd,
    SendMessageCmd,
)

if TYPE_CHECKING:
    import argparse
    from collections.abc import AsyncIterator

    from tutor.thread_pool import FollowupThreadPool
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
        in GUI mode where ``sys.stdin`` has been redirected to ``/dev/tty``
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


async def _stdin_loop(
    client: ClaudeSDKClient,
    sink: OutputSink,
    registry: LineRegistry,
    filter_re: re.Pattern[str] | None,
    skip_token: str,
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

        line_idx = registry.add_line(raw_line)
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
        if response.upper() == skip_token.upper():
            sink.on_explanation(line_idx, raw_line, response)
            continue

        registry.set_explanation(line_idx, response)
        sink.on_explanation(line_idx, raw_line, response)


# ---------------------------------------------------------------------------
# Command dispatcher
# ---------------------------------------------------------------------------


async def _dispatch_commands(  # pyright: ignore[reportUnusedFunction] - imported at runtime by gui.py
    queue: asyncio.Queue[Cmd],
    pool: FollowupThreadPool,
    stop_event: asyncio.Event,
) -> None:
    """Read commands from the GUI and dispatch to the thread pool."""
    while not stop_event.is_set():
        try:
            cmd = await asyncio.wait_for(queue.get(), timeout=0.1)
        except TimeoutError:
            continue
        match cmd:
            case OpenThreadCmd():
                await pool.open_thread(cmd.thread_id, cmd.anchor_idx)
            case ReopenThreadCmd():
                await pool.reopen_thread(cmd.thread_id)
            case SendMessageCmd():
                await pool.send_message(cmd.thread_id, cmd.text)
            case HideThreadCmd():
                await pool.hide_thread(cmd.thread_id)
            case DeleteThreadCmd():
                await pool.delete_thread(cmd.thread_id)


# ---------------------------------------------------------------------------
# Terminal mode entry point
# ---------------------------------------------------------------------------


async def run_terminal(args: argparse.Namespace) -> int:
    """Run in terminal-only mode (default, no ``--gui``)."""
    try:
        filter_re = re.compile(args.filter_regex) if args.filter_regex else None
    except re.PatternError as exc:
        msg = f'oh-language-tutor: invalid --filter-regex: {exc}'
        raise SystemExit(msg) from exc
    system_prompt = build_system_prompt(args)
    resume_id = load_saved_session_id(args)

    log_path = Path(args.log_file).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    session_path = Path(args.session_file).expanduser()

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=args.model,
        allowed_tools=[],
        resume=resume_id,
    )

    stop_event = asyncio.Event()

    def _handle_sigint() -> None:
        stop_event.set()

    with contextlib.suppress(NotImplementedError):
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, _handle_sigint)

    with log_path.open('a', encoding='utf-8', buffering=1) as log:
        log.write(f'\n=== session start model={args.model} resume={resume_id or "-"} ===\n')

        sink = TerminalSink(log, ansi=ansi_enabled())
        registry = LineRegistry()

        async with ClaudeSDKClient(options=options) as client:
            await _stdin_loop(client, sink, registry, filter_re, args.skip_token, stop_event, session_path)

        log.write('=== session end ===\n')

    return 0
