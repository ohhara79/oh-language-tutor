"""Language tutor for any text stream, backed by the Claude Agent SDK.

Reads a source text stream on stdin (typically piped from another
program — a game, a subtitle stream, a chat log, anything), echoes it
back to stdout, and for each interesting line asks a persistent Claude
session to explain it for a language learner.

See docs/plans/ for the full design. This module is the entry point;
all logic lives in the ``tutor`` package.
"""

from __future__ import annotations

import asyncio
import sys

from tutor.args import parse_args
from tutor.web import run_web


def main() -> None:
    """Entry point for oh-language-tutor."""
    args = parse_args()
    try:
        rc = asyncio.run(run_web(args))
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == '__main__':
    main()
