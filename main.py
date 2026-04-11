"""Language tutor for any text stream, backed by the Claude Agent SDK.

Reads a source text stream on stdin (typically piped from another
program — a game, a subtitle stream, a chat log, anything), echoes it
back to stdout, and for each interesting line asks a persistent Claude
session to explain it for a language learner.

See PLAN.md alongside this file for the full design. This module is
the sole Python entry point — no external Python code, and no
source-specific logic. All domain knowledge lives in the optional
--extra-system-prompt file; all audience knowledge is built from the
--source-language / --target-language / --level flags.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import re
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_SESSION_FILE = PROJECT_DIR / 'state' / 'session.id'
DEFAULT_LOG_FILE = PROJECT_DIR / 'state' / 'tutor.log'
DEFAULT_MODEL = 'claude-opus-4-6'
DEFAULT_LEVEL = 'intermediate'
DEFAULT_SKIP_TOKEN = 'SKIP'  # noqa: S105

# ANSI escape helpers (suppressed automatically when stdout is not a TTY).
_RESET = '\033[0m'
_DIM = '\033[2m'
_CYAN = '\033[36m'
_BOLD = '\033[1m'


def build_base_system_prompt(
    source_language: str,
    target_language: str,
    level: str,
    skip_token: str,
) -> str:
    """Build the audience/format half of the system prompt from CLI flags."""
    return f"""You are a private language tutor helping a native {target_language} speaker learn {source_language}. The learner's level is {level}.

Each user message is ONE raw line of text from a stream that may or may not contain actual {source_language} content worth explaining. The stream may also include unrelated noise — engine warnings, log banners, timestamps, debug prints — which should be ignored.

Decision rule:

- If the line is NOT real {source_language} content worth explaining (noise, metadata, technical output, unrelated output), respond with EXACTLY the single word `{skip_token}` and nothing else. Do not wrap it, do not add punctuation, do not explain the decision — just `{skip_token}`.
- Otherwise, produce a short explanation tailored to a {level} {source_language} learner whose native language is {target_language}.

Explanation structure (skip any empty section, stay under 100 words):

  🎯 Translation: <natural {target_language} translation>
  📚 Vocabulary: <2-3 items, {source_language} → {target_language}>
  💡 Expression: <one idiom/slang/grammar pattern, explained in {target_language}>
  🎬 Context:    <one sentence on what the speaker means in THIS moment, referencing earlier lines you've seen in this conversation>

Level guidance:
- beginner:     write almost everything in {target_language}; simple vocabulary; explain even basic words.
- intermediate: bilingual, {target_language}-first; focus on idioms, slang, and cultural references.
- advanced:     explain in plain {source_language}; only use {target_language} for subtle points.

