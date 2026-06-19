"""
应用配置管理。

使用 pydantic-settings 从环境变量/.env 文件加载配置。
"""
from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings


def _parse_cors(v: str | list) -> list[str]:
    """将逗号分隔字符串解析为列表。"""
    if isinstance(v, str):
        return [origin.strip() for origin in v.split(",") if origin.strip()]
    return v


class Settings(BaseSettings):
    """应用配置。"""

    # 应用
    PROJECT_NAME: str = "teacherAssist"
    VERSION: str = "0.1.0"
    DEBUG: bool = False

    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/teacher_assist.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # CORS (支持逗号分隔字符串)
    CORS_ORIGINS: Annotated[list[str], BeforeValidator(_parse_cors)] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # ─── LLM 通用（留空 = 需用户在 UI 中自行配置）───
    LLM_PROVIDER: str = ""
    LLM_DEFAULT_MAX_TOKENS: int = 4096

    # DeepSeek Provider
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_MAX_TOKENS: int = 4096
    DEEPSEEK_BASE_URL: str = ""

    # Anthropic Provider
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_MAX_TOKENS: int = 4096

    # Whisper API (OpenAI 兼容)
    OPENAI_API_KEY: str = ""
    WHISPER_MODEL: str = "whisper-1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
