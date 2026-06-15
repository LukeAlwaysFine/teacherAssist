"""
Session 相关 Pydantic Schema。

请求/响应验证模型。
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ─── Session ───

class SessionBase(BaseModel):
    """Session 基础字段。"""
    title: str = Field(default="未命名课堂", max_length=200)
    knowledge_outline: str | None = None
    student_name: str | None = Field(default=None, max_length=50, description="学生姓名")
    class_start_time: str | None = Field(default=None, max_length=20, description="上课开始时间（如 16:30）")
    class_end_time: str | None = Field(default=None, max_length=20, description="上课结束时间（如 18:30）")
    subject: str | None = Field(default=None, max_length=50, description="科目")
    textbook: str | None = Field(default=None, max_length=100, description="教材")
    grade: str | None = Field(default=None, max_length=50, description="年级")


class SessionCreate(SessionBase):
    """创建 Session。"""
    source: str = Field(default="upload", pattern="^(realtime|upload)$")


class SessionUpdateOutline(BaseModel):
    """更新知识点大纲。"""
    knowledge_outline: str = Field(..., min_length=1, description="知识点大纲文本，每行一个知识点")


class SessionResponse(SessionBase):
    """Session 响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    teacher_id: int
    audio_file_path: str | None = None
    status: str
    source: str
    stt_engine: str | None = None
    duration_seconds: int | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    """Session 列表响应。"""
    sessions: list[SessionResponse]
    total: int
    page: int
    page_size: int


# ─── Transcript ───

class TranscriptResponse(BaseModel):
    """转录响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_text: str | None = None
    raw_segments: list[dict] | None = None
    processing_time_seconds: float | None = None
    audio_duration_seconds: float | None = None


# ─── Analysis Report ───

class KnowledgePoint(BaseModel):
    """知识点覆盖。"""
    name: str
    covered: bool
    teacher_clarity: str | None = None  # 清晰/一般/不足
    student_understanding: str | None = None  # 已掌握/存疑/未掌握/不确定
    evidence: str | None = None
    time_spent_minutes: int | None = None


class InteractionAnalysis(BaseModel):
    """课堂互动分析。"""
    student_questions_count: int = 0
    key_questions: list[str] = Field(default_factory=list)
    engagement_level: str | None = None  # 高/中/低
    teacher_student_ratio: str | None = None  # "70:30"


class ReinforcementItem(BaseModel):
    """巩固建议。"""
    area: str
    reason: str | None = None
    suggested_exercise_type: str | None = None
    priority: str | None = None  # 高/中/低


class AnalysisReportResponse(BaseModel):
    """分析报告响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    cleaned_transcript: str | None = None
    knowledge_points: list[KnowledgePoint] | None = None
    student_mastery: list[dict] | None = None
    classroom_performance: InteractionAnalysis | None = None
    reinforcement_plan: list[ReinforcementItem] | None = None
    parent_report: str | None = None
    processing_time_seconds: float | None = None
    created_at: datetime


# ─── Session 详情（含转录 + 报告）───

class SessionDetailResponse(SessionResponse):
    """Session 详情（含关联数据）。"""
    transcript: TranscriptResponse | None = None
    analysis: AnalysisReportResponse | None = None


# ─── 状态查询 ───

class SystemStatusResponse(BaseModel):
    """服务器系统状态。"""
    gpu_available: bool
    gpu_info: str | None
    cpu_info: str
    api_configured: bool
    default_engine: str
    available_engines: list[str]


class EngineInfoResponse(BaseModel):
    """单个引擎信息。"""
    id: str
    name: str
    description: str
    speed: str
    cost: str
    pros: list[str]
    cons: list[str]
    hardware_requirements: str
    available: bool = True
    unavailable_reason: str | None = None


# ─── 统一响应 ───

class APIResponse(BaseModel):
    """统一 API 响应格式。"""
    code: int = 200
    message: str = "成功"
    data: Any | None = None
