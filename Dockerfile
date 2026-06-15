# ═══════════════════════════════════════════════════
# 教师助手 — Docker 镜像
# 构建: docker build -t teacherassist .
# ═══════════════════════════════════════════════════

FROM python:3.11-slim

LABEL org.opencontainers.image.title="teacherAssist"
LABEL org.opencontainers.image.description="教师智能助手 — 课堂录音转录 + AI 分析"

# 系统依赖：ffmpeg（音频解码）、wget（模型下载）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 缓存层，代码变动不重装）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 复制应用代码
COPY app/ ./app/
COPY static/ ./static/
COPY scripts/entrypoint.sh ./scripts/

# 数据目录（运行时 volume 挂载）
RUN mkdir -p /app/data /app/models

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV WHISPER_MODELS_DIR=/app/models
ENV DATABASE_URL=sqlite+aiosqlite:///./data/teacher_assist.db

ENTRYPOINT ["bash", "scripts/entrypoint.sh"]
