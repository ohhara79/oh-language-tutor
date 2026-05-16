"""Helpers for consuming claude_agent_sdk streaming events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from claude_agent_sdk import StreamEvent


def text_delta(event: StreamEvent) -> str | None:
    """Extract incremental text from a ``content_block_delta`` stream event.

    Returns ``None`` for any other event shape. The SDK wraps the raw
    Anthropic stream event under ``StreamEvent.event``; we only care about
    ``text_delta`` deltas for live UI rendering.
    """
    raw: dict[str, Any] = event.event
    if raw.get('type') != 'content_block_delta':
        return None
    delta_obj: object = raw.get('delta')
    if not isinstance(delta_obj, dict):
        return None
    delta = cast('dict[str, Any]', delta_obj)
    if delta.get('type') != 'text_delta':
        return None
    text: object = delta.get('text')
    return text if isinstance(text, str) else None
