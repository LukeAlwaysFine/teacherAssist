#!/bin/bash
# ═══════════════════════════════════════════════════
# 教师助手 — Docker 一键安装（Mac / Linux）
# 用法: bash scripts/install.sh
# ═══════════════════════════════════════════════════
set -e

cd "$(dirname "$0")/.."

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║   教师助手 — Docker 一键安装          ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── 1. 检查 Docker ──
echo "  [1/4] 检测 Docker 环境..."
if ! command -v docker &>/dev/null; then
    echo "  [✗] 未找到 Docker，请先安装 Docker Desktop 或 Docker Engine"
    echo "      下载: https://www.docker.com/products/docker-desktop/"
    exit 1
fi

if ! docker info &>/dev/null; then
    echo "  [✗] Docker 未运行，请先启动 Docker"
    exit 1
fi
echo "  [✓] Docker 已运行"
echo ""

# ── 2. 配置 .env ──
echo "  [2/4] 配置环境变量..."

if [ -f ".env" ]; then
    echo "  [✓] .env 配置文件已存在，跳过配置"
    echo "       如需重新配置，请删除 .env 后重新运行本脚本"
else
    echo "  正在创建配置文件..."
    echo ""

    # 生成随机密钥
    RANDOM_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || echo "change-me-to-a-random-secret-key")
    PORT=8000

    read -p "  1. DeepSeek API Key（必填）: " API_KEY
    if [ -z "$API_KEY" ]; then
        echo "  [✗] API Key 不能为空，安装中止"
        exit 1
    fi

    read -p "  2. 服务端口 [8000]: " USER_PORT
    PORT=${USER_PORT:-8000}

    cat > .env <<EOF
# 教师助手 — 环境配置
PROJECT_NAME=teacherAssist
DEBUG=false
DATABASE_URL=sqlite+aiosqlite:///./data/teacher_assist.db
SECRET_KEY=$RANDOM_KEY
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
LLM_PROVIDER=deepseek
LLM_DEFAULT_MAX_TOKENS=4096
DEEPSEEK_API_KEY=$API_KEY
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_MAX_TOKENS=4096
DEEPSEEK_BASE_URL=https://api.deepseek.com
ANTHROPIC_API_KEY=
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_MAX_TOKENS=4096
OPENAI_API_KEY=
WHISPER_MODEL=whisper-1
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
PORT=$PORT
EOF

    echo ""
    echo "  [✓] 配置已保存到 .env"
fi
echo ""

# ── 3. 构建镜像 ──
echo "  [3/4] 构建 Docker 镜像..."
echo "  预计时间：5-10 分钟（首次需下载 Python 依赖包约 1.5GB）"
echo ""

docker compose build
echo "  [✓] 镜像构建完成"
echo ""

# ── 4. 启动服务 ──
echo "  [4/4] 启动服务..."
echo "  注意：首次启动会下载语音识别模型（约 1.5GB）"
echo ""

docker compose up -d

# 等待服务就绪
echo "  等待服务就绪..."
for i in $(seq 1 30); do
    if curl -s "http://localhost:${PORT}/api/v1/status" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║  安装完成！                          ║"
echo "  ╠══════════════════════════════════════╣"
echo "  ║  访问地址: http://localhost:${PORT}     ║"
echo "  ║  停止服务: docker compose down       ║"
echo "  ║  重新启动: docker compose up -d      ║"
echo "  ║  查看日志: docker compose logs -f    ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

read -p "  是否在浏览器中打开？[Y/n]: " OPEN
if [ "$OPEN" != "n" ] && [ "$OPEN" != "N" ]; then
    if command -v open &>/dev/null; then
        open "http://localhost:${PORT}"
    elif command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:${PORT}"
    fi
fi
