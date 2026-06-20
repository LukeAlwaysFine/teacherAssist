"""
UserLLMConfig — 用户自定义 LLM 配置。

每个用户最多一条配置记录；配置了则覆盖系统默认的 LLM Provider 设置。
"""
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.user import User


class UserLLMConfig(Base):
    __tablename__ = "user_llm_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)

    provider: Mapped[str] = mapped_column(String(20), default="deepseek")
    api_key: Mapped[str] = mapped_column(String(512), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    base_url: Mapped[str] = mapped_column(String(255), default="")
    reasoning_effort: Mapped[str] = mapped_column(String(20), default="high")

    # 关联
    user: Mapped["User"] = relationship(back_populates="llm_config")

    def is_configured(self) -> bool:
        """用户是否已填写 API Key（必须项）。"""
        return bool(self.api_key.strip())

    def __repr__(self) -> str:
        return f"<UserLLMConfig(user_id={self.user_id}, provider='{self.provider}')>"
