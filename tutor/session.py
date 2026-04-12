"""Session id persistence for cross-run resume."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


def load_saved_session_id(args: argparse.Namespace) -> str | None:
    """Decide the ``resume`` value for ClaudeAgentOptions."""
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
    """Write the session id to disk so the next run can resume."""
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session_id + '\n', encoding='utf-8')