You have a persistent conversation history across every line sent this session, so refer back to prior context naturally (resolving "he"/"she"/"they", noticing callbacks, etc.).
"""  # noqa: E501


def build_system_prompt(args: argparse.Namespace) -> str:
    """Base + optional user-supplied extras."""
    base = build_base_system_prompt(
        args.source_language,
        args.target_language,
        args.level,
        args.skip_token,
    )
    if args.extra_system_prompt:
        extra = Path(args.extra_system_prompt).expanduser().read_text(encoding='utf-8')
        return base + '\n\nADDITIONAL SOURCE-SPECIFIC CONTEXT:\n\n' + extra
    return base


def load_saved_session_id(args: argparse.Namespace) -> str | None:
    """Decide the `resume` value for ClaudeAgentOptions."""
    if args.new_session:
        return None
    if args.resume_id:
        return args.resume_id
    try:
        sid = Path(args.session_file).expanduser().read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        return None
    return sid or None


def save_session_id(path: Path, session_id: str) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session_id + '\n', encoding='utf-8')


def ansi_enabled() -> bool:
    return sys.stdout.isatty() and os.environ.get('NO_COLOR', '') == ''


def print_header(label: str) -> None:
    rule = '─' * 72
    if ansi_enabled():
        sys.stdout.write(f'{_DIM}{_CYAN}── 🎓 {label} {rule[len(label) + 6 :]}{_RESET}\n')
    else:
        sys.stdout.write(f'── 🎓 {label} {rule[len(label) + 6 :]}\n')
    sys.stdout.flush()


def print_footer() -> None:
    if ansi_enabled():
        sys.stdout.write(f'{_DIM}{_CYAN}{"─" * 72}{_RESET}\n\n')
    else:
        sys.stdout.write(f'{"─" * 72}\n\n')
    sys.stdout.flush()


def extract_label(raw_line: str) -> str:
    """Pull a short header label out of a raw line for the separator."""
    m = re.match(r'^\s*([^:]{1,40}):\s*\"', raw_line)
    if m:
        return m.group(1).strip()
    return raw_line[:40].strip() or 'line'


async def stdin_line_stream() -> AsyncIterator[str]:
    """Async generator yielding one stripped line per stdin line, until EOF."""
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    while True:
        raw = await reader.readline()
        if not raw:
            return
        yield raw.decode('utf-8', errors='replace').rstrip('\n')


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog='oh-language-tutor',
        description='Pipe a text stream in; get Claude explanations out.',
    )
    p.add_argument(
        '--source-language',
        required=True,
        help='Full name of the language being learned (e.g. English).',
    )
    p.add_argument(
        '--target-language',
        required=True,
        help="Full name of the learner's native language (e.g. Korean).",
    )
    p.add_argument(
        '--level',
        default=DEFAULT_LEVEL,
        choices=('beginner', 'intermediate', 'advanced'),
        help='Learner proficiency (default: %(default)s).',
    )
    p.add_argument(
        '--extra-system-prompt',
        help='Path to a text file appended to the base system prompt.',
    )
    p.add_argument(
        '--filter-regex',
        help='Only send lines matching this regex to the LLM. Omit to send every line.',
    )
    p.add_argument(
        '--skip-token',
        default=DEFAULT_SKIP_TOKEN,
        help='Sentinel word the LLM emits for non-content lines (default: %(default)s).',
    )
    p.add_argument(
        '--model',
        default=DEFAULT_MODEL,
        help='Claude model id (default: %(default)s).',
    )
    p.add_argument(
        '--session-file',
        default=str(DEFAULT_SESSION_FILE),
        help='Where the session id for cross-run resume is stored.',
    )
    p.add_argument(
        '--log-file',
        default=str(DEFAULT_LOG_FILE),
        help='Append-only log of raw input + explanations.',
    )
    p.add_argument(
        '--new-session',
        action='store_true',
        help='Ignore any saved session id and start fresh.',
    )
    p.add_argument(
        '--resume-id',
        help='Resume a specific session id (overrides --session-file).',
    )
    return p.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    filter_re = re.compile(args.filter_regex) if args.filter_regex else None
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

    last_sent: str | None = None
    saved_session_id = False

    stop_event = asyncio.Event()

    def _handle_sigint() -> None:
        stop_event.set()

    # Windows / restricted env: fall through to default handling.
    with contextlib.suppress(NotImplementedError):
        asyncio.get_running_loop().add_signal_handler(signal.SIGINT, _handle_sigint)

    with log_path.open('a', encoding='utf-8', buffering=1) as log:
        log.write(f'\n=== session start model={args.model} resume={resume_id or "-"} ===\n')

        async with ClaudeSDKClient(options=options) as client:
            async for raw_line in stdin_line_stream():
                if stop_event.is_set():
                    break

                # 1. Passthrough every line to stdout + log.
                sys.stdout.write(raw_line + '\n')
                sys.stdout.flush()
                log.write(raw_line + '\n')

                # 2. Optional Python-side pre-filter.
                if filter_re and not filter_re.search(raw_line):
                    continue
                # 3. Empty lines are never worth an API call.
                if not raw_line.strip():
                    continue
                # 4. Dedup immediate repeats.
                if raw_line == last_sent:
                    continue
                last_sent = raw_line

                # 5. Submit this line as the next user turn.
                await client.query(raw_line)

                # 6. Buffer the whole response so we can inspect the skip token.
                buf: list[str] = []
                try:
                    async for msg in client.receive_response():
                        if isinstance(msg, AssistantMessage):
                            buf.extend(block.text for block in msg.content if isinstance(block, TextBlock))
                        elif isinstance(msg, ResultMessage) and not saved_session_id:
                            try:
                                save_session_id(session_path, msg.session_id)
                                saved_session_id = True
                            except OSError as exc:
                                sys.stderr.write(f'[oh-language-tutor] could not save session id: {exc}\n')
                except Exception as exc:  # noqa: BLE001
                    sys.stderr.write(f'[oh-language-tutor] query failed: {exc}\n')
                    continue

                response = ''.join(buf).strip()
                if not response:
                    continue
                if response.upper() == args.skip_token.upper():
                    continue

                # 7. Not a skip — print explanation block to stdout + log.
                label = extract_label(raw_line)
                print_header(label)
                sys.stdout.write(response + '\n')
                sys.stdout.flush()
                print_footer()

                log.write(f'--- explanation for: {raw_line}\n')
                log.write(response + '\n')
                log.write('---\n')

        log.write('=== session end ===\n')

    return 0


def main() -> None:
    args = parse_args()
    try:
        rc = asyncio.run(run(args))
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == '__main__':
    main()
