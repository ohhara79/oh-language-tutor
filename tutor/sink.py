"""Output sinks: terminal (default) and log file."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO

    from tutor.types import ThreadMeta

# ANSI escape helpers (suppressed automatically when stdout is not a TTY).
_RESET = '\033[0m'
_DIM = '\033[2m'
_CYAN = '\033[36m'
_BOLD = '\033[1m'


def ansi_enabled() -> bool:
    """Return True when ANSI escape codes are safe to emit."""
    return sys.stdout.isatty() and os.environ.get('NO_COLOR', '') == ''


class TerminalSink:
    """OutputSink implementation that writes to stdout + a log file."""

    def __init__(self, log: TextIO, *, ansi: bool) -> None:
        self._log: TextIO = log
        self._ansi: bool = ansi

    # -- OutputSink protocol --------------------------------------------------

    def on_raw_line(self, raw: str) -> None:
        sys.stdout.write(raw + '\n')
        sys.stdout.flush()
        self._log.write(raw + '\n')

    def on_explanation(self, line_idx: int, raw: str, text: str) -> None:  # noqa: ARG002
        self._print_header()
        sys.stdout.write(text + '\n')
        sys.stdout.flush()
        self._print_footer()
        self._log.write(f'--- explanation for: {raw}\n')
        self._log.write(text + '\n')
        self._log.write('---\n')

    def on_thread_chunk(self, thread_id: str, chunk: str) -> None:
        pass  # terminal mode does not display thread conversations

    def on_thread_done(self, thread_id: str) -> None:
        pass

    def on_thread_list(self, threads: list[ThreadMeta]) -> None:
        pass

    def on_error(self, msg: str) -> None:
        sys.stderr.write(f'[oh-language-tutor] {msg}\n')

    # -- internal helpers -----------------------------------------------------

    def _print_header(self) -> None:
        rule = '\u2500' * 72
        if self._ansi:
            sys.stdout.write(f'{_DIM}{_CYAN}{rule}{_RESET}\n')
        else:
            sys.stdout.write(f'{rule}\n')
        sys.stdout.flush()

    def _print_footer(self) -> None:
        if self._ansi:
            sys.stdout.write(f'{_DIM}{_CYAN}{"\u2500" * 72}{_RESET}\n\n')
        else:
            sys.stdout.write(f'{"\u2500" * 72}\n\n')
        sys.stdout.flush()
