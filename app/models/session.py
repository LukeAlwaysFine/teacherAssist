"""
课堂 Session 模型。

记录每次课堂教学的元信息、音频文件、转录状态。
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.transcript import Transcript
    from app.models.analysis import AnalysisReport


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), default="未命名课堂")

    # 关联教师
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # 学生姓名
    student_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 上课时间
    class_start_time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    class_end_time: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # 音频文件
    audio_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 教材大纲选择（科目/教材/年级）
    subject: Mapped[str | None] = mapped_column(String(50), nullable=True)
    textbook: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # 知识点大纲（JSON 文本，可为空，分析前输入即可）
    knowledge_outline: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 状态机: recording → transcribing → analyzing → completed / failed
    status: Mapped[str] = mapped_column(String(20), default="created")

    # 音频来源: "realtime" | "upload"
    source: Mapped[str] = mapped_column(String(20), default="upload")

    # 使用的 STT 引擎
    stt_engine: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # 音频时长（秒）
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 错误信息（失败时记录）
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关联
    teacher: Mapped["User"] = relationship(back_populates="sessions")
    transcripts: Mapped[list["Transcript"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    analysis: Mapped["AnalysisReport | None"] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Session(id={self.id}, title='{self.title}', status='{self.status}')>"

    @property
    def is_processing(self) -> bool:
        """是否正在处理中。"""
        return self.status in ("recording", "transcribing", "analyzing")

    @property
    def is_ready_for_analysis(self) -> bool:
        """是否满足分析条件（转录完成 + 大纲已录入）。"""
        return self.status == "transcribed" and bool(self.knowledge_outline)
