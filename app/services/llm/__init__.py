"""
LLM Provider 抽象层。

不限制特定厂商：任何 OpenAI 兼容 API 均可使用。
Anthropic 使用官方 SDK；其他所有厂商通过 OpenAI 兼容协议接入。
"""
from app.services.llm.base import BaseLLMProvider
from app.services.llm.anthropic import AnthropicProvider
from app.services.llm.deepseek import DeepSeekProvider

__all__ = ["BaseLLMProvider", "AnthropicProvider", "DeepSeekProvider"]


def create_llm_provider(
    provider: str = "",
    api_key: str = "",
    model: str = "",
    max_tokens: int = 4096,
    base_url: str = "",
) -> BaseLLMProvider:
    """工厂函数：根据配置创建对应的 LLM Provider。

    用户配置优先于系统默认。

    Args:
        provider: 提供商名称。"anthropic" 使用 Anthropic SDK；其他均为 OpenAI 兼容。
        api_key: API 密钥（必填）。
        model: 模型 ID。
        max_tokens: 最大输出 token 数。
        base_url: API 端点 URL（OpenAI 兼容时需要）。

    Returns:
        BaseLLMProvider 实例。

    """
    import logging
    from app.core.config import settings

    logger = logging.getLogger(__name__)

    provider_name = (provider or settings.LLM_PROVIDER or "").strip().lower()
    effective_key = api_key or ""
    effective_model = model or ""
    effective_tokens = max_tokens or 4096
    effective_url = base_url or ""

    if provider_name == "anthropic":
        return AnthropicProvider(
            api_key=effective_key,
            model=effective_model or "claude-sonnet-4-6",
            max_tokens=effective_tokens,
        )

    # 所有其他厂商：OpenAI 兼容协议
    # 若有明确的 provider 名称但非已知值，记录警告以帮助发现拼写错误
    known_providers = {
        "deepseek", "openai", "qwen", "zhipu", "moonshot",
        "groq", "ollama", "siliconflow",
    }
    if provider_name and provider_name not in known_providers:
        logger.warning(
            "未识别的 LLM provider '%s'，将按 OpenAI 兼容协议处理。"
            "如果连接失败，请检查 provider 名称是否正确",
            provider_name,
        )
    # DEEPSEEK_BASE_URL 作为所有 OpenAI 兼容 provider 的默认 endpoint
    if not effective_url:
        effective_url = settings.DEEPSEEK_BASE_URL or "https://api.deepseek.com"

    # AsyncOpenAI SDK 不允许空字符串 api_key，用占位符绕过初始化检查
    # 真正调用时 AIService._call_llm 会先检查 api_key 是否已配置
    return DeepSeekProvider(
        api_key=effective_key or "sk-placeholder",
        model=effective_model or "deepseek-chat",
        max_tokens=effective_tokens,
        base_url=effective_url,
    )
