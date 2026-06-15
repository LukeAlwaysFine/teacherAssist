"""
DeepSeek Provider — DeepSeek V4 Pro Max 及兼容 OpenAI API 格式的模型。
"""
import logging

from openai import AsyncOpenAI

from app.services.llm.base import (
    BaseLLMProvider,
    ChatMessage,
    ChatResponse,
)

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """LLM Provider 通用异常。"""
    pass


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek API Provider（OpenAI 兼容接口）。

    Default model: deepseek-chat (DeepSeek V4 Pro Max).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
        base_url: str = "https://api.deepseek.com",
    ) -> None:
        super().__init__(api_key, model, max_tokens)
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    @property
    def provider_name(self) -> str:
        return "deepseek"

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """调用 DeepSeek API（OpenAI 兼容格式）。

        所有消息（含 system）统一放入 messages 列表。
        """
        formatted: list[dict[str, str]] = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=formatted,  # type: ignore[arg-type]
                max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                temperature=temperature,
            )
            choice = response.choices[0]
            return ChatResponse(
                content=choice.message.content or "",
                model=response.model,
                usage={
                    "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                },
            )
        except Exception as e:
            logger.error(f"DeepSeek API call failed: {e}")
            raise LLMProviderError(f"DeepSeek API 调用失败: {e}") from e
