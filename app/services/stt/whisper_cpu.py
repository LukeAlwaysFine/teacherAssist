"""
Whisper.cpp CPU 引擎。

使用 pywhispercpp 在 CPU 上运行，无需 GPU。
1 小时音频 ≈ 12-20 分钟处理时间。

支持格式：WAV 原生；MP3/FLAC/OGG/M4A/AAC 等需 FFMPEG。
"""
import asyncio
import logging
import os
import tempfile
import time
import wave
from pathlib import Path
from typing import Callable, Optional

from app.services.stt.base import BaseSTTEngine, STTResult

logger = logging.getLogger(__name__)


def _ensure_ffmpeg_in_path() -> None:
    """确保 FFMPEG 二进制在 PATH 中（whisper.cpp 解码非 WAV 格式需要）。

    whisper.cpp 内部通过 popen("ffmpeg") 调用 FFMPEG，
    所以需要一个名为 ffmpeg.exe 的二进制在 PATH 上。

    优先级：系统 FFMPEG > imageio-ffmpeg（自动创建 ffmpeg.exe 副本）。
    """
    import shutil
    import stat

    # 1. 系统已有 FFMPEG
    if shutil.which("ffmpeg"):
        return

    # 2. imageio-ffmpeg — 二进制名为 ffmpeg-win-x86_64-v7.1.exe，
    #    需要创建 ffmpeg.exe 副本才能被 whisper.cpp 找到
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        ffmpeg_src = Path(get_ffmpeg_exe())
        ffmpeg_dir = ffmpeg_src.parent
        ffmpeg_dst = ffmpeg_dir / "ffmpeg.exe"

        # 如果副本不存在或已过期，创建/更新
        if not ffmpeg_dst.exists() or ffmpeg_src.stat().st_mtime > ffmpeg_dst.stat().st_mtime:
            shutil.copy2(ffmpeg_src, ffmpeg_dst)
            logger.info(f"Created ffmpeg.exe from {ffmpeg_src.name}")

        os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
        return
    except ImportError:
        pass

    logger.warning(
        "FFMPEG not found — only WAV files are supported. "
        "Install imageio-ffmpeg for MP3/FLAC/OGG/M4A support."
    )


class STTEngineError(Exception):
    """STT 引擎通用异常。"""
    pass


def _detect_audio_duration(audio_path: Path) -> float | None:
    """检测音频文件时长（秒）。

    优先级：WAV 直接解析 > ffprobe 读文件头 > pydub。
    ffprobe 对 MP3/M4A 等格式毫秒级完成，无需解码整个文件。
    失败时返回 None。
    """
    suffix = audio_path.suffix.lower()
    # 1. WAV 文件 — 直接解析
    if suffix in (".wav", ".wave"):
        try:
            with wave.open(str(audio_path), "r") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return frames / rate
        except Exception:
            pass

    # 2. ffprobe — 读文件头元数据（imageio-ffmpeg 自带，毫秒级）
    duration = _detect_duration_ffprobe(audio_path)
    if duration is not None:
        return duration

    # 3. pydub — 最后兜底
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(str(audio_path))
        return audio.duration_seconds
    except Exception:
        pass
    return None


def _detect_duration_ffprobe(audio_path: Path) -> float | None:
    """通过 ffprobe 检测音频时长（秒）。

    ffprobe 只读取文件头元数据，几乎瞬时完成（毫秒级），
    支持 MP3 / M4A / FLAC / OGG / AAC / WAV 等所有常见格式。

    Args:
        audio_path: 音频文件路径。

    Returns:
        音频时长（秒），失败时返回 None。
    """
    import json
    import shutil
    import subprocess

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        # 尝试 imageio-ffmpeg 自带的 ffprobe
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            ffmpeg_exe = Path(get_ffmpeg_exe())
            ffprobe_candidate = ffmpeg_exe.parent / "ffprobe.exe"
            if ffprobe_candidate.exists():
                ffprobe = str(ffprobe_candidate)
        except ImportError:
            pass

    if not ffprobe:
        return None

    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_format", str(audio_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            duration = float(info.get("format", {}).get("duration", 0))
            if duration > 0:
                logger.debug(
                    f"ffprobe detected duration: {duration:.1f}s "
                    f"({audio_path.suffix})"
                )
                return duration
    except Exception:
        pass
    return None


