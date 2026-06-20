"""
User 路由 — 用户资料管理 + LLM 配置。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.user_llm_config import UserLLMConfig
from app.schemas.session import (
    APIResponse,
    UserLLMConfigUpdate,
    UserLLMConfigResponse,
)
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


# ═══════════════════════════════════════════════════════════
# 用户 LLM 配置
# ═══════════════════════════════════════════════════════════

@router.get("/users/me/llm-config", response_model=APIResponse)
async def get_llm_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的 LLM 配置（未配置时返回空模板）。"""
    result = await db.execute(
        select(UserLLMConfig).where(UserLLMConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()

    if config:
        return APIResponse(data=UserLLMConfigResponse.model_validate(config).model_dump())
    else:
        # 返回空模板
        return APIResponse(data={
            "id": 0,
            "provider": "deepseek",
            "api_key": "",
            "model": "",
            "max_tokens": 4096,
            "base_url": "",
            "reasoning_effort": "high",
        })


@router.put("/users/me/llm-config", response_model=APIResponse)
async def update_llm_config(
    request: UserLLMConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建或更新当前用户的 LLM 配置。"""
    result = await db.execute(
        select(UserLLMConfig).where(UserLLMConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()

    if config:
        config.provider = request.provider
        config.api_key = request.api_key
        config.model = request.model
        config.max_tokens = request.max_tokens
        config.base_url = request.base_url
        config.reasoning_effort = request.reasoning_effort
    else:
        config = UserLLMConfig(
            user_id=current_user.id,
            provider=request.provider,
            api_key=request.api_key,
            model=request.model,
            max_tokens=request.max_tokens,
            base_url=request.base_url,
            reasoning_effort=request.reasoning_effort,
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    return APIResponse(
        message="LLM 配置已保存",
        data=UserLLMConfigResponse.model_validate(config).model_dump(),
    )
