@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0.."

title 教师助手 — 安装程序

echo.
echo   ╔══════════════════════════════════════╗
echo   ║   教师助手 — Docker 一键安装          ║
echo   ╚══════════════════════════════════════╝
echo.

:: ── 1. 检查 Docker ──
echo   [1/4] 检测 Docker 环境...
docker --version >nul 2>&1
if errorlevel 1 (
    echo   [✗] 未找到 Docker Desktop，请先安装：
    echo       https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo   [✗] Docker Desktop 未运行，请先启动 Docker Desktop
    echo.
    pause
    exit /b 1
)
echo   [✓] Docker Desktop 已运行
echo.

:: ── 2. 配置 .env ──
echo   [2/4] 配置环境变量...

if exist ".env" (
    echo   [✓] .env 配置文件已存在，跳过配置
    echo        如需重新配置，请删除 .env 后重新运行本脚本
) else (
    echo   正在创建配置文件...
    echo.

    :: 生成随机密钥
    for /f "delims=" %%i in ('python -c "import secrets; print(secrets.token_urlsafe(32))" 2^>nul') do set "RANDOM_KEY=%%i"
    if not defined RANDOM_KEY set "RANDOM_KEY=change-me-to-a-random-secret-key"

    set "PORT=8000"

    :: 写入 .env
    (
        echo # 教师助手 — 环境配置
        echo PROJECT_NAME=teacherAssist
        echo DEBUG=false
        echo DATABASE_URL=sqlite+aiosqlite:///./data/teacher_assist.db
        echo SECRET_KEY=!RANDOM_KEY!
        echo ACCESS_TOKEN_EXPIRE_MINUTES=30
        echo REFRESH_TOKEN_EXPIRE_DAYS=7
        echo LLM_PROVIDER=
        echo LLM_DEFAULT_MAX_TOKENS=4096
        echo DEEPSEEK_API_KEY=
        echo DEEPSEEK_MODEL=deepseek-chat
        echo DEEPSEEK_MAX_TOKENS=4096
        echo DEEPSEEK_BASE_URL=
        echo ANTHROPIC_API_KEY=
        echo CLAUDE_MODEL=claude-sonnet-4-6
        echo CLAUDE_MAX_TOKENS=4096
        echo OPENAI_API_KEY=
        echo WHISPER_MODEL=whisper-1
        echo CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
        echo PORT=!PORT!
    ) > .env

    echo.
    echo   [✓] 配置已保存到 .env
    echo   AI 服务请在启动后通过网页右上角 ⚙️ 按钮进行配置。
)
echo.

:: ── 3. 构建镜像 ──
echo   [3/4] 构建 Docker 镜像...
echo   预计时间：5-10 分钟（首次需下载 Python 依赖包约 1.5GB）
echo.
docker compose build
if errorlevel 1 (
    echo   [✗] 镜像构建失败，请检查上方错误信息
    pause
    exit /b 1
)
echo   [✓] 镜像构建完成
echo.

:: ── 4. 启动服务 ──
echo   [4/4] 启动服务...
echo   注意：首次启动会下载语音识别模型（约 1.5GB）
echo.
docker compose up -d
if errorlevel 1 (
    echo   [✗] 服务启动失败
    pause
    exit /b 1
)

:: 等待服务就绪
echo   等待服务就绪...
for /l %%i in (1,1,30) do (
    curl -s http://localhost:%PORT%/api/v1/status >nul 2>&1
    if not errorlevel 1 goto :ready
    timeout /t 2 >nul
)
:ready

echo.
echo   ╔══════════════════════════════════════╗
echo   ║  安装完成！                          ║
echo   ╠══════════════════════════════════════╣
echo   ║  访问地址: http://localhost:%PORT%     ║
echo   ║  停止服务: docker compose down       ║
echo   ║  重新启动: docker compose up -d      ║
echo   ║  查看日志: docker compose logs -f    ║
echo   ╚══════════════════════════════════════╝
echo.

set /p "OPEN=是否在浏览器中打开？[Y/n]: "
if /i "!OPEN!"=="n" goto :end
start http://localhost:%PORT%

:end
pause
