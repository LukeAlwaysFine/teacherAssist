"""
Auth 路由 — 注册、登录、Token 刷新。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    RefreshTokenRequest,
)
from app.schemas.session import APIResponse
from app.services.auth_service import AuthService, AuthServiceError

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=APIResponse, status_code=201)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """用户注册。"""
    service = AuthService(db)
    try:
        tokens = await service.register(data)
        return APIResponse(
            code=201,
            message="注册成功",
            data=tokens.model_dump(),
        )
    except AuthServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/login", response_model=APIResponse)
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """用户登录。"""
    service = AuthService(db)
    try:
        tokens = await service.login(data)
        return APIResponse(
            message="登录成功",
            data=tokens.model_dump(),
        )
    except AuthServiceError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/refresh", response_model=APIResponse)
async def refresh_token(
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """刷新 access token。"""
    service = AuthService(db)
    try:
        tokens = await service.refresh_token(data.refresh_token)
        return APIResponse(
            message="令牌已刷新",
            data=tokens.model_dump(),
        )
    except AuthServiceError as e:
        raise HTTPException(status_code=401, detail=str(e))
