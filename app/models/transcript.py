"""
Transcript 转录模型。

存储 STT 转录的完整文本和分段信息。
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.session import Session


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"), unique=True, index=True
    )

    # 完整转录文本
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 原始分段数据（JSON）:
    # [{chunk_index, start_time, end_time, text}, ...]
    raw_segments: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # STT 处理统计
    processing_time_seconds: Mapped[float | None] = mapped_column(nullable=True)
    audio_duration_seconds: Mapped[float | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 关联
    session: Mapped["Session"] = relationship(back_populates="transcripts")

    def __repr__(self) -> str:
        text_preview = (
            self.full_text[:50] + "..."
            if self.full_text and len(self.full_text) > 50
            else self.full_text
        )
        return f"<Transcript(id={self.id}, text='{text_preview}')>"
