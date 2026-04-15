"""Render state-dir JSON (tutor.json + threads/*.json) as a single HTML page."""

from __future__ import annotations

import html
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import markdown as md

from tutor.markdown_util import emphasis_to_html
from tutor.types import format_created_at_utc

if TYPE_CHECKING:
    from tutor.thread_store import ThreadStore
    from tutor.tutor_store import TutorStore
    from tutor.types import ThreadMeta, TutorEntry


_CSS = """
:root { color-scheme: light dark; }
body {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    max-width: 820px;
    margin: 2rem auto;
    padding: 0 1rem;
    line-height: 1.55;
}
header { border-bottom: 1px solid #888; margin-bottom: 2rem; padding-bottom: 0.5rem; }
header h1 { margin: 0 0 0.25rem 0; font-size: 1.4rem; }
.meta { color: #888; font-size: 0.85rem; margin: 0; }
.line {
    border-top: 1px solid #ddd;
    padding: 0.4rem 0;
}
.line:first-child { border-top: none; }
details.explain > summary.raw {
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 0.9rem;
    color: #333;
    white-space: pre-wrap;
    cursor: pointer;
    list-style: revert;
}
details.explain[open] > summary.raw { margin-bottom: 0.5rem; color: #666; }
.explanation-body { margin: 0 0 0.25rem 1.25rem; }
.explanation-body :first-child { margin-top: 0; }
.explanation-body :last-child { margin-bottom: 0; }
details.thread {
    margin: 0.5rem 0 0.25rem 1.25rem;
    padding: 0.5rem 0.75rem;
    background: rgba(128, 128, 128, 0.08);
    border-radius: 4px;
}
details.thread > summary {
    cursor: pointer;
    font-size: 0.9rem;
    color: #555;
}
details.thread[open] > summary { margin-bottom: 0.5rem; }
.msg { margin: 0.5rem 0; }
.msg.user { color: #0b6bcb; }
.msg.user .who { font-weight: 600; margin-right: 0.3rem; }
.msg.assistant { border-left: 3px solid rgba(128, 128, 128, 0.3); padding-left: 0.75rem; }
.msg.assistant :first-child { margin-top: 0; }
.msg.assistant :last-child { margin-bottom: 0; }
code { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 0.9em; }
pre { background: rgba(128, 128, 128, 0.08); padding: 0.5rem 0.75rem; border-radius: 4px; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { border-left: 3px solid rgba(128, 128, 128, 0.3); margin: 0.5rem 0; padding: 0 0.75rem; color: #555; }
.empty { color: #888; font-style: italic; padding: 2rem 0; text-align: center; }
section.orphans { border-top: 2px dashed #ccc; margin-top: 2rem; padding-top: 1rem; }
section.orphans > h2 { font-size: 1.1rem; color: #888; }
.orphan-anchor {
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 0.9rem;
    color: #666;
    white-space: pre-wrap;
    margin-bottom: 0.25rem;
}
@media (prefers-color-scheme: dark) {
    body { background: #1a1a1a; color: #eee; }
    details.explain > summary.raw { color: #ddd; }
    details.explain[open] > summary.raw { color: #aaa; }
    details.thread > summary { color: #bbb; }
    blockquote { color: #bbb; }
    .msg.user { color: #6ab0ff; }
    .empty { color: #888; }
    header { border-color: #444; }
    .line { border-color: #333; }
}
"""


def _render_markdown(text: str) -> str:
    """Convert stored markdown text to an HTML fragment, CJK-safe."""
    return md.markdown(emphasis_to_html(text), extensions=['extra', 'sane_lists'])


def _render_thread(thread: ThreadMeta) -> str:
    when = html.escape(format_created_at_utc(thread.created_at))
    n = len(thread.messages)
    summary = html.escape(f'Thread ({n} msg{"s" if n != 1 else ""}, {when})')
    parts: list[str] = [f'<details class="thread"><summary>{summary}</summary>']
    for m in thread.messages:
        if m.role == 'user':
            parts.append(
                f'<div class="msg user"><span class="who">You:</span>{html.escape(m.text)}</div>',
            )
        else:
            parts.append(f'<div class="msg assistant">{_render_markdown(m.text)}</div>')
    parts.append('</details>')
    return ''.join(parts)


def _render_line(entry: TutorEntry, threads: list[ThreadMeta]) -> str:
    parts: list[str] = ['<section class="line">']
    parts.append(
        '<details class="explain">'
        f'<summary class="raw">{html.escape(entry.raw)}</summary>'
        f'<div class="explanation-body">{_render_markdown(entry.explanation)}</div>'
        '</details>',
    )
    parts.extend(_render_thread(t) for t in threads)
    parts.append('</section>')
    return ''.join(parts)


def _render_orphan_threads(threads: list[ThreadMeta]) -> str:
    if not threads:
        return ''
    parts: list[str] = [
        '<section class="orphans"><h2>Orphan threads</h2>',
        '<p class="meta">Threads whose anchor line is not present in tutor.json.</p>',
    ]
    for t in threads:
        parts.append(f'<section class="line"><div class="orphan-anchor">{html.escape(t.anchor_raw)}</div>')
        parts.append(_render_thread(t))
        parts.append('</section>')
    parts.append('</section>')
    return ''.join(parts)


def _build_html(entries: list[TutorEntry], threads: list[ThreadMeta]) -> str:
    threads_by_id: dict[str, list[ThreadMeta]] = defaultdict(list)
    for t in threads:
        if t.anchor_id:
            threads_by_id[t.anchor_id].append(t)

    live_ids = {e.id for e in entries}

    body_parts: list[str] = [_render_line(entry, threads_by_id.get(entry.id, [])) for entry in entries]

    orphans = [t for t in threads if not t.anchor_id or t.anchor_id not in live_ids]
    body_parts.append(_render_orphan_threads(orphans))

    main = ''.join(body_parts) if (entries or orphans) else '<p class="empty">No content yet.</p>'
    now = datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M UTC')

    return (
        '<!doctype html>\n'
        '<html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>oh-language-tutor export</title>'
        f'<style>{_CSS}</style>'
        '</head><body>'
        '<header>'
        '<h1>oh-language-tutor</h1>'
        f'<p class="meta">Exported {html.escape(now)} · {len(entries)} lines · {len(threads)} threads</p>'
        '</header>'
        f'<main>{main}</main>'
        '</body></html>\n'
    )


def export_to_html(tutor_store: TutorStore, thread_store: ThreadStore, out_path: Path) -> None:
    """Render the current state-dir contents to ``out_path`` atomically."""
    entries = tutor_store.load()
    threads = thread_store.list_threads()
    content = _build_html(entries, threads)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode='w',
        encoding='utf-8',
        dir=out_path.parent,
        suffix='.tmp',
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.rename(out_path)
