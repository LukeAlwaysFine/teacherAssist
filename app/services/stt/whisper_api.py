"""
OpenAI Whisper API 引擎。

通过 OpenAI API 进行云端转录，无需本地算力。
1 小时音频 ≈ 3-8 分钟处理时间，¥1.3-2.6/小时。
"""
import logging
import time
from pathlib import Path

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.stt.base import BaseSTTEngine, STTResult

logger = logging.getLogger(__name__)


class STTEngineError(Exception):
    """STT 引擎通用异常。"""
    pass


class WhisperAPIEngine(BaseSTTEngine):
    """OpenAI Whisper API 引擎。

    使用 OpenAI 云端 Whisper 模型进行转录。
    """

    def __init__(self, model_name: str = "whisper-1") -> None:
        super().__init__(model_name)
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            raise STTEngineError(
                "OPENAI_API_KEY 未配置。请在 .env 中设置 OPENAI_API_KEY"
            )
        self._client = AsyncOpenAI(api_key=api_key)

    @property
    def engine_name(self) -> str:
        return "whisper_api"

    @property
    def engine_label(self) -> str:
        return "云端 API 处理"

    async def transcribe(self, audio_path: Path, progress_callback=None) -> STTResult:
        """通过 OpenAI API 转写音频文件。"""
        start = time.time()

        try:
            with open(audio_path, "rb") as audio_file:
                response = await self._client.audio.transcriptions.create(
                    model=self.model_name,
                    file=audio_file,
                    response_format="verbose_json",
                    language="zh",
                )

            segments = []
            full_text_parts = []
            if hasattr(response, 'segments') and response.segments:
                for seg in response.segments:
                    segments.append({
                        "start": seg.get("start", 0),
                        "end": seg.get("end", 0),
                        "text": seg.get("text", "").strip(),
                    })
                    full_text_parts.append(seg.get("text", "").strip())
            else:
                full_text = response.text or ""
                segments = [{"start": 0, "end": 0, "text": full_text}]
                full_text_parts = [full_text]

            full_text = " ".join(full_text_parts)
            elapsed = time.time() - start
            duration = segments[-1]["end"] if segments else 0

            logger.info(
                f"API transcription complete: {len(segments)} segments, "
                f"{elapsed:.1f}s, model={response.model if hasattr(response, 'model') else self.model_name}"
            )
            return STTResult(
                text=full_text,
                segments=segments,
                engine_name=self.engine_name,
                processing_time_seconds=elapsed,
                audio_duration_seconds=duration,
            )
        except Exception as e:
            logger.error(f"API transcription failed: {e}")
            raise STTEngineError(f"Whisper API 转录失败: {e}") from e

    async def transcribe_chunk(self, audio_bytes: bytes) -> STTResult:
        """转写音频片段。

        OpenAI API 支持直接传 bytes（文件名命名为特定扩展名）。
        """
        start = time.time()
        try:
            import io
            audio_io = io.BytesIO(audio_bytes)
            audio_io.name = "chunk.webm"

            response = await self._client.audio.transcriptions.create(
                model=self.model_name,
                file=audio_io,
                response_format="verbose_json",
                language="zh",
            )

            segments = []
            full_text_parts = []
            if hasattr(response, 'segments') and response.segments:
                for seg in response.segments:
                    segments.append({
                        "start": seg.get("start", 0),
                        "end": seg.get("end", 0),
                        "text": seg.get("text", "").strip(),
                    })
                    full_text_parts.append(seg.get("text", "").strip())
            else:
                full_text = response.text or ""
                segments = [{"start": 0, "end": 0, "text": full_text}]
                full_text_parts = [full_text]

            full_text = " ".join(full_text_parts)
            elapsed = time.time() - start

            return STTResult(
                text=full_text,
                segments=segments,
                engine_name=self.engine_name,
                processing_time_seconds=elapsed,
                audio_duration_seconds=0,
            )
        except Exception as e:
            raise STTEngineError(f"API Chunk 转录失败: {e}") from e

    @staticmethod
    def get_engine_info() -> dict:
        return {
            "id": "whisper_api",
            "name": "☁️ Whisper 云端",
            "description": "通过 Whisper 云端接口转录，中文准确率最高",
            "speed": "1 小时 ≈ 3-8 分钟",
            "cost": "¥1.3-2.6 / 小时",
            "pros": [
                "中文准确率最高（95-98%）",
                "不占用本地处理器/显卡",
                "无需高端硬件",
                "支持 gpt-4o-mini-transcribe 更便宜",
            ],
            "cons": [
                "按量付费，40 节/月 ≈ ¥55-110",
                "需要联网",
                "音频上传至 OpenAI 服务器（隐私考量）",
                "高峰期可能排队",
            ],
            "hardware_requirements": "任何能上网的电脑，无需特殊硬件",
        }
