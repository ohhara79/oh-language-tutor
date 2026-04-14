"""Terminal-mode entry point."""

from __future__ import annotations

import asyncio
import contextlib
import re
import signal
from pathlib import Path
from typing import TYPE_CHECKING

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from tutor.core import _stdin_loop
from tutor.prompts import build_system_prompt
from tutor.session import load_saved_session_id
from tutor.sink import TerminalSink, ansi_enabled

if TYPE_CHECKING:
    import argparse


async def run_terminal(args: argparse.Namespace) -> int:
    """Run in terminal-only mode (default, no ``--gui``)."""
    try:
        filter_re = re.compile(args.filter_regex) if args.filter_regex else None
    except re.PatternError as exc:
        msg = f'oh-language-tutor: invalid --filter-regex: {exc}'
        raise SystemExit(msg) from exc
    system_prompt = build_system_prompt(args)
    resume_id = load_saved_session_id(args)

    state_dir = Path(args.state_dir).expanduser()
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / 'tutor.log'
    session_path = state_dir / 'session.id'

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

        async with ClaudeSDKClient(options=options) as client:
            await _stdin_loop(client, sink, filter_re, stop_event, session_path)

        log.write('=== session end ===\n')

    return 0
