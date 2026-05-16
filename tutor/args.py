"""CLI argument parsing for oh-language-tutor."""

from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STATE_DIR = PROJECT_DIR / 'state' / 'scratch'
DEFAULT_EXPLAIN_MODEL = 'claude-opus-4-7'
DEFAULT_ASK_MODEL = 'claude-opus-4-7'


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments and return an ``argparse.Namespace``."""
    p = argparse.ArgumentParser(
        prog='oh-language-tutor',
        description='Pipe a text stream in; get Claude explanations out.',
    )
    p.add_argument(
        '--extra-system-prompt',
        help='Path to a text file appended to the base system prompt.',
    )
    p.add_argument(
        '--filter-regex',
        help=(
            'Only keep stdin lines matching this regex. If the pattern has a '
            'capture group, group 1 replaces the kept line (others are ignored). '
            'Omit to keep every line.'
        ),
    )
    p.add_argument(
        '--explain-model',
        default=DEFAULT_EXPLAIN_MODEL,
        help='Claude model id for streaming explanations (default: %(default)s).',
    )
    p.add_argument(
        '--ask-model',
        default=DEFAULT_ASK_MODEL,
        help='Claude model id for ask-thread follow-ups (default: %(default)s).',
    )
    p.add_argument(
        '--state-dir',
        default=str(DEFAULT_STATE_DIR),
        help=(
            'Write target for stdin lines (default: %(default)s). The web '
            'picker lists sibling dirs of this path so the user can choose '
            'which dataset to view; this flag only governs where new stdin '
            'lines are persisted.'
        ),
    )
    p.add_argument(
        '--web-host',
        default='127.0.0.1',
        help='Web UI bind address (default: %(default)s).',
    )
    p.add_argument(
        '--web-port',
        default=8000,
        type=int,
        help='Web UI bind port (default: %(default)s).',
    )
    return p.parse_args(argv)
