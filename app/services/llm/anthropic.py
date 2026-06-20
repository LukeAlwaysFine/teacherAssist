"""
Anthropic Provider — Claude 系列模型（claude-sonnet-4-6, claude-opus-4-8 等）。
"""
import logging
from typing import Any

from anthropic import AsyncAnthropic

from app.services.llm.base import (
    BaseLLMProvider,
    ChatMessage,
    ChatResponse,
)

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """LLM Provider 通用异常。"""
    pass


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API Provider。"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        reasoning_effort: str = "high",
    ) -> None:
        super().__init__(api_key, model, max_tokens, reasoning_effort)
        self._client = AsyncAnthropic(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "anthropic"

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """调用 Claude API。

        Anthropic 需要单独提取 system 消息，其余为 messages。
        """
        system_prompt = ""
        user_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                user_messages.append({"role": msg.role, "content": msg.content})

        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                system=system_prompt,
                messages=user_messages,
                temperature=temperature,
            )
            text_blocks = [
                block.text for block in response.content if block.type == "text"
            ]
            return ChatResponse(
                content="\n".join(text_blocks),
                model=response.model,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )
        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")
            raise LLMProviderError(f"Claude API 调用失败: {e}") from e
