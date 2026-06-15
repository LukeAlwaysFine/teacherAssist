"""
LLM Provider 抽象基类。

所有 LLM 厂商 Provider 必须继承此类并实现 chat() 方法。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    """LLM 对话消息。"""
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ChatResponse:
    """LLM 调用响应。"""
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
    })


class BaseLLMProvider(ABC):
    """LLM Provider 抽象基类。

    所有厂商实现必须提供 chat() 方法。
    """

    def __init__(self, api_key: str, model: str, max_tokens: int = 4096) -> None:
        """初始化 Provider。

        Args:
            api_key: API 密钥。
            model: 模型名称。
            max_tokens: 每次调用最大 token 数。
        """
        if not api_key:
            raise ValueError(f"{self.__class__.__name__}: 缺少 API Key")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """发送对话请求。

        Args:
            messages: 消息列表（包含 system prompt + user messages）。
            temperature: 采样温度（0-1）。
            max_tokens: 本次调用最大 token 数，为 None 时使用实例默认值。

        Returns:
            ChatResponse 对象，包含响应文本和使用统计。

        Raises:
            LLMProviderError: 调用失败时抛出。
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider 名称标识。"""
        ...
