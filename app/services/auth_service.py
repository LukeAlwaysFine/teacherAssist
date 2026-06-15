"""
Auth 服务 — 注册、登录、Token 刷新。
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.user import User
from app.schemas.auth import UserRegister, UserLogin, TokenResponse, UserProfile

logger = logging.getLogger(__name__)


class AuthServiceError(Exception):
    """认证服务异常。"""
    pass


class AuthService:
    """认证服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(self, data: UserRegister) -> TokenResponse:
        """注册新用户。

        Args:
            data: 注册信息。

        Returns:
            TokenResponse: 包含 access + refresh token。

        Raises:
            AuthServiceError: 邮箱已注册时抛出。
        """
        # 检查邮箱是否已存在
        result = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise AuthServiceError("该邮箱已被注册")

        # 创建用户
        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role=data.role,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"User registered: {user.email} (id={user.id})")

        # 生成 token
        return TokenResponse(
            access_token=create_access_token(str(user.id)),
            refresh_token=create_refresh_token(str(user.id)),
        )

    async def login(self, data: UserLogin) -> TokenResponse:
        """用户登录。

        Args:
            data: 登录凭据。

        Returns:
            TokenResponse: 包含 access + refresh token。

        Raises:
            AuthServiceError: 邮箱或密码错误时抛出。
        """
        result = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.hashed_password):
            raise AuthServiceError("邮箱或密码错误")

        logger.info(f"User logged in: {user.email} (id={user.id})")

        return TokenResponse(
            access_token=create_access_token(str(user.id)),
            refresh_token=create_refresh_token(str(user.id)),
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """使用 refresh token 刷新 access token。

        Args:
            refresh_token: 有效的 refresh token。

        Returns:
            TokenResponse: 新的 token 对。

        Raises:
            AuthServiceError: token 无效或类型错误时抛出。
        """
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise AuthServiceError("无效的 refresh token")

            user_id = payload.get("sub")
            if not user_id:
                raise AuthServiceError("无效的 token payload")

            # 验证用户仍然存在
            result = await self.db.execute(
                select(User).where(User.id == int(user_id))
            )
            user = result.scalar_one_or_none()
            if not user:
                raise AuthServiceError("用户不存在")

            logger.info(f"Token refreshed for user id={user_id}")

            return TokenResponse(
                access_token=create_access_token(str(user.id)),
                refresh_token=create_refresh_token(str(user.id)),
            )
        except AuthServiceError:
            raise
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise AuthServiceError("Token 刷新失败") from e

    async def get_profile(self, user_id: int) -> UserProfile:
        """获取用户信息。

        Args:
            user_id: 用户 ID。

        Returns:
            UserProfile: 用户信息。

        Raises:
            AuthServiceError: 用户不存在时抛出。
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise AuthServiceError("用户不存在")
        return UserProfile.model_validate(user)
