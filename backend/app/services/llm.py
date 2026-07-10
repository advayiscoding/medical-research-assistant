"""Claude API access — the only module that imports the Anthropic SDK.

Same isolation principle as vector_store.py: one wrapper, one place to change
if we swap models or providers. Exposes a tiny async `complete()` surface so the
RAG and agent layers depend on an interface, not on the SDK — which is what lets
tests inject a fake with no network and no API key.
"""

import logging
from typing import Protocol

from anthropic import AsyncAnthropic

from app.core.config import Settings

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Structural interface the RAG/agent layers depend on. A fake in tests just
    needs a matching `complete` coroutine."""

    async def complete(self, system: str, user: str, *, max_tokens: int = ...) -> str: ...


class ClaudeClient:
    def __init__(self, settings: Settings) -> None:
        # AsyncAnthropic so the LLM round-trip (seconds) never blocks the event
        # loop. The key comes from our Settings, not ambient env, so config has
        # one source of truth.
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model

    async def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        """Single grounded completion. Non-streaming: RAG answers are short
        (~1-2k tokens, well under the ~16k non-streaming timeout threshold), and
        a whole-answer response is simpler to parse citations from than a stream.
        Adaptive thinking is left off here — grounded extraction from provided
        text is not a reasoning-heavy task, and off keeps latency/cost down; the
        agent layer (Phase 7) turns it on for the harder multi-step work."""
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Concatenate text blocks; guard the block type (thinking/tool blocks
        # could appear if config changes) rather than assuming content[0].text.
        return "".join(b.text for b in resp.content if b.type == "text")


def get_claude_client(settings: Settings) -> ClaudeClient:
    return ClaudeClient(settings)
