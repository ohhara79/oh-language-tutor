"""Tests for pure helpers and small widgets in ``tutor.tui``.

These tests avoid Textual's ``Pilot`` harness: the helpers do not touch the
event loop, widget lifecycle, or DOM. Pilot-driven tests live in
``test_tui_app.py``.
"""

from __future__ import annotations

from typing import Any

from markdown_it.token import Token

from tutor.tui import (
    ExplanationBlock,
    LineBlock,
    ThreadListItem,
    _CJKMarkdown,
    _QuickButton,
    _rich_md,
)
from tutor.types import ThreadMessage, ThreadMeta

# -- _rich_md / _CJKMarkdown -------------------------------------------------


def test_rich_md_returns_cjk_markdown():
    md = _rich_md('**hi**')
    assert isinstance(md, _CJKMarkdown)


def test_cjk_markdown_converts_emphasis_to_strong_tokens():
    md = _CJKMarkdown('**bold**')
    out = [t for t in md._flatten_tokens(md.parsed) if t.type.startswith('strong')]
    kinds = [(t.type, t.nesting, t.markup) for t in out]
    assert ('strong_open', 1, '**') in kinds
    assert ('strong_close', -1, '**') in kinds


def test_cjk_markdown_converts_em_to_em_tokens():
    md = _CJKMarkdown('*slanted*')
    out = [t for t in md._flatten_tokens(md.parsed) if t.type.startswith('em')]
    kinds = [(t.type, t.nesting, t.markup) for t in out]
    assert ('em_open', 1, '*') in kinds
    assert ('em_close', -1, '*') in kinds


def test_cjk_markdown_handles_cjk_adjacent_emphasis():
    """The whole point of this subclass: CJK characters adjacent to **."""
    md = _CJKMarkdown('안녕**하세요**!')
    flat = list(md._flatten_tokens(md.parsed))
    types = [t.type for t in flat]
    assert 'strong_open' in types
    assert 'strong_close' in types
    # Text content is preserved between the tags
    text_contents = [t.content for t in flat if t.type == 'text']
    assert '하세요' in text_contents


def test_cjk_markdown_passes_through_non_html_inline():
    md = _CJKMarkdown('plain text')
    flat = list(md._flatten_tokens(md.parsed))
    # Every token with non-empty content is preserved with type 'text'
    text_tokens = [t for t in flat if t.type == 'text' and t.content == 'plain text']
    assert len(text_tokens) == 1


def test_cjk_markdown_passes_through_unknown_html_inline():
    """Synthetic html_inline token whose content isn't a known tag is yielded unchanged."""
    md = _CJKMarkdown('x')
    unknown = Token(
        type='html_inline',
        tag='',
        nesting=0,
        attrs={},
        map=None,
        level=0,
        children=None,
        content='<code>',
        markup='',
        info='',
        meta={},
        block=False,
        hidden=False,
    )
    # Build a minimal parsed-like input: a paragraph with a single inline
    # group containing the html_inline token. The parent _flatten_tokens will
    # yield the html_inline token through; our override should pass it along
    # as-is because '<code>' isn't in the open/close map.
    inline = Token(
        type='inline',
        tag='',
        nesting=0,
        attrs={},
        map=[0, 1],
        level=1,
        children=[unknown],
        content='<code>',
        markup='',
        info='',
        meta={},
        block=True,
        hidden=False,
    )
    flat = list(md._flatten_tokens([inline]))
    html_inline_tokens = [t for t in flat if t.type == 'html_inline']
    assert len(html_inline_tokens) == 1
    assert html_inline_tokens[0].content == '<code>'


# -- _QuickButton ------------------------------------------------------------


def test_quickbutton_zeroes_active_effect_duration():
    btn = _QuickButton('Hit')
    assert btn.active_effect_duration == 0.0


# -- LineBlock ---------------------------------------------------------------


def test_lineblock_exposes_raw_and_tutor_id():
    block = LineBlock('raw text', 'tid-1')
    assert block.raw == 'raw text'
    assert block.tutor_id == 'tid-1'


def test_lineblock_compose_yields_label_and_two_buttons():
    block = LineBlock('some raw', 'abc-123')
    children = list(block.compose())
    assert len(children) == 3
    # First is Label with the raw text
    from textual.widgets import Label

    assert isinstance(children[0], Label)
    assert str(children[0].render()) == 'some raw'
    # Next two are _QuickButtons with expected IDs
    assert isinstance(children[1], _QuickButton)
    assert children[1].id == 'ask-abc-123'
    assert isinstance(children[2], _QuickButton)
    assert children[2].id == 'line-delete-abc-123'


# -- ExplanationBlock --------------------------------------------------------


def test_explanationblock_renders_markdown():
    blk = ExplanationBlock('**strong**')
    visual: Any = blk.render()
    # RichVisual wraps a _CJKMarkdown under ._renderable
    assert isinstance(visual._renderable, _CJKMarkdown)


# -- ThreadListItem ----------------------------------------------------------


def _meta(**kw: Any) -> ThreadMeta:
    base: dict[str, Any] = {
        'thread_id': 't-1',
        'anchor_raw': 'the anchor line',
        'session_id': 's',
        'created_at': '2026-04-18T12:00:00+00:00',
        'anchor_id': 'a-1',
        'messages': [],
    }
    base.update(kw)
    return ThreadMeta(**base)


def test_threadlistitem_compose_yields_label_and_two_buttons():
    meta = _meta(messages=[ThreadMessage(role='user', text='q1')])
    item = ThreadListItem(meta)
    children = list(item.compose())
    assert len(children) == 3

    from textual.widgets import Label

    assert isinstance(children[0], Label)
    label_text = str(children[0].render())
    assert 'the anchor line' in label_text
    assert '1 msgs' in label_text
    assert '2026-04-18 12:00:00 UTC' in label_text

    assert isinstance(children[1], _QuickButton)
    assert children[1].id == 'reopen-t-1'
    assert isinstance(children[2], _QuickButton)
    assert children[2].id == 'delete-t-1'


def test_threadlistitem_truncates_long_anchor_raw():
    long_raw = 'X' * 120
    meta = _meta(anchor_raw=long_raw)
    item = ThreadListItem(meta)
    children = list(item.compose())

    from textual.widgets import Label

    assert isinstance(children[0], Label)
    label_text = str(children[0].render())
    # Only first 60 chars appear
    assert 'X' * 60 in label_text
    assert 'X' * 61 not in label_text
