"""
AnalysisReport 分析报告模型。

存储 LLM 生成的课堂分析结果。
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.session import Session


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"), unique=True, index=True
    )

    # LLM 清理后的转录（含角色标注）
    cleaned_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 知识点覆盖分析
    # [{"name": "...", "covered": true, "teacher_clarity": "...",
    #   "student_understanding": "...", "evidence": "...",
    #   "time_spent_minutes": 12}, ...]
    knowledge_points: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 学生掌握程度
    # [{"point": "...", "level": "...", "evidence": "..."}, ...]
    student_mastery: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 课堂互动表现
    # {"student_questions_count": 5, "key_questions": [...],
    #  "engagement_level": "高", "teacher_student_ratio": "70:30"}
    classroom_performance: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 课后巩固建议
    # [{"area": "...", "reason": "...", "suggested_exercise_type": "...",
    #   "priority": "高"}, ...]
    reinforcement_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 家长反馈报告（生成后缓存，避免重复调用 LLM）
    parent_report: Mapped[str | None] = mapped_column(Text, nullable=True)

    # LLM 原始输出（调试用）
    raw_llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 分析耗时（秒）
    processing_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 教师对学生表现的定性观察（生成家长报告时结合使用）
    teacher_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 关联
    session: Mapped["Session"] = relationship(back_populates="analysis")

    def __repr__(self) -> str:
        return f"<AnalysisReport(id={self.id}, session_id={self.session_id})>"
