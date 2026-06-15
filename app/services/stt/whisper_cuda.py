"""
Whisper.cpp CUDA 引擎。

使用 pywhispercpp + CUDA 在 GPU 上高效推理。
1 小时音频 ≈ 2-5 分钟处理时间。
"""
import logging
import os
import tempfile
import time
from pathlib import Path

from app.services.stt.base import BaseSTTEngine, STTResult
from app.services.stt.whisper_cpu import _ensure_ffmpeg_in_path, _detect_audio_duration

logger = logging.getLogger(__name__)


class STTEngineError(Exception):
    """STT 引擎通用异常。"""
    pass


class WhisperCUDAEngine(BaseSTTEngine):
    """Whisper.cpp CUDA 引擎。

    需要 NVIDIA GPU（6GB+ 显存）并安装 CUDA 版 pywhispercpp。
    """

    def __init__(self, model_name: str = "medium") -> None:
        super().__init__(model_name)
        self._model = None

    @property
    def engine_name(self) -> str:
        return "whisper_cuda"

    @property
    def engine_label(self) -> str:
        return "GPU 加速处理"

    def _get_model(self):
        """延迟加载 CUDA 模型。"""
        if self._model is None:
            try:
                import torch
                if not torch.cuda.is_available():
                    raise STTEngineError(
                        "CUDA 不可用，请检查 NVIDIA 驱动和 CUDA 安装"
                    )
                device_name = torch.cuda.get_device_name(0)
                logger.info(f"Using GPU: {device_name}")

                from pywhispercpp.model import Model
                models_dir = os.environ.get("WHISPER_MODELS_DIR") or None
                self._model = Model(self.model_name, models_dir=models_dir, n_threads=4)
                logger.info(
                    f"Whisper.cpp CUDA model '{self.model_name}' loaded on {device_name}"
                )
            except ImportError:
                raise STTEngineError(
                    "pywhispercpp 未安装。请运行: pip install pywhispercpp"
                )
            except STTEngineError:
                raise
            except Exception as e:
                raise STTEngineError(f"CUDA 模型加载失败: {e}")
        return self._model

    async def transcribe(self, audio_path: Path, progress_callback=None) -> STTResult:
        """转写完整音频文件（GPU 加速）。"""
        # 确保 FFMPEG 可用（非 WAV 格式需要）
        _ensure_ffmpeg_in_path()

        start = time.time()

        try:
            model = self._get_model()
            logger.info(f"Starting whisper.cpp CUDA transcription: {str(audio_path)}")
            result = model.transcribe(str(audio_path))
            logger.info(
                f"Whisper.cpp CUDA model.transcribe() returned: "
                f"{len(result) if result else 0} segments"
            )

            segments = []
            full_text_parts = []
            # pywhispercpp returns List[Segment] directly
            for seg in result:
                # 兼容不同版本的 pywhispercpp 属性命名
                t0 = getattr(seg, 't0', 0) / 100.0 if hasattr(seg, 't0') else 0
                t1 = getattr(seg, 't1', 0) / 100.0 if hasattr(seg, 't1') else 0
                text = (getattr(seg, 'text', '') or '').strip()
                segments.append({
                    "start": t0,
                    "end": t1,
                    "text": text,
                })
                if text:
                    full_text_parts.append(text)

            full_text = " ".join(full_text_parts)
            elapsed = time.time() - start
            duration = segments[-1]["end"] if segments else 0

            logger.info(
                f"CUDA transcription complete: {len(segments)} segments, "
                f"{elapsed:.1f}s processing, {duration:.1f}s audio "
                f"(ratio: {elapsed/duration:.2f}x)"
            )
            return STTResult(
                text=full_text,
                segments=segments,
                engine_name=self.engine_name,
                processing_time_seconds=elapsed,
                audio_duration_seconds=duration,
            )
        except Exception as e:
            logger.error(f"CUDA transcription failed: {e}")
            raise STTEngineError(f"GPU 转录失败: {e}") from e

    async def transcribe_chunk(self, audio_bytes: bytes) -> STTResult:
        """转写音频片段。"""
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False
            ) as tmp:
                tmp.write(audio_bytes)
                tmp_path = Path(tmp.name)

            result = await self.transcribe(tmp_path)
            return result
        except Exception as e:
            raise STTEngineError(f"Chunk 转录失败: {e}") from e
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    @staticmethod
    def get_engine_info() -> dict:
        return {
            "id": "whisper_cuda",
            "name": "🚀 显卡加速处理",
            "description": "使用 Whisper.cpp + CUDA 在显卡上高速推理",
            "speed": "1 小时 ≈ 2-5 分钟",
            "cost": "免费",
            "pros": [
                "速度最快，1 小时音频仅需 2-5 分钟",
                "完全免费，本地处理",
                "适合频繁使用场景",
            ],
            "cons": [
                "需要 NVIDIA 显卡（6GB+ 显存）",
                "需要安装 CUDA 驱动",
                "笔记本电脑 GPU 可能性能不足",
            ],
            "hardware_requirements": "NVIDIA GPU，6GB+ 显存，CUDA 11.0+",
        }
