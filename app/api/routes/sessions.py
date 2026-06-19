"""
Session API 路由。

课堂录制、转录、分析的核心端点。
"""
import asyncio
import io
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from urllib.parse import quote as _url_quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.db import AsyncSessionLocal
from app.models.user import User
from app.models.session import Session
from app.models.transcript import Transcript
from app.models.analysis import AnalysisReport
from app.schemas.session import (
    SessionCreate,
    SessionResponse,
    SessionListResponse,
    SessionDetailResponse,
    SessionUpdateOutline,
    TranscriptResponse,
    AnalysisReportResponse,
    APIResponse,
    SystemStatusResponse,
    EngineInfoResponse,
    ParentReportReviseRequest,
    ReportTemplateCreate,
    ReportTemplateUpdate,
    ReportTemplateResponse,
)
from app.services.stt import get_system_info, create_stt_engine
from app.services.stt.whisper_cpu import WhisperCPUEngine, _detect_audio_duration
from app.services.audio_service import AudioService, TranscriptSSE
from app.services.transcription_tracker import tracker, TranscriptionProgress

# ─── 分析进度追踪（内存） ───
import time as _time

_analysis_progress: dict[int, dict] = {}  # session_id → {progress_pct, stage, status}

_ANALYSIS_STAGES = [
    (0, 30, "正在清理转录文本..."),
    (30, 60, "正在分析知识点覆盖..."),
    (60, 80, "正在评估学生掌握程度..."),
    (80, 92, "正在生成巩固建议..."),
    (92, 99, "正在整理分析报告..."),
]

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])


def _unwrap_retry_error(exc: Exception) -> str:
    """提取 RetryError 中的原始错误信息，避免展示给用户看不懂的堆栈。

    tenacity 的 RetryError 包装了最后一次失败的异常，
    直接 str() 会显示为 "RetryError[<Future at 0x...>]" 难以理解。
    """
    try:
        from tenacity import RetryError
        if isinstance(exc, RetryError):
            last = exc.last_attempt.exception() if exc.last_attempt else None
            if last:
                return str(last)
    except Exception:
        pass
    return str(exc)


async def _create_ai_service(db: AsyncSession, user_id: int) -> "AIService":
    """创建 AIService，自动加载用户 LLM 配置。"""
    from sqlalchemy import select as _select
    from app.models.user_llm_config import UserLLMConfig
    from app.services.ai_service import AIService

    result = await db.execute(
        _select(UserLLMConfig).where(UserLLMConfig.user_id == user_id)
    )
    config = result.scalar_one_or_none()
    return AIService(user_config=config)

# 上传文件目录
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 活跃的实时录制会话（路径 A）
_active_sessions: dict[int, AudioService] = {}


def _get_audio_dir(session_id: int) -> Path:
    """获取 session 的音频存储目录。"""
    d = UPLOAD_DIR / str(session_id)
    d.mkdir(parents=True, exist_ok=True)
    return d



# ═══════════════════════════════════════════════════════════
# 系统状态
# ═══════════════════════════════════════════════════════════

@router.get("/status", response_model=APIResponse)
async def get_system_status():
    """获取服务器 STT 引擎状态。"""
    info = get_system_info()
    return APIResponse(data=SystemStatusResponse(**info).model_dump())


@router.get("/engines", response_model=APIResponse)
async def get_engine_list():
    """获取所有 STT 引擎信息（含不可用引擎及原因）。"""
    info = get_system_info()
    engines: list[dict] = []

    # ── CPU 引擎 — 始终可用 ──
    cpu_info = WhisperCPUEngine.get_engine_info()
    cpu_info["available"] = True
    engines.append(cpu_info)

    # ── CUDA 引擎 ──
    cuda_available = "whisper_cuda" in info["available_engines"]
    try:
        from app.services.stt.whisper_cuda import WhisperCUDAEngine
        cuda_info = WhisperCUDAEngine.get_engine_info()
    except ImportError:
        cuda_info = {
            "id": "whisper_cuda",
            "name": "🚀 显卡加速处理",
            "description": "使用 Whisper.cpp + CUDA 在显卡上高速推理",
            "speed": "1 小时 ≈ 2-5 分钟",
            "cost": "免费",
            "pros": ["速度最快", "完全免费，本地处理"],
            "cons": ["需要 NVIDIA 显卡"],
            "hardware_requirements": "NVIDIA 显卡，6GB+ 显存，CUDA 11.0+",
        }
    cuda_info["available"] = cuda_available
    if not cuda_available:
        cuda_info["unavailable_reason"] = (
            "未检测到 NVIDIA 显卡或 CUDA 不可用。"
            "请确认：1) 已安装 NVIDIA 显卡 2) 已安装 CUDA 版 PyTorch"
        )
    engines.append(cuda_info)

    # ── API 引擎 ──
    api_available = info["api_configured"]
    try:
        from app.services.stt.whisper_api import WhisperAPIEngine
        api_info = WhisperAPIEngine.get_engine_info()
    except (ImportError, Exception):
        api_info = {
            "id": "whisper_api",
            "name": "☁️ Whisper 云端",
            "description": "通过 Whisper 云端接口转录，中文准确率最高",
            "speed": "1 小时 ≈ 3-8 分钟",
            "cost": "¥1.3-2.6 / 小时",
            "pros": ["中文准确率最高", "不占用本地处理器/显卡"],
            "cons": ["按量付费", "需要联网", "音频上传至云端"],
            "hardware_requirements": "任何能上网的电脑",
        }
    api_info["available"] = api_available
    if not api_available:
        api_info["unavailable_reason"] = (
            "未配置 OpenAI API Key。请在 .env 中设置 OPENAI_API_KEY=sk-..."
        )
    engines.append(api_info)

    return APIResponse(data={
        "engines": [EngineInfoResponse(**e).model_dump() for e in engines],
        "default_engine": info["default_engine"],
    })


