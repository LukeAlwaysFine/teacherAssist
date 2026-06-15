# Feedback routes
from fastapi import APIRouter

router = APIRouter(tags=["feedback"])


@router.get("/feedbacks")
async def list_feedbacks():
    """获取课堂反馈列表。"""
    raise NotImplementedError


@router.post("/feedbacks")
async def create_feedback():
    """提交课堂反馈。"""
    raise NotImplementedError


@router.post("/feedbacks/summarize")
async def summarize_feedback():
    """AI 总结课堂反馈。"""
    raise NotImplementedError
