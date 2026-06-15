"""
转录进度追踪器。

在内存中追踪每个 session 的转录进度，供前端轮询。

状态机：pending → transcribing → finalizing → completed / failed
  - transcribing: 正在处理音频，不断有新分段产出
  - finalizing: 最后一段已产出，正在等待 whisper 最终化（VAD 尾清）
  - 前端可据此区分"还在跑"和"快好了"
"""
import time
from dataclasses import dataclass, field
from typing import Optional


# finalizing 触发阈值：进度到达此值且 N 秒无更新，自动转入 finalizing
FINALIZING_PCT_THRESHOLD = 99.0
FINALIZING_STALE_SECONDS = 8.0  # 超时 8 秒无进度更新 → 转入 finalizing


@dataclass
class TranscriptionProgress:
    """单个转录任务的进度。"""
    session_id: int
    status: str = "pending"  # pending | transcribing | finalizing | completed | failed
    progress_pct: float = 0.0
    start_time: float | None = None
    end_time: float | None = None
    audio_duration_seconds: float | None = None
    latest_segment_time: float = 0.0
    error_message: str | None = None
    _last_update_at: float = 0.0  # 最后一次 update() 的时间戳

    @property
    def elapsed_seconds(self) -> float | None:
        """已用时间（秒）。"""
        if self.start_time is None:
            return None
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def estimated_remaining_seconds(self) -> float | None:
        """预估剩余时间（秒）。"""
        if self.audio_duration_seconds is None or self.elapsed_seconds is None:
            return None
        if self.progress_pct <= 0:
            return None
        processed_ratio = self.progress_pct / 100.0
        total_estimated = self.elapsed_seconds / processed_ratio
        remaining = total_estimated - self.elapsed_seconds
        return max(0, remaining)

    @property
    def seconds_since_last_update(self) -> float:
        """距最后一次进度更新的秒数。"""
        if self._last_update_at <= 0:
            return 0
        return time.time() - self._last_update_at


class TranscriptionTracker:
    """转录进度追踪器（单例，内存存储）。

    自动检测 finalizing 状态：当进度达到阈值（99%）且在 FINALIZING_STALE_SECONDS
    内无新的进度更新时，自动从 transcribing 转为 finalizing。
    """

    def __init__(self) -> None:
        self._tasks: dict[int, TranscriptionProgress] = {}

    def start(self, session_id: int, audio_duration: float | None = None) -> TranscriptionProgress:
        """标记转录开始。"""
        now = time.time()
        progress = TranscriptionProgress(
            session_id=session_id,
            status="transcribing",
            start_time=now,
            audio_duration_seconds=audio_duration,
            _last_update_at=now,
        )
        self._tasks[session_id] = progress
        return progress

    def update(self, session_id: int, progress_pct: float, latest_segment_time: float = 0.0) -> None:
        """更新进度百分比。

        进度到达 99.9% 后不再递增 — 防止前端误以为已完成。
        实际完成由 complete() 负责标记。
        """
        if session_id in self._tasks:
            p = self._tasks[session_id]
            p.progress_pct = min(progress_pct, 99.9)
            p.latest_segment_time = latest_segment_time
            p._last_update_at = time.time()
            # 恢复为 transcribing（可能从 finalizing 回来，说明又有新分段产出）
            if p.status == "finalizing":
                p.status = "transcribing"

    def complete(self, session_id: int) -> TranscriptionProgress:
        """标记转录完成。"""
        if session_id in self._tasks:
            p = self._tasks[session_id]
            p.status = "completed"
            p.progress_pct = 100.0
            p.end_time = time.time()
            p._last_update_at = time.time()
            return p
        raise KeyError(f"Session {session_id} 未被追踪")

    def fail(self, session_id: int, error: str) -> TranscriptionProgress:
        """标记转录失败。"""
        if session_id in self._tasks:
            p = self._tasks[session_id]
            p.status = "failed"
            p.end_time = time.time()
            p.error_message = error
            p._last_update_at = time.time()
            return p
        raise KeyError(f"Session {session_id} 未被追踪")

    def get(self, session_id: int) -> TranscriptionProgress | None:
        """获取进度。

        自动检测 finalizing 状态：
        进度 ≥ FINALIZING_PCT_THRESHOLD 且 FINALIZING_STALE_SECONDS 未更新
        → 自动转为 finalizing（不修改内部状态，仅透传状态给前端）。
        """
        progress = self._tasks.get(session_id)
        if progress is None:
            return None

        # 只在 transcribing 状态下检测是否需要转为 finalizing
        if progress.status == "transcribing":
            if (
                progress.seconds_since_last_update >= FINALIZING_STALE_SECONDS
                and progress.latest_segment_time > 0
            ):
                # 有已知时长：进度到 99% 才触发 finalizing
                # 未知时长：长时间无新分段产出即视为 finalizing
                if (
                    progress.audio_duration_seconds
                    and progress.progress_pct < FINALIZING_PCT_THRESHOLD
                ):
                    pass  # 时长已知但进度未到 99%，继续 transcribing
                else:
                    import copy
                    p = copy.copy(progress)
                    p.status = "finalizing"
                    return p

        return progress

    def remove(self, session_id: int) -> None:
        """清理任务记录。"""
        self._tasks.pop(session_id, None)


# 全局单例
tracker = TranscriptionTracker()
