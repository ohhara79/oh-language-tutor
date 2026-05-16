"""Shared pytest fixtures for the oh-language-tutor test suite."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent, TextBlock

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    from jinja2 import Environment


def make_assistant(text: str) -> AssistantMessage:
    """Build a real ``AssistantMessage`` with a single ``TextBlock``.

    ``tutor.core`` and ``tutor.thread_pool`` check ``isinstance(msg, AssistantMessage)``,
    so tests must use the real SDK classes, not MagicMock.
    """
    return AssistantMessage(content=[TextBlock(text=text)], model='test-model')


def make_assistant_multi(*chunks: str) -> AssistantMessage:
    """Build an ``AssistantMessage`` with multiple ``TextBlock`` chunks."""
    return AssistantMessage(content=[TextBlock(text=c) for c in chunks], model='test-model')


def make_text_delta(text: str) -> StreamEvent:
    """Build a ``StreamEvent`` wrapping a single ``text_delta`` content block.

    Used by tests that need to drive the streaming UI chunk path through
    ``tutor.stream_util.text_delta``.
    """
    return StreamEvent(
        uuid='test-uuid',
        session_id='test-session',
        event={
            'type': 'content_block_delta',
            'index': 0,
            'delta': {'type': 'text_delta', 'text': text},
        },
    )


def make_result(session_id: str) -> ResultMessage:
    """Build a real ``ResultMessage`` with the given session id."""
    return ResultMessage(
        subtype='success',
        duration_ms=0,
        duration_api_ms=0,
        is_error=False,
        num_turns=1,
        session_id=session_id,
    )


class FakeClaudeSDKClient:
    """Minimal async-context-manager stand-in for ``ClaudeSDKClient``.

    Construct with a queue of response batches (each batch is an iterable of
    real SDK messages). Each ``query()`` call pops the next batch, which
    ``receive_response()`` then yields.

    Usage::

        fake = FakeClaudeSDKClient([[make_assistant('hi'), make_result('sid')]])
        async with fake:
            await fake.query('hello')
            async for msg in fake.receive_response():
                ...
    """

    def __init__(
        self,
        response_batches: list[Iterable[Any]] | None = None,
        *,
        raise_on_enter: BaseException | None = None,
        raise_on_query: BaseException | None = None,
    ) -> None:
        self._batches: list[list[Any]] = [list(b) for b in (response_batches or [])]
        self._queue: list[Any] = []
        self._raise_on_enter: BaseException | None = raise_on_enter
        self._raise_on_query: BaseException | None = raise_on_query
        self.queries: list[str] = []
        self.entered: bool = False
        self.exited: bool = False
        self.options: Any = None

    async def __aenter__(self) -> FakeClaudeSDKClient:
        if self._raise_on_enter is not None:
            raise self._raise_on_enter
        self.entered = True
        return self

    async def __aexit__(self, *_: object) -> None:
        self.exited = True

    async def query(self, text: str) -> None:
        if self._raise_on_query is not None:
            raise self._raise_on_query
        self.queries.append(text)
        if self._batches:
            self._queue.extend(self._batches.pop(0))

    async def receive_response(self) -> AsyncIterator[Any]:
        while self._queue:
            yield self._queue.pop(0)


class FakeClaudeSDKClientFactory:
    """Callable that records constructor calls and returns pre-seeded fakes.

    Used with ``monkeypatch.setattr(module, 'ClaudeSDKClient', factory)``.
    Push one ``FakeClaudeSDKClient`` per expected construction; the factory
    pops them in order and records each constructor's ``options`` kwarg.
    """

    def __init__(self) -> None:
        self._clients: list[FakeClaudeSDKClient] = []
        self.constructed: list[FakeClaudeSDKClient] = []
        self.option_calls: list[Any] = []

    def push(self, client: FakeClaudeSDKClient) -> FakeClaudeSDKClient:
        self._clients.append(client)
        return client

    def __call__(self, *, options: Any = None) -> FakeClaudeSDKClient:
        if not self._clients:
            msg = 'FakeClaudeSDKClientFactory exhausted — push more clients'
            raise RuntimeError(msg)
        client = self._clients.pop(0)
        client.options = options
        self.option_calls.append(options)
        self.constructed.append(client)
        return client


@pytest.fixture
def fake_client_factory() -> FakeClaudeSDKClientFactory:
    """Return a fresh ``FakeClaudeSDKClientFactory`` for each test."""
    return FakeClaudeSDKClientFactory()


@pytest.fixture
def jinja_env() -> Environment:
    """Return the real Jinja2 environment used by the web app."""
    from tutor.web import build_template_env

    return build_template_env()
