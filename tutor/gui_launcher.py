"""Deferred import wrapper for the Textual GUI."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


async def run_gui(args: argparse.Namespace) -> int:
    """Launch the Textual TUI (requires ``textual`` to be installed)."""
    try:
        from tutor.gui import OhLanguageTutorApp  # noqa: PLC0415
    except ImportError:
        sys.stderr.write('[oh-language-tutor] --gui requires textual. Install it with: uv add textual\n')
        return 1

    return await OhLanguageTutorApp.launch(args)
