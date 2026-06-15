"""
STT 引擎抽象基类。

所有语音转文字引擎必须继承此类。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class STTResult:
    """STT 转录结果。"""
    text: str
    segments: list[dict]  # [{start, end, text}, ...]
    engine_name: str
    processing_time_seconds: float
    audio_duration_seconds: float


class BaseSTTEngine(ABC):
    """STT 引擎抽象基类。

    所有实现必须提供 transcribe() 和 transcribe_chunk() 方法。
    """

    def __init__(self, model_name: str = "medium") -> None:
        self.model_name = model_name

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """引擎标识名称。"""
        ...

    @property
    @abstractmethod
    def engine_label(self) -> str:
        """引擎显示名称（中文）。"""
        ...

    @abstractmethod
    async def transcribe(self, audio_path: Path, progress_callback=None) -> STTResult:
        """转写完整音频文件。

        Args:
            audio_path: 音频文件路径。
            progress_callback: 可选进度回调 (progress_pct, latest_segment_time)。

        Returns:
            STTResult: 转录结果，包含文本和时间轴分段。

        Raises:
            STTEngineError: 转录失败时抛出。
        """
        ...

    @abstractmethod
    async def transcribe_chunk(self, audio_bytes: bytes) -> STTResult:
        """转写音频片段（用于实时 chunk 处理）。

        Args:
            audio_bytes: 音频字节数据（Opus/WebM 编码）。

        Returns:
            STTResult: 转录结果。
        """
        ...

    @staticmethod
    def get_engine_info() -> dict:
        """返回引擎的描述信息，供前端 UI 展示。

        Returns:
            dict: {
                id: str,
                name: str,
                description: str,
                speed: str,
                cost: str,
                pros: list[str],
                cons: list[str],
                hardware_requirements: str,
            }
        """
        raise NotImplementedError
