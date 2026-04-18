"""Tests for ``tutor.markdown_util``."""

from __future__ import annotations

from tutor.markdown_util import _insert_blank_before_lists, emphasis_to_html, render_markdown


def test_emphasis_to_html_bold() -> None:
    assert emphasis_to_html('**hello**') == '<strong>hello</strong>'


def test_emphasis_to_html_italic() -> None:
    assert emphasis_to_html('*hi*') == '<em>hi</em>'


def test_emphasis_to_html_cjk_adjacent_bold() -> None:
    out = emphasis_to_html('안녕**하세요**!')
    assert '<strong>하세요</strong>' in out


def test_emphasis_to_html_cjk_adjacent_italic() -> None:
    out = emphasis_to_html('안녕*하세요*!')
    assert '<em>하세요</em>' in out


def test_emphasis_to_html_triple_stars_no_broken_nesting() -> None:
    out = emphasis_to_html('***both***')
    assert '*' not in out.replace('<strong>', '').replace('</strong>', '').replace('<em>', '').replace('</em>', '')


def test_emphasis_to_html_ignores_spaced_markers() -> None:
    assert emphasis_to_html('a ** b ** c') == 'a ** b ** c'


def test_insert_blank_before_lists_adds_blank() -> None:
    result = _insert_blank_before_lists('Heading\n- item1\n- item2')
    assert result == 'Heading\n\n- item1\n- item2'


def test_insert_blank_before_lists_existing_blank_unchanged() -> None:
    original = 'Heading\n\n- item1\n- item2'
    assert _insert_blank_before_lists(original) == original


def test_insert_blank_before_lists_numbered_marker() -> None:
    result = _insert_blank_before_lists('Intro\n1. first')
    assert result == 'Intro\n\n1. first'


def test_insert_blank_before_lists_consecutive_items_stay_contiguous() -> None:
    src = '- a\n- b\n- c'
    assert _insert_blank_before_lists(src) == src


def test_render_markdown_bold_inside_list_item() -> None:
    html = render_markdown('Heading\n- **word** meaning')
    assert '<ul>' in html
    assert '<strong>word</strong>' in html


def test_render_markdown_plain_paragraph() -> None:
    assert render_markdown('hello world') == '<p>hello world</p>'
