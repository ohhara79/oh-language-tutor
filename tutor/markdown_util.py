"""Shared markdown utilities used by the TUI, HTML exporter, and web UI."""

from __future__ import annotations

import re

import markdown as md

# CommonMark's emphasis rules fail when a closing ** (or *) is preceded by
# punctuation and followed by a word character — common in CJK text where no
# space separates bold spans from surrounding characters.  We side-step this
# by converting **/​* emphasis to HTML <strong>/<em> tags with a regex *before*
# handing the text to a markdown parser.
_RE_STRONG = re.compile(r'\*\*(?!\s)(.+?)(?<!\s)\*\*')
_RE_EMPH = re.compile(r'(?<!\*)\*(?!\*|\s)(.+?)(?<!\s|\*)\*(?!\*)')
_RE_LIST_MARKER = re.compile(r'^\s*([-*+]|\d+\.)\s')


def emphasis_to_html(text: str) -> str:
    """Replace ``**text**`` / ``*text*`` with HTML tags before parsing."""
    text = _RE_STRONG.sub(r'<strong>\1</strong>', text)
    return _RE_EMPH.sub(r'<em>\1</em>', text)


def _insert_blank_before_lists(text: str) -> str:
    # Python-markdown needs a blank line before a list; the model often emits
    # a heading line directly followed by "- item" lines, which then renders
    # as one run-on <p>. Inject the blank line so it parses as <ul>.
    lines = text.split('\n')
    out: list[str] = []
    for line in lines:
        if (
            _RE_LIST_MARKER.match(line)
            and out
            and out[-1].strip()
            and not _RE_LIST_MARKER.match(out[-1])
        ):
            out.append('')
        out.append(line)
    return '\n'.join(out)


def render_markdown(text: str) -> str:
    """Convert stored markdown text to an HTML fragment, CJK-safe."""
    text = _insert_blank_before_lists(text)
    return md.markdown(emphasis_to_html(text), extensions=['extra', 'sane_lists'])
