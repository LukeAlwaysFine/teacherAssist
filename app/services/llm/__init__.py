"""
LLM Provider 抽象层。

支持 DeepSeek、Anthropic Claude 等多厂商，通过配置切换。
"""
from app.services.llm.base import BaseLLMProvider
from app.services.llm.anthropic import AnthropicProvider
from app.services.llm.deepseek import DeepSeekProvider

__all__ = ["BaseLLMProvider", "AnthropicProvider", "DeepSeekProvider"]


def create_llm_provider() -> BaseLLMProvider:
    """工厂函数：根据配置创建对应的 LLM Provider。

    Returns:
        BaseLLMProvider 实例。

    Raises:
        ValueError: LLM_PROVIDER 配置值不合法。
    """
    from app.core.config import settings

    provider_name = settings.LLM_PROVIDER.lower()

    if provider_name == "anthropic":
        return AnthropicProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.CLAUDE_MAX_TOKENS,
        )
    elif provider_name == "deepseek":
        return DeepSeekProvider(
            api_key=settings.DEEPSEEK_API_KEY,
            model=settings.DEEPSEEK_MODEL,
            max_tokens=settings.DEEPSEEK_MAX_TOKENS,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
    else:
        raise ValueError(f"不支持的 LLM_PROVIDER: {provider_name}。"
                         f"支持的提供商: anthropic, deepseek")
