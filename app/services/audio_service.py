"""
AudioService — 音频处理编排服务。

职责：
- 管理 chunk 拼接去重
- 编排全量/实时转录流程
- 通过 SSE 推送转录进度
"""
import asyncio
import logging
from pathlib import Path
from typing import AsyncGenerator

from app.services.stt.base import BaseSTTEngine, STTResult
from app.services.stt import create_stt_engine

logger = logging.getLogger(__name__)


class AudioServiceError(Exception):
    """音频处理异常。"""
    pass


class AudioService:
    """音频处理编排服务。

    管理转录流程，支持：
    - 全量文件转录（路径 B/C/D）
    - 实时 chunk 转录（路径 A）
    - 简单文本去重拼接
    """

    def __init__(self, engine: BaseSTTEngine | None = None) -> None:
        self.engine = engine or create_stt_engine()

        # Chunk 拼接状态（路径 A 使用）
        self._chunk_texts: list[str] = []
        self._chunk_segments: list[dict] = []
        self._overlap_seconds: float = 5.0  # 前后 chunk 重叠秒数

    @property
    def collected_text(self) -> str:
        """当前已收集的所有 chunk 转录文本（拼接后）。"""
        return " ".join(self._chunk_texts)

    @property
    def collected_segments(self) -> list[dict]:
        """当前已收集的所有分段（时间轴已调整）。"""
        return list(self._chunk_segments)

    async def transcribe_file(
        self,
        audio_path: Path,
        progress_callback=None,
    ) -> STTResult:
        """转写完整音频文件。

        Args:
            audio_path: 音频文件路径。
            progress_callback: 可选进度回调 (progress_pct, segment_time)。

        Returns:
            STTResult: 转录结果。

        Raises:
            AudioServiceError: 转录失败时抛出。
        """
        try:
            result = await self.engine.transcribe(audio_path, progress_callback=progress_callback)
            return result
        except Exception as e:
            raise AudioServiceError(f"转录失败: {e}") from e

    async def add_chunk(self, audio_bytes: bytes, chunk_index: int) -> STTResult:
        """处理一个音频 chunk（路径 A）。

        转写 chunk 并与已有文本做去重拼接。

        Args:
            audio_bytes: 音频 chunk 字节数据。
            chunk_index: chunk 序号（从 0 开始）。

        Returns:
            STTResult: 当前 chunk 的转录结果（已去重）。
        """
        try:
            result = await self.engine.transcribe_chunk(audio_bytes)

            # 简单去重：与前一个 chunk 的尾部做重叠检测
            if chunk_index > 0 and self._chunk_texts:
                result = self._deduplicate_overlap(result)

            # 存储（调整时间偏移）
            base_offset = self._chunk_segments[-1]["end"] if self._chunk_segments else 0.0
            for seg in result.segments:
                seg["chunk_index"] = chunk_index
                seg["start"] = seg.get("start", 0) + base_offset
                seg["end"] = seg.get("end", 0) + base_offset

            self._chunk_texts.append(result.text)
            self._chunk_segments.extend(result.segments)

            return result
        except Exception as e:
            raise AudioServiceError(f"Chunk {chunk_index} 处理失败: {e}") from e

    def _deduplicate_overlap(self, new_result: STTResult) -> STTResult:
        """处理 chunk 重叠区域的文本去重。

        策略：比较新 chunk 开头与前一个 chunk 结尾的文本相似度，
        如果高度重叠，则从新 chunk 中删除重复部分。

        Args:
            new_result: 当前 chunk 的转录结果。

        Returns:
            去重后的 STTResult。
        """
        prev_text = self._chunk_texts[-1] if self._chunk_texts else ""
        if not prev_text:
            return new_result

        # 取前一个 chunk 最后 30 字，新 chunk 前 50 字
        prev_tail = prev_text[-30:] if len(prev_text) > 30 else prev_text
        new_head = new_result.text[:50] if len(new_result.text) > 50 else new_result.text

        overlap = self._find_common_substring(prev_tail, new_head)
        if overlap and len(overlap) >= 3:  # 至少 3 字重叠
            # 从新 chunk 文本中去掉重叠部分
            idx = new_result.text.find(overlap)
            if idx >= 0:
                deduped_text = new_result.text[idx + len(overlap):].strip()
                new_result.text = deduped_text

        return new_result

    @staticmethod
    def _find_common_substring(a: str, b: str, min_len: int = 3) -> str:
        """找到两个字符串的最长公共子串。"""
        if not a or not b:
            return ""
        longest = ""
        for i in range(len(a)):
            for j in range(len(b)):
                k = 0
                while (i + k < len(a) and j + k < len(b)
                       and a[i + k] == b[j + k]):
                    k += 1
                if k > len(longest) and k >= min_len:
                    longest = a[i:i + k]
        return longest

    def reset(self) -> None:
        """重置 chunk 拼接状态（新建课堂时调用）。"""
        self._chunk_texts = []
        self._chunk_segments = []


# ─── SSE 推送 ───

class TranscriptSSE:
    """SSE (Server-Sent Events) 转录文本推送器。

    用于路径 A 实时将转录文本推送到前端。
    """

    @staticmethod
    async def event_stream(
        audio_service: AudioService,
        check_interval: float = 1.0,
    ) -> AsyncGenerator[str, None]:
        """生成 SSE 事件流。

        Args:
            audio_service: 正在处理中的 AudioService 实例。
            check_interval: 检查新文本的间隔（秒）。

        Yields:
            SSE 格式的事件字符串。
        """
        last_index = 0
        while True:
            current_texts = audio_service._chunk_texts
            if len(current_texts) > last_index:
                # 有新文本
                for i in range(last_index, len(current_texts)):
                    yield f"data: {current_texts[i]}\n\n"
                last_index = len(current_texts)
            await asyncio.sleep(check_interval)
