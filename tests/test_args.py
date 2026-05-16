"""Tests for ``tutor.args.parse_args``."""

from __future__ import annotations

import pytest

from tutor.args import (
    DEFAULT_ASK_MODEL,
    DEFAULT_EXPLAIN_MODEL,
    parse_args,
)


def test_no_args_produces_namespace_with_defaults() -> None:
    args = parse_args([])
    assert args.explain_model == DEFAULT_EXPLAIN_MODEL
    assert args.ask_model == DEFAULT_ASK_MODEL
    assert args.web_host == '127.0.0.1'
    assert args.web_port == 8000
    assert args.extra_system_prompt is None
    assert args.filter_regex is None


def test_web_port_is_coerced_to_int() -> None:
    args = parse_args(['--web-port', '9001'])
    assert args.web_port == 9001
    assert isinstance(args.web_port, int)


def test_web_port_rejects_non_integer() -> None:
    with pytest.raises(SystemExit):
        parse_args(['--web-port', 'not-a-number'])
