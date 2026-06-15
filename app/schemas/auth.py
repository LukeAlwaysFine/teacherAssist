"""Auth 相关 Pydantic Schema。"""
from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    """用户注册请求。"""
    email: str = Field(..., min_length=5, max_length=255, description="邮箱")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    full_name: str = Field(..., min_length=1, max_length=100, description="姓名")
    role: str = Field(default="teacher", pattern="^(teacher|student)$")


class UserLogin(BaseModel):
    """用户登录请求。"""
    email: str = Field(..., description="邮箱")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    """Token 响应。"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    """用户信息响应。"""
    id: int
    email: str
    full_name: str
    role: str

    model_config = {"from_attributes": True}


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求。"""
    refresh_token: str = Field(..., description="刷新令牌")
