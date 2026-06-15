"""
User 路由 — 用户资料管理。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.session import APIResponse
from app.services.auth_service import AuthService, AuthServiceError

router = APIRouter(tags=["users"])


@router.get("/users/me", response_model=APIResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户信息。"""
    service = AuthService(db)
    try:
        profile = await service.get_profile(current_user.id)
        return APIResponse(data=profile.model_dump())
    except AuthServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
