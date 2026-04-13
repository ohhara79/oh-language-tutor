"""CLI argument parsing for oh-language-tutor."""

from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STATE_DIR = PROJECT_DIR / 'state'
DEFAULT_MODEL = 'claude-opus-4-6'
DEFAULT_LEVEL = 'intermediate'
DEFAULT_SKIP_TOKEN = 'SKIP'  # noqa: S105


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments and return an ``argparse.Namespace``."""
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
        '--state-dir',
        default=str(DEFAULT_STATE_DIR),
        help='Directory for all persistent state files (default: %(default)s).',
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
    p.add_argument(
        '--gui',
        action='store_true',
        help='Launch the interactive Textual TUI instead of plain terminal output.',
    )
    return p.parse_args(argv)