# ═══════════════════════════════════════════════════════════
# Session CRUD
# ═══════════════════════════════════════════════════════════

@router.post("/sessions", response_model=APIResponse, status_code=201)
async def create_session(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建课堂记录。"""
    session = Session(
        title=data.title,
        teacher_id=current_user.id,
        source=data.source,
        knowledge_outline=data.knowledge_outline,
        student_name=data.student_name,
        class_start_time=data.class_start_time,
        class_end_time=data.class_end_time,
        subject=data.subject,
        textbook=data.textbook,
        grade=data.grade,
        status="created",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return APIResponse(
        code=201,
        message="课堂已创建",
        data=SessionResponse.model_validate(session).model_dump(),
    )


@router.get("/sessions", response_model=APIResponse)
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取历史课堂列表（分页）。"""
    query = select(Session).where(Session.teacher_id == current_user.id)
    count_query = select(func.count(Session.id)).where(
        Session.teacher_id == current_user.id
    )

    if status:
        query = query.where(Session.status == status)
        count_query = count_query.where(Session.status == status)

    query = query.order_by(Session.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    sessions = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    return APIResponse(
        data=SessionListResponse(
            sessions=[SessionResponse.model_validate(s) for s in sessions],
            total=total,
            page=page,
            page_size=page_size,
        ).model_dump(),
    )


@router.get("/sessions/{session_id}", response_model=APIResponse)
async def get_session_detail(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取课堂详情（含转录 + 分析报告）。"""
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    # 先用 SessionResponse 转换，避免触发 ORM lazy-load 关系属性
    session_resp = SessionResponse.model_validate(session)
    detail = SessionDetailResponse(**session_resp.model_dump())

    # 加载转录
    transcript_result = await db.execute(
        select(Transcript).where(Transcript.session_id == session_id)
    )
    transcript = transcript_result.scalar_one_or_none()
    if transcript:
        detail.transcript = TranscriptResponse.model_validate(transcript)

    # 加载分析报告
    analysis_result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.session_id == session_id)
    )
    analysis = analysis_result.scalar_one_or_none()
    if analysis:
        detail.analysis = AnalysisReportResponse.model_validate(analysis)

    return APIResponse(data=detail.model_dump())


# ═══════════════════════════════════════════════════════════
# 已转录文档列表
# ═══════════════════════════════════════════════════════════

@router.get("/transcripts", response_model=APIResponse)
async def list_transcripts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前教师所有已转录文档列表（含课堂信息便于辨认）。

    返回所有状态为 transcribed/completed 的 session 的转录文档。
    """
    # 查询当前教师所有有转录的 session
    result = await db.execute(
        select(Session, Transcript)
        .join(Transcript, Transcript.session_id == Session.id)
        .where(
            Session.teacher_id == current_user.id,
            Session.status.in_(["transcribed", "completed"]),
        )
        .order_by(Session.created_at.desc())
    )
    rows = result.all()

    transcripts = []
    for session, transcript in rows:
        transcripts.append({
            "id": transcript.id,
            "session_id": session.id,
            "session_title": session.title,
            "student_name": session.student_name,
            "class_start_time": session.class_start_time,
            "class_end_time": session.class_end_time,
            "subject": session.subject,
            "grade": session.grade,
            "full_text": transcript.full_text,
            "text_length": len(transcript.full_text) if transcript.full_text else 0,
            "audio_duration_seconds": transcript.audio_duration_seconds,
            "created_at": transcript.created_at.isoformat() if transcript.created_at else None,
        })

    return APIResponse(data={
        "transcripts": transcripts,
        "total": len(transcripts),
    })


# ═══════════════════════════════════════════════════════════
# 路径 A: 实时 chunk 上传
# ═══════════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/chunk", response_model=APIResponse)
async def upload_chunk(
    session_id: int,
    chunk_index: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传音频 chunk（路径 A）。"""
    # 验证 session 归属
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    # 读取 chunk
    audio_bytes = await file.read()

    # 保存 chunk 文件
    chunk_file = _get_audio_dir(session_id) / f"chunk_{chunk_index:04d}.webm"
    with open(chunk_file, "wb") as f:
        f.write(audio_bytes)

    # 获取或创建 AudioService
    if session_id not in _active_sessions:
        engine = create_stt_engine("cpu")  # 路径 A 统一用 CPU
        _active_sessions[session_id] = AudioService(engine=engine)

    audio_service = _active_sessions[session_id]

    # 更新状态
    if session.status != "recording":
        session.status = "recording"
        await db.commit()

    try:
        # 转录 chunk
        result = await audio_service.add_chunk(audio_bytes, chunk_index)

        # 保存转录到 DB
        transcript_result = await db.execute(
            select(Transcript).where(Transcript.session_id == session_id)
        )
        transcript = transcript_result.scalar_one_or_none()

        if transcript:
            transcript.full_text = audio_service.collected_text
            transcript.raw_segments = audio_service.collected_segments
        else:
            transcript = Transcript(
                session_id=session_id,
                full_text=audio_service.collected_text,
                raw_segments=audio_service.collected_segments,
            )
            db.add(transcript)

        await db.commit()

        return APIResponse(
            data={
                "chunk_index": chunk_index,
                "text": result.text,
                "processing_time": result.processing_time_seconds,
            }
        )
    except Exception as e:
        logger.error(f"Chunk processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"转录失败: {e}")


@router.get("/sessions/{session_id}/transcript")
async def stream_transcript(
    session_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SSE 实时推送转录文本（路径 A 使用）。"""
    # 验证
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    # 获取活跃的 AudioService，若不存在则创建临时实例
    audio_service = _active_sessions.get(session_id)

    if not audio_service:
        raise HTTPException(status_code=400, detail="该课堂没有活跃的录制会话")

    async def event_generator():
        async for event in TranscriptSSE.event_stream(audio_service, check_interval=1.0):
            if await request.is_disconnected():
                break
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════
# 路径 B/C/D: 文件上传
# ═══════════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/upload", response_model=APIResponse)
async def upload_audio_file(
    session_id: int,
    engine_type: str = Form(default="auto"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传完整音频文件（路径 B/C/D）。"""
    # 验证 session 归属
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    # 保存文件
    audio_dir = _get_audio_dir(session_id)
    ext = Path(file.filename or "audio.mp3").suffix or ".mp3"
    audio_path = audio_dir / f"audio{ext}"
    with open(audio_path, "wb") as f:
        content = await file.read()
        f.write(content)

    session.audio_file_path = str(audio_path)
    session.source = "upload"
    session.status = "transcribing"
    await db.commit()

    # 创建引擎
    try:
        engine = create_stt_engine(None if engine_type == "auto" else engine_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session.stt_engine = engine.engine_name
    await db.commit()

    # 原始文件直接送给 whisper.cpp（内部通过 FFmpeg 解码，无需预转换）
    # 预检测音频时长（用于进度估算；非 WAV 可能失败，降级为不确定进度）
    audio_duration = _detect_audio_duration(audio_path)

    # 初始化进度追踪
    tracker.start(session_id, audio_duration)

    # 异步转录（线程池中运行，避免阻塞事件循环）
    def transcribe_and_save_sync():
        """在独立线程中运行转录+保存（因为 Whisper.cpp 是同步 CPU 操作）。"""
        import asyncio as _asyncio
        import traceback as _traceback

        async def _save():
            async with AsyncSessionLocal() as bg_db:
                try:
                    audio_service = AudioService(engine=engine)
                    # 传入进度回调（tracker 是线程安全的单例 dict 操作）
                    result = await audio_service.transcribe_file(
                        audio_path,
                        progress_callback=lambda pct, seg_time: tracker.update(
                            session_id, pct, seg_time
                        ),
                    )

                    # 转录完成 — 立即标记，让前端看到进度 100% + completed
                    tracker.complete(session_id)

                    # 保存转录到数据库
                    transcript_result = await bg_db.execute(
                        select(Transcript).where(Transcript.session_id == session_id)
                    )
                    transcript = transcript_result.scalar_one_or_none()

                    if transcript:
                        transcript.full_text = result.text
                        transcript.raw_segments = result.segments
                        transcript.processing_time_seconds = result.processing_time_seconds
                        transcript.audio_duration_seconds = result.audio_duration_seconds
                    else:
                        transcript = Transcript(
                            session_id=session_id,
                            full_text=result.text,
                            raw_segments=result.segments,
                            processing_time_seconds=result.processing_time_seconds,
                            audio_duration_seconds=result.audio_duration_seconds,
                        )
                        bg_db.add(transcript)

                    # 更新 session 状态
                    result_session = await bg_db.execute(
                        select(Session).where(Session.id == session_id)
                    )
                    bg_session = result_session.scalar_one()
                    bg_session.status = "transcribed"
                    bg_session.duration_seconds = int(result.audio_duration_seconds)
                    await bg_db.commit()

                    logger.info(f"Session {session_id} transcription complete")
                except Exception as e:
                    logger.error(
                        f"Session {session_id} transcription failed: {e}\n"
                        f"{_traceback.format_exc()}"
                    )
                    # 确保 tracker.fail 一定成功 — 捕获 KeyError
                    try:
                        tracker.fail(session_id, str(e))
                    except KeyError:
                        logger.warning(
                            f"Session {session_id} not in tracker during fail — "
                            f"manually setting status"
                        )
                    try:
                        result_session = await bg_db.execute(
                            select(Session).where(Session.id == session_id)
                        )
                        fail_session = result_session.scalar_one()
                        fail_session.status = "failed"
                        fail_session.error_message = str(e)
                        await bg_db.commit()
                    except Exception as db_err:
                        logger.error(f"Failed to update session status: {db_err}")

        # 在新的事件循环中运行（线程安全）
        loop = _asyncio.new_event_loop()
        try:
            loop.run_until_complete(_save())
        except Exception as loop_err:
            # 兜底：事件循环级别异常（如 tracker.fail 的 KeyError 穿透 _save）
            logger.error(
                f"Session {session_id} event loop crashed: {loop_err}\n"
                f"{_traceback.format_exc()}"
            )
            try:
                tracker.fail(session_id, str(loop_err))
            except KeyError:
                pass
        finally:
            loop.close()

    import threading
    threading.Thread(target=transcribe_and_save_sync, daemon=True).start()

    return APIResponse(
        message="音频已上传，转录处理中",
        data={
            "session_id": session_id,
            "engine": engine.engine_name,
            "engine_label": engine.engine_label,
            "status": "transcribing",
        },
    )


# ═══════════════════════════════════════════════════════════
# 转录进度查询
# ═══════════════════════════════════════════════════════════

@router.get("/sessions/{session_id}/transcription-progress", response_model=APIResponse)
async def get_transcription_progress(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询转录进度（实时轮询）。

    返回状态包括：
    - pending / transcribing / finalizing / completed / failed
    - finalizing: 所有分段已产出，whisper 正在做 VAD 尾清等最终化
    """
    # 验证 session 归属
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    progress = tracker.get(session_id)
    if progress is None:
        # 未在 tracker 中 → 判断是否为僵尸状态
        # 如果 DB 显示 transcribing 但 tracker 中无记录，说明转录线程已死
        if session.status == "transcribing":
            stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=30)
            if session.updated_at and session.updated_at.replace(tzinfo=timezone.utc) < stale_threshold:
                # 僵尸状态 — 标记为失败
                session.status = "failed"
                session.error_message = "转录进程意外中断（超过 30 分钟无更新），请重试"
                await db.commit()
                return APIResponse(data={
                    "status": "failed",
                    "progress_pct": 0.0,
                    "start_time": None,
                    "end_time": None,
                    "elapsed_seconds": None,
                    "estimated_remaining_seconds": None,
                    "audio_duration_seconds": None,
                    "latest_segment_time": 0.0,
                    "seconds_since_last_update": 0.0,
                    "error_message": session.error_message,
                })

        # 正常情况：从 session 状态推断
        return APIResponse(data={
            "status": session.status,
            "progress_pct": 100.0 if session.status == "transcribed" else 0.0,
            "start_time": None,
            "end_time": None,
            "elapsed_seconds": None,
            "estimated_remaining_seconds": None,
            "audio_duration_seconds": None,
            "latest_segment_time": 0.0,
            "seconds_since_last_update": 0.0,
            "error_message": session.error_message,
        })

    return APIResponse(data={
        "status": progress.status,
        "progress_pct": progress.progress_pct,
        "start_time": progress.start_time,
        "end_time": progress.end_time,
        "elapsed_seconds": progress.elapsed_seconds,
        "estimated_remaining_seconds": progress.estimated_remaining_seconds,
        "audio_duration_seconds": progress.audio_duration_seconds,
        "latest_segment_time": progress.latest_segment_time,
        "seconds_since_last_update": progress.seconds_since_last_update,
        "error_message": progress.error_message,
    })


# ═══════════════════════════════════════════════════════════
# 分析进度查询
# ═══════════════════════════════════════════════════════════

@router.get("/sessions/{session_id}/analysis-progress", response_model=APIResponse)
async def get_analysis_progress(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询 AI 分析进度（实时轮询）。"""
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    progress = _analysis_progress.get(session_id)
    if progress is None:
        # 未在 tracker 中，从 session 状态推断
        pct = 100.0 if session.status == "completed" else 0.0
        return APIResponse(data={
            "progress_pct": pct,
            "stage": "分析完成" if session.status == "completed" else "等待分析",
            "status": session.status,
            "start_time": None,
            "estimated_seconds": None,
        })

    return APIResponse(data={
        "progress_pct": progress.get("progress_pct", 0),
        "stage": progress.get("stage", ""),
        "status": progress.get("status", "analyzing"),
        "start_time": progress.get("start_time"),
        "estimated_seconds": progress.get("estimated_seconds"),
    })


# ═══════════════════════════════════════════════════════════
# 知识点大纲
# ═══════════════════════════════════════════════════════════

@router.put("/sessions/{session_id}/outline", response_model=APIResponse)
async def update_outline(
    session_id: int,
    data: SessionUpdateOutline,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """录入/更新知识点大纲。"""
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    session.knowledge_outline = data.knowledge_outline
    await db.commit()

    return APIResponse(
        message="知识点大纲已更新",
        data={"session_id": session_id},
    )


# ═══════════════════════════════════════════════════════════
# 触发分析
# ═══════════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/analyze", response_model=APIResponse)
async def trigger_analysis(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """触发 LLM 课堂分析。"""
    import time

    # 验证
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    if not session.knowledge_outline:
        raise HTTPException(
            status_code=400,
            detail="请先录入知识点大纲",
        )

    # 获取转录
    transcript_result = await db.execute(
        select(Transcript).where(Transcript.session_id == session_id)
    )
    transcript = transcript_result.scalar_one_or_none()
    if not transcript or not transcript.full_text:
        raise HTTPException(
            status_code=400,
            detail="转录文本为空，请先完成音频转录",
        )

    # 更新状态
    session.status = "analyzing"
    await db.commit()

    # 估算分析耗时：基于转录长度（每 500 字约 8 秒，最少 15 秒，最多 90 秒）
    transcript_len = len(transcript.full_text) if transcript.full_text else 0
    estimated_seconds = max(15, min(90, transcript_len / 500 * 8))

    # 初始化分析进度
    _analysis_progress[session_id] = {
        "progress_pct": 0.0,
        "stage": "准备分析...",
        "status": "analyzing",
        "start_time": _time.time(),
        "estimated_seconds": estimated_seconds,
    }

    # 异步分析（独立 DB session）
    async def analyze_and_save():
        # 启动进度模拟器（在后台持续更新进度）
        async def _simulate_progress():
            """基于预估时间平滑推进进度（0% → 95%），完成时由主任务设为 100%"""
            start = _time.time()
            while session_id in _analysis_progress:
                elapsed = _time.time() - start
                # 平滑曲线：前期快后期慢，最多到 95%
                raw_pct = min(elapsed / estimated_seconds * 100, 95.0)
                # 加一点随机微调，避免太机械
                import random
                pct = round(raw_pct + random.uniform(-2, 2), 1)
                pct = max(0, min(95.0, pct))

                # 确定当前阶段
                stage = "正在分析..."
                for lo, hi, label in _ANALYSIS_STAGES:
                    if pct >= lo and pct < hi:
                        stage = label
                        break

                if session_id in _analysis_progress:
                    _analysis_progress[session_id]["progress_pct"] = pct
                    _analysis_progress[session_id]["stage"] = stage

                await asyncio.sleep(1.5)

        progress_task = asyncio.create_task(_simulate_progress())

        try:
            async with AsyncSessionLocal() as bg_db:
                try:
                    ai_service = await _create_ai_service(bg_db, session.teacher_id)

                    start = _time.time()
                    result = await ai_service.analyze_classroom(
                        transcript=transcript.full_text,
                        knowledge_outline=session.knowledge_outline,
                    )
                    elapsed = _time.time() - start

                    # 保存分析报告
                    analysis_result = await bg_db.execute(
                        select(AnalysisReport).where(
                            AnalysisReport.session_id == session_id
                        )
                    )
                    analysis = analysis_result.scalar_one_or_none()

                    report_data = {
                        "session_id": session_id,
                        "cleaned_transcript": result.get("cleaned_transcript"),
                        "knowledge_points": result.get("knowledge_points", []),
                        "student_mastery": result.get("student_mastery", []),
                        "classroom_performance": result.get("classroom_performance"),
                        "reinforcement_plan": result.get("reinforcement_plan", []),
                        "raw_llm_response": result.get("_raw_llm_response"),
                        "processing_time_seconds": elapsed,
                    }

                    if analysis:
                        for k, v in report_data.items():
                            setattr(analysis, k, v)
                    else:
                        analysis = AnalysisReport(**report_data)
                        bg_db.add(analysis)

                    # 更新状态
                    result_session = await bg_db.execute(
                        select(Session).where(Session.id == session_id)
                    )
                    s = result_session.scalar_one()
                    s.status = "completed"
                    await bg_db.commit()

                    # 分析完成 → 进度 100%
                    if session_id in _analysis_progress:
                        _analysis_progress[session_id]["progress_pct"] = 100.0
                        _analysis_progress[session_id]["stage"] = "分析完成"
                        _analysis_progress[session_id]["status"] = "completed"

                    logger.info(
                        f"Session {session_id} analysis complete in {elapsed:.1f}s"
                    )
                except Exception as e:
                    # 如果是 tenacity RetryError，提取原始异常信息
                    raw_error = _unwrap_retry_error(e)
                    logger.error(f"Session {session_id} analysis failed: {raw_error}")
                    if session_id in _analysis_progress:
                        _analysis_progress[session_id]["status"] = "failed"
                        _analysis_progress[session_id]["stage"] = f"分析失败: {raw_error}"
                    try:
                        result_session = await bg_db.execute(
                            select(Session).where(Session.id == session_id)
                        )
                        s = result_session.scalar_one()
                        s.status = "failed"
                        s.error_message = raw_error
                        await bg_db.commit()
                    except Exception as db_err:
                        logger.error(f"Failed to update session status: {db_err}")

        finally:
            # 清理进度模拟任务
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass

    asyncio.create_task(analyze_and_save())

    return APIResponse(
        message="分析已触发，处理中",
        data={"session_id": session_id, "status": "analyzing"},
    )


# ═══════════════════════════════════════════════════════════
# 家长反馈报告模板管理
# ═══════════════════════════════════════════════════════════

@router.post("/templates", response_model=APIResponse)
async def create_template(
    request: ReportTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传自定义家长报告模板。

    模板为纯文本文件，支持变量占位符：
    {subject}, {date}, {time}, {student_name},
    {total_knowledge_points}, {covered_count}, {mastered_count},
    {engagement_level}
    """
    from app.models.template import ReportTemplate

    # 检查同名模板
    existing = await db.execute(
        select(ReportTemplate).where(
            ReportTemplate.user_id == current_user.id,
            ReportTemplate.name == request.name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"模板「{request.name}」已存在")

    # 如果设为默认，先取消其他默认
    if request.set_as_default:
        defaults = (await db.execute(
            select(ReportTemplate).where(
                ReportTemplate.user_id == current_user.id,
                ReportTemplate.is_default == True,  # noqa: E712
            )
        )).scalars().all()
        for t in defaults:
            t.is_default = False

    template = ReportTemplate(
        user_id=current_user.id,
        name=request.name,
        content=request.content,
        is_default=request.set_as_default,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return APIResponse(
        message="模板已上传",
        data=ReportTemplateResponse.model_validate(template).model_dump(),
    )


@router.get("/templates", response_model=APIResponse)
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出当前用户的所有模板（默认模板排在最前面）。"""
    from app.models.template import ReportTemplate

    result = await db.execute(
        select(ReportTemplate)
        .where(ReportTemplate.user_id == current_user.id)
        .order_by(ReportTemplate.is_default.desc(), ReportTemplate.created_at.desc())
    )
    templates = result.scalars().all()

    # 系统默认模板（虚拟条目，始终在列表首位）
    import os
    default_prompt_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "prompts", "parent_report.txt"
    )
    try:
        with open(default_prompt_path, "r", encoding="utf-8") as f:
            default_content = f.read()
    except FileNotFoundError:
        default_content = ""

    data = {
        "templates": [ReportTemplateResponse.model_validate(t).model_dump() for t in templates],
        "system_default": {
            "id": 0,
            "name": "学达默认模板",
            "content_preview": default_content[:200] + ("..." if len(default_content) > 200 else ""),
            "is_default": not any(t.is_default for t in templates),
        },
        "total": len(templates),
    }

    return APIResponse(data=data)


@router.get("/templates/{template_id}", response_model=APIResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个模板的完整内容。"""
    from app.models.template import ReportTemplate

    result = await db.execute(
        select(ReportTemplate).where(
            ReportTemplate.id == template_id,
            ReportTemplate.user_id == current_user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    return APIResponse(data=ReportTemplateResponse.model_validate(template).model_dump())


@router.put("/templates/{template_id}", response_model=APIResponse)
async def update_template(
    template_id: int,
    request: ReportTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新模板（目前仅支持「设为默认」）。"""
    from app.models.template import ReportTemplate

    result = await db.execute(
        select(ReportTemplate).where(
            ReportTemplate.id == template_id,
            ReportTemplate.user_id == current_user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    if request.is_default:
        # 取消其他默认
        all_defaults = (await db.execute(
            select(ReportTemplate).where(
                ReportTemplate.user_id == current_user.id,
                ReportTemplate.is_default == True,  # noqa: E712
            )
        )).scalars().all()
        for t in all_defaults:
            t.is_default = False
        template.is_default = True
        await db.commit()

    return APIResponse(
        message=f"模板「{template.name}」已设为默认",
        data=ReportTemplateResponse.model_validate(template).model_dump(),
    )


@router.delete("/templates/{template_id}", response_model=APIResponse)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除自定义模板。"""
    from app.models.template import ReportTemplate

    result = await db.execute(
        select(ReportTemplate).where(
            ReportTemplate.id == template_id,
            ReportTemplate.user_id == current_user.id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    name = template.name
    was_default = template.is_default
    await db.delete(template)
    await db.commit()

    return APIResponse(
        message=f"模板「{name}」已删除",
        data={"was_default": was_default},
    )


# ═══════════════════════════════════════════════════════════
# 家长反馈报告
# ═══════════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/parent-report", response_model=APIResponse)
async def generate_parent_report(
    session_id: int,
    subject: str = Form(default=""),
    class_date: str = Form(default=""),
    class_time: str = Form(default=""),
    teacher_feedback: str = Form(default=""),
    regenerate: bool = Query(False, description="强制重新生成，忽略缓存"),
    template_id: int = Query(0, description="模板ID，0 表示使用系统默认模板"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成家长反馈报告（基于已完成的分析）。

    首次生成后缓存到数据库，后续直接返回缓存。
    传 regenerate=true 可强制重新生成。
    传 template_id 可指定自定义模板，0 为系统默认模板。
    """
    from app.services.ai_service import AIService, AIServiceError
    from app.models.template import ReportTemplate

    # 验证 session
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    # 自动填充：表单未填时从 Session 获取
    if not class_time and session.class_start_time and session.class_end_time:
        class_time = f"{session.class_start_time}-{session.class_end_time}"

    # 获取分析报告
    analysis_result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.session_id == session_id)
    )
    analysis = analysis_result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(
            status_code=400,
            detail="该课堂尚未完成分析，请先触发 AI 分析",
        )

    # 有缓存且不强制重新生成 → 直接返回
    if analysis.parent_report and not regenerate:
        return APIResponse(
            message="家长报告（缓存）",
            data={
                "session_id": session_id,
                "report": analysis.parent_report,
            },
        )

    # 构建分析结果字典
    analysis_data = {
        "knowledge_points": analysis.knowledge_points or [],
        "classroom_performance": analysis.classroom_performance,
        "reinforcement_plan": analysis.reinforcement_plan or [],
    }

    # 加载自定义模板（如指定）
    custom_template: str | None = None
    if template_id > 0:
        tmpl_result = await db.execute(
            select(ReportTemplate).where(
                ReportTemplate.id == template_id,
                ReportTemplate.user_id == current_user.id,
            )
        )
        tmpl = tmpl_result.scalar_one_or_none()
        if tmpl:
            custom_template = tmpl.content
        else:
            raise HTTPException(status_code=404, detail="指定模板不存在")
    elif template_id == 0:
        # 检查用户是否有默认模板
        default_result = await db.execute(
            select(ReportTemplate).where(
                ReportTemplate.user_id == current_user.id,
                ReportTemplate.is_default == True,  # noqa: E712
            )
        )
        default_tmpl = default_result.scalar_one_or_none()
        if default_tmpl:
            custom_template = default_tmpl.content

    # 存储教师定性反馈
    if teacher_feedback.strip():
        analysis.teacher_feedback = teacher_feedback

    try:
        ai_service = await _create_ai_service(db, current_user.id)
        report = await ai_service.generate_parent_report(
            analysis_result=analysis_data,
            subject=subject,
            class_date=class_date,
            class_time=class_time,
            student_name=session.student_name or "",
            teacher_feedback=teacher_feedback,
            custom_template=custom_template,
        )
        # 缓存到数据库
        analysis.parent_report = report
        await db.commit()

        return APIResponse(
            message="家长报告已生成",
            data={
                "session_id": session_id,
                "report": report,
            },
        )
    except AIServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# 家长报告修改建议（与 LLM 交互修订）
# ═══════════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/parent-report/revise", response_model=APIResponse)
async def revise_parent_report(
    session_id: int,
    request: ParentReportReviseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据教师修改建议，让 LLM 修订已有家长反馈报告。

    需要已有家长报告；传入自然语言修改建议，LLM 基于原始分析数据
    和现有报告生成修订版本。
    """
    from app.services.ai_service import AIService, AIServiceError

    # 验证 session 归属
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    # 获取分析报告
    analysis_result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.session_id == session_id)
    )
    analysis = analysis_result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(
            status_code=400,
            detail="该课堂尚未完成分析",
        )
    if not analysis.parent_report:
        raise HTTPException(
            status_code=400,
            detail="该课堂尚未生成家长报告，请先生成",
        )

    # 构建分析结果字典
    analysis_data = {
        "knowledge_points": analysis.knowledge_points or [],
        "classroom_performance": analysis.classroom_performance,
        "reinforcement_plan": analysis.reinforcement_plan or [],
    }

    # 获取 session 的上下文信息
    subject = session.subject or ""
    class_time = ""
    if session.class_start_time and session.class_end_time:
        class_time = f"{session.class_start_time}-{session.class_end_time}"

    try:
        ai_service = await _create_ai_service(db, current_user.id)
        revised_report = await ai_service.revise_parent_report(
            existing_report=analysis.parent_report,
            revision_instruction=request.revision_instruction,
            analysis_result=analysis_data,
            subject=subject,
            class_time=class_time,
        )
        # 更新缓存
        analysis.parent_report = revised_report
        await db.commit()

        return APIResponse(
            message="报告已修订",
            data={
                "session_id": session_id,
                "report": revised_report,
            },
        )
    except AIServiceError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# 报告图片生成
# ═══════════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/report-image")
async def create_report_image(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成课堂分析报告图片（PNG）。

    将知识点覆盖、课堂互动、巩固建议（含颜色图例）和家长报告
    渲染为一张 PNG 图片，可直接下载分享给家长。
    """
    # 验证 session 归属
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    # 获取分析报告
    analysis_result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.session_id == session_id)
    )
    analysis = analysis_result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(
            status_code=400,
            detail="该课堂尚未完成分析，请先触发 AI 分析",
        )

    # 构建知识点数据
    knowledge_points = analysis.knowledge_points or []

    # 构建课堂互动数据
    classroom_performance = analysis.classroom_performance

    # 构建巩固建议
    reinforcement_plan = analysis.reinforcement_plan or []

    # 获取家长报告（优先用缓存）
    parent_report_text = analysis.parent_report or ""
    if not parent_report_text:
        try:
            ai_service = await _create_ai_service(db, current_user.id)
            analysis_data = {
                "knowledge_points": knowledge_points,
                "classroom_performance": classroom_performance,
                "reinforcement_plan": reinforcement_plan,
            }
            # 格式化日期时间
            class_date = ""
            class_time = ""
            if session.class_start_time:
                try:
                    class_date = session.class_start_time.strftime("%Y年%m月%d日")
                except Exception:
                    pass
                if session.class_end_time:
                    class_time = f"{session.class_start_time}-{session.class_end_time}"
                else:
                    class_time = str(session.class_start_time)
            # 获取自定义模板
            custom_template = None
            from app.models.template import ReportTemplate
            default_result = await db.execute(
                select(ReportTemplate).where(
                    ReportTemplate.user_id == current_user.id,
                    ReportTemplate.is_default == True,  # noqa: E712
                )
            )
            default_tmpl = default_result.scalar_one_or_none()
            if default_tmpl:
                custom_template = default_tmpl.content
            parent_report_text = await ai_service.generate_parent_report(
                analysis_result=analysis_data,
                subject=session.subject or "",
                class_date=class_date,
                class_time=class_time,
                student_name=session.student_name or "",
                teacher_feedback=analysis.teacher_feedback or "",
                custom_template=custom_template,
            )
            # 缓存
            analysis.parent_report = parent_report_text
            await db.commit()
        except Exception as e:
            logger.warning(f"Parent report generation failed for image: {e}")
            parent_report_text = "（家长报告生成失败）"

    # 格式化日期
    class_date = ""
    if session.class_start_time:
        try:
            class_date = session.class_start_time.strftime("%Y年%m月%d日")
        except Exception:
            pass

    # 生成图片
    try:
        from app.services.report_image import generate_report_image

        image_bytes = generate_report_image(
            session_title=session.title or "",
            student_name=session.student_name or "",
            class_date=class_date,
            knowledge_points=knowledge_points,
            classroom_performance=classroom_performance,
            reinforcement_plan=reinforcement_plan,
            parent_report=parent_report_text,
        )
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"图片生成失败: {e}")

    # 生成安全的文件名（RFC 5987 编码以支持中文）
    safe_title = (session.title or "report").replace(" ", "_")[:30]
    filename = f"{safe_title}_分析报告.png"
    # ASCII fallback 文件名（去除非 ASCII 字符）
    ascii_filename = safe_title.encode("ascii", errors="ignore").decode("ascii") or "report"
    ascii_filename = f"{ascii_filename}_report.png"
    # RFC 5987 编码的 UTF-8 文件名
    encoded_filename = _url_quote(filename, safe="")

    return StreamingResponse(
        io.BytesIO(image_bytes),
        media_type="image/png",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_filename}\"; "
                f"filename*=UTF-8''{encoded_filename}"
            ),
            "Content-Length": str(len(image_bytes)),
        },
    )


# ═══════════════════════════════════════════════════════════
# 导入已有转录
# ═══════════════════════════════════════════════════════════

class ImportTranscriptBody(BaseModel):
    full_text: str
    source_session_id: int | None = None


@router.put("/sessions/{session_id}/transcript", response_model=APIResponse)
async def import_transcript(
    session_id: int,
    body: ImportTranscriptBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导入已有转录文本到当前课堂（复用已转录文档）。"""
    # 验证 session
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    # 获取或创建 transcript
    transcript_result = await db.execute(
        select(Transcript).where(Transcript.session_id == session_id)
    )
    transcript = transcript_result.scalar_one_or_none()

    if transcript:
        transcript.full_text = body.full_text
    else:
        transcript = Transcript(session_id=session_id, full_text=body.full_text)
        db.add(transcript)

    session.status = "transcribed"
    await db.commit()

    return APIResponse(
        message="转录文本已导入",
        data={"session_id": session_id, "status": "transcribed"},
    )


# ═══════════════════════════════════════════════════════════
# 结束录制
# ═══════════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/finish", response_model=APIResponse)
async def finish_recording(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """结束实时录制，合并所有 chunk 并更新状态。"""
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    # 清理活跃会话
    audio_service = _active_sessions.pop(session_id, None)
    if audio_service:
        audio_service.reset()

    session.status = "transcribed"
    await db.commit()

    return APIResponse(
        message="录制已结束",
        data={"session_id": session_id, "status": "transcribed"},
    )


# ═══════════════════════════════════════════════════════════
# 清空上传缓存
# ═══════════════════════════════════════════════════════════

@router.post("/maintenance/clear-uploads", response_model=APIResponse)
async def clear_uploads(current_user: User = Depends(get_current_user)):
    """清空 uploads/ 目录中的所有音频文件（不可逆）。"""
    import shutil, os

    project_dir = Path(os.path.abspath(".")).resolve()
    abs_upload = UPLOAD_DIR.resolve()
    if not str(abs_upload).startswith(str(project_dir)):
        raise HTTPException(status_code=500, detail="上传目录路径异常")

    files = []
    total_size = 0
    if UPLOAD_DIR.exists():
        for f in UPLOAD_DIR.rglob("*"):
            if f.is_file() and str(f.resolve()).startswith(str(project_dir)):
                total_size += f.stat().st_size
                files.append(str(f.relative_to(UPLOAD_DIR)))

    if not files:
        return APIResponse(code=200, message="上传目录已为空，无需清理",
            data={"file_count": 0, "total_size_mb": 0, "deleted_dirs": 0, "errors": []})

    size_mb = round(total_size / 1024 / 1024, 2)
    deleted_count, errors = 0, []
    for item in list(UPLOAD_DIR.iterdir()):
        try:
            if not str(item.resolve()).startswith(str(project_dir)):
                continue
            shutil.rmtree(item) if item.is_dir() else item.unlink()
            deleted_count += 1
        except Exception as e:
            errors.append(str(e))

    msg = f"已清理 {len(files)} 个音频文件，释放 {size_mb} MB 磁盘空间"
    if errors:
        msg += f"（{len(errors)} 个删除失败）"

    return APIResponse(code=200, message=msg,
        data={"file_count": len(files), "total_size_mb": size_mb, "deleted_dirs": deleted_count, "errors": errors})


# ═══════════════════════════════════════════════════════════
# 删除课堂记录
# ═══════════════════════════════════════════════════════════

@router.delete("/sessions/{session_id}", response_model=APIResponse)
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除指定课堂及其关联的转录、分析报告和音频文件（不可逆）。"""
    import shutil

    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.teacher_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="课堂记录不存在")

    # 记录信息用于响应
    title = session.title
    audio_path = session.audio_file_path

    # 级联删除数据库记录（Session.transcripts 和 Session.analysis 均配置了 cascade="all, delete-orphan"，确保一并删除）
    await db.delete(session)
    await db.commit()

    # 清理内存中的转录进度跟踪（如有）
    from app.services.transcription_tracker import get_tracker
    get_tracker().remove(session_id)

    # 删除关联的音频文件（磁盘清理）
    deleted_files = 0
    errors: list[str] = []
    # 1. 删除 session 目录下的上传文件
    session_upload_dir = UPLOAD_DIR / str(session_id)
    if session_upload_dir.exists():
        try:
            shutil.rmtree(session_upload_dir)
            deleted_files += 1
        except Exception as e:
            errors.append(f"删除上传目录失败: {e}")
    # 2. 删除 audio_file_path 指向的文件
    if audio_path:
        try:
            audio_file = Path(audio_path)
            if audio_file.exists():
                audio_file.unlink()
                deleted_files += 1
        except Exception as e:
            errors.append(f"删除音频文件失败: {e}")

    return APIResponse(
        code=200,
        message=f"已删除课堂「{title}」及其关联数据",
        data={
            "session_id": session_id,
            "deleted_files": deleted_files,
            "errors": errors if errors else None,
        },
    )


@router.delete("/sessions", response_model=APIResponse)
async def clear_all_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除当前用户的所有课堂记录及关联音频文件（不可逆）。"""
    import shutil

    result = await db.execute(
        select(Session).where(Session.teacher_id == current_user.id)
    )
    sessions = result.scalars().all()

    if not sessions:
        return APIResponse(code=200, message="没有需要删除的课堂记录",
            data={"deleted_count": 0})

    count = len(sessions)
    total_deleted_files = 0
    errors: list[str] = []

    for session in sessions:
        audio_path = session.audio_file_path
        sid = session.id

        # 删除上传目录
        session_dir = UPLOAD_DIR / str(sid)
        if session_dir.exists():
            try:
                shutil.rmtree(session_dir)
                total_deleted_files += 1
            except Exception as e:
                errors.append(f"Session {sid} 上传目录删除失败: {e}")

        # 删除音频文件
        if audio_path:
            try:
                af = Path(audio_path)
                if af.exists():
                    af.unlink()
                    total_deleted_files += 1
            except Exception as e:
                errors.append(f"Session {sid} 音频文件删除失败: {e}")

        # 级联删除数据库记录
        await db.delete(session)

    await db.commit()

    return APIResponse(
        code=200,
        message=f"已删除 {count} 个课堂记录",
        data={
            "deleted_count": count,
            "deleted_files": total_deleted_files,
            "errors": errors if errors else None,
        },
    )