class WhisperCPUEngine(BaseSTTEngine):
    """Whisper.cpp CPU 引擎。

    使用 GGML 模型在 CPU 上高效推理。
    """

    def __init__(self, model_name: str = "medium") -> None:
        super().__init__(model_name)
        self._model = None

    @property
    def engine_name(self) -> str:
        return "whisper_cpu"

    @property
    def engine_label(self) -> str:
        return "CPU 本地处理"

    def _get_model(self):
        """延迟加载模型（首次使用时加载）。"""
        if self._model is None:
            try:
                from pywhispercpp.model import Model
                models_dir = os.environ.get("WHISPER_MODELS_DIR") or None
                self._model = Model(self.model_name, models_dir=models_dir)
                logger.info(f"Whisper.cpp model '{self.model_name}' loaded on CPU")
            except ImportError:
                raise STTEngineError(
                    "pywhispercpp 未安装。请运行: pip install pywhispercpp"
                )
            except Exception as e:
                raise STTEngineError(f"模型加载失败: {e}")
        return self._model

    async def transcribe(
        self,
        audio_path: Path,
        progress_callback: Optional[Callable[[float, float], None]] = None,
    ) -> STTResult:
        """转写完整音频文件。

        Args:
            audio_path: 音频文件路径。
            progress_callback: 进度回调 (progress_pct, latest_segment_time_seconds)。
        """
        # 确保 FFMPEG 可用（非 WAV 格式需要）
        _ensure_ffmpeg_in_path()

        start = time.time()

        # 预检测音频时长
        audio_duration = _detect_audio_duration(audio_path)
        if audio_duration:
            logger.info(f"Detected audio duration: {audio_duration:.1f}s")
        else:
            logger.info("Could not detect audio duration, progress will be indeterminate")

        try:
            model = self._get_model()
            audio_path_str = str(audio_path)

            # 进度追踪状态（闭包捕获）
            last_segment_time = 0.0
            last_progress_pct = 0.0

            def on_new_segment(seg):
                nonlocal last_segment_time, last_progress_pct
                try:
                    seg_time = seg.t1 / 100.0 if hasattr(seg, 't1') else 0
                    if seg_time > last_segment_time:
                        last_segment_time = seg_time
                    # 基于音频时长计算进度
                    if audio_duration and audio_duration > 0:
                        seg_pct = min(last_segment_time / audio_duration * 100, 95.0)
                    else:
                        # 无时长（极少见，ffprobe + pydub 都不可用）：
                        # 基于处理时间保守估算，渐近趋近 80%，不伪造精确数字
                        elapsed = time.time() - start
                        seg_pct = min(elapsed / max(elapsed + 30, 1) * 80, 80.0)
                    # 取段进度和当前进度的较大值，确保不倒退
                    pct = max(last_progress_pct, seg_pct)
                    if pct > last_progress_pct + 0.3:
                        last_progress_pct = pct
                        if progress_callback:
                            try:
                                progress_callback(pct, last_segment_time)
                            except Exception:
                                pass
                except Exception:
                    pass

            # 心跳：段之间缓慢推进进度（每 2 秒一次）
            async def _heartbeat():
                nonlocal last_progress_pct
                while True:
                    await asyncio.sleep(2.0)
                    if last_segment_time > 0:
                        elapsed = time.time() - start
                        if audio_duration and audio_duration > 0:
                            # 已知时长：基于处理时间做保守推进（不超过段进度）
                            time_pct = min(elapsed / audio_duration * 25, 90.0)
                        else:
                            # 未知时长：渐近趋近 80%，让前端知道还在处理中
                            time_pct = min(elapsed / max(elapsed + 30, 1) * 80, 80.0)
                        pct = max(last_progress_pct, time_pct, 0)
                        pct = min(pct, 95.0)
                        if pct > last_progress_pct + 0.3:
                            last_progress_pct = pct
                            if progress_callback:
                                try:
                                    progress_callback(pct, last_segment_time)
                                except Exception:
                                    pass

            heartbeat_task = asyncio.create_task(_heartbeat())

            logger.info(f"Starting whisper.cpp transcription: {audio_path_str}")
            result = model.transcribe(
                audio_path_str,
                new_segment_callback=on_new_segment,
                language="zh",
            )
            # 停止心跳
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            logger.info(
                f"Whisper.cpp model.transcribe() returned: "
                f"{len(result) if result else 0} segments"
            )
            # pywhispercpp returns List[Segment] directly

            segments = []
            full_text_parts = []
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
                f"CPU transcription complete: {len(segments)} segments, "
                f"{elapsed:.1f}s processing, {duration:.1f}s audio "
                f"(ratio: {elapsed/max(duration,0.1):.2f}x)"
            )
            return STTResult(
                text=full_text,
                segments=segments,
                engine_name=self.engine_name,
                processing_time_seconds=elapsed,
                audio_duration_seconds=duration,
            )
        except Exception as e:
            logger.error(f"CPU transcription failed: {e}")
            raise STTEngineError(f"转录失败: {e}") from e

    async def transcribe_chunk(self, audio_bytes: bytes) -> STTResult:
        """转写音频片段。

        将 bytes 写入临时文件后调用 transcribe。
        """
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
            "id": "whisper_cpu",
            "name": "💻 处理器本地处理",
            "description": "使用 Whisper.cpp 在处理器上运行，无需额外硬件",
            "speed": "1 小时 ≈ 12-20 分钟",
            "cost": "免费",
            "pros": [
                "完全免费，本地处理",
                "无需独立显卡",
                "断网也能使用",
                "隐私数据不出本地",
            ],
            "cons": [
                "处理速度取决于 CPU 性能",
                "i5 以下处理器可能需要 20 分钟以上",
            ],
            "hardware_requirements": "CPU: Intel i5 / AMD Ryzen 5 或更高，无需 GPU",
        }
