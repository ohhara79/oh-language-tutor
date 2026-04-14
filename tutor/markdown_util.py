"""Shared markdown utilities used by both the TUI and the HTML exporter."""

from __future__ import annotations

import re

# CommonMark's emphasis rules fail when a closing ** (or *) is preceded by
# punctuation and followed by a word character — common in CJK text where no
# space separates bold spans from surrounding characters.  We side-step this
# by converting **/​* emphasis to HTML <strong>/<em> tags with a regex *before*
# handing the text to a markdown parser.
_RE_STRONG = re.compile(r'\*\*(?!\s)(.+?)(?<!\s)\*\*')
_RE_EMPH = re.compile(r'(?<!\*)\*(?!\*|\s)(.+?)(?<!\s|\*)\*(?!\*)')


def emphasis_to_html(text: str) -> str:
    """Replace ``**text**`` / ``*text*`` with HTML tags before parsing."""
    text = _RE_STRONG.sub(r'<strong>\1</strong>', text)
    return _RE_EMPH.sub(r'<em>\1</em>', text)
