"""Tests for ``tutor.args.parse_args``."""

from __future__ import annotations

import pytest

from tutor.args import (
    DEFAULT_ASK_MODEL,
    DEFAULT_EXPLAIN_MODEL,
    DEFAULT_SKIP_TOKEN,
    parse_args,
)


def _required() -> list[str]:
    return ['--source-language', 'English', '--target-language', 'Korean']


def test_required_args_produce_namespace() -> None:
    args = parse_args(_required())
    assert args.source_language == 'English'
    assert args.target_language == 'Korean'


def test_missing_source_language_exits() -> None:
    with pytest.raises(SystemExit):
        parse_args(['--target-language', 'Korean'])


def test_missing_target_language_exits() -> None:
    with pytest.raises(SystemExit):
        parse_args(['--source-language', 'English'])


def test_defaults() -> None:
    args = parse_args(_required())
    assert args.level == 'intermediate'
    assert args.skip_token == DEFAULT_SKIP_TOKEN
    assert args.explain_model == DEFAULT_EXPLAIN_MODEL
    assert args.ask_model == DEFAULT_ASK_MODEL
    assert args.web_host == '127.0.0.1'
    assert args.web_port == 8000
    assert args.tui is False
    assert args.web is False
    assert args.new_session is False
    assert args.resume_id is None
    assert args.extra_system_prompt is None
    assert args.filter_regex is None


@pytest.mark.parametrize('level', ['beginner', 'intermediate', 'advanced'])
def test_level_accepts_valid_choices(level: str) -> None:
    args = parse_args([*_required(), '--level', level])
    assert args.level == level


def test_level_rejects_invalid_choice() -> None:
    with pytest.raises(SystemExit):
        parse_args([*_required(), '--level', 'fluent'])


def test_tui_and_web_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        parse_args([*_required(), '--tui', '--web'])


def test_web_port_is_coerced_to_int() -> None:
    args = parse_args([*_required(), '--web-port', '9001'])
    assert args.web_port == 9001
    assert isinstance(args.web_port, int)


def test_web_port_rejects_non_integer() -> None:
    with pytest.raises(SystemExit):
        parse_args([*_required(), '--web-port', 'not-a-number'])


def test_new_session_flag_sets_true() -> None:
    args = parse_args([*_required(), '--new-session'])
    assert args.new_session is True


def test_resume_id_stored() -> None:
    args = parse_args([*_required(), '--resume-id', 'abc123'])
    assert args.resume_id == 'abc123'
