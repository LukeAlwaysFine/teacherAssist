"""
FastAPI 应用入口。

注册中间件、路由、异常处理器。
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db import engine, Base

logger = logging.getLogger(__name__)

# 确保所有模型被导入，Base.metadata 才能感知全部表
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    # 启动时：创建数据库表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")
    yield
    # 关闭时：清理资源
    await engine.dispose()


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=__import__("app").__version__,
        lifespan=lifespan,
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "Content-Length"],
    )

    # 调试中间件：记录所有非 2xx/3xx 响应的请求方法和路径
    @app.middleware("http")
    async def log_bad_requests(request: Request, call_next):
        response = await call_next(request)
        if response.status_code >= 400:
            logger.warning(
                f"[{response.status_code}] {request.method} {request.url.path} "
                f"Origin={request.headers.get('origin', 'none')} "
                f"Referer={request.headers.get('referer', 'none')}"
            )
        return response

    # 注册路由
    from app.api.routes import auth, exercises, users, sessions

    app.include_router(auth.router, prefix="/api/v1/auth")
    app.include_router(sessions.router, prefix="/api/v1")
    # feedback routes — 待实现（课后习题反馈收集 + AI 总结）
    # from app.api.routes import feedback
    # app.include_router(feedback.router, prefix="/api/v1")
    app.include_router(exercises.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")

    # 清空上传文件 — 必须在 StaticFiles mount 之前注册
    from app.api.routes.maintenance import router as maintenance_router
    app.include_router(maintenance_router, prefix="/api/v1/maintenance")
    app.include_router(maintenance_router, prefix="/api/v/maintenance")

    # 静态文件（前端）
    from fastapi.staticfiles import StaticFiles
    import os
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    # 全局异常处理器
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception on {request.method} {request.url.path}")
        detail = str(exc) if settings.DEBUG else None
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "服务器内部错误",
                "data": None,
                "detail": detail,
            },
        )

    return app


app = create_app()
 
