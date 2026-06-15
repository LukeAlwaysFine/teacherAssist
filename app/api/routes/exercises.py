# Exercise routes
from fastapi import APIRouter

router = APIRouter(tags=["exercises"])


@router.get("/exercises")
async def list_exercises():
    """获取习题列表。"""
    raise NotImplementedError


@router.post("/exercises")
async def create_exercise():
    """发布新习题。"""
    raise NotImplementedError


@router.post("/exercises/{exercise_id}/submit")
async def submit_answer():
    """提交习题答案。"""
    raise NotImplementedError


@router.post("/exercises/{exercise_id}/score")
async def score_answer():
    """AI 批改习题。"""
    raise NotImplementedError
