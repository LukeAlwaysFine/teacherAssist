#!/bin/bash
# ═══════════════════════════════════════════════════
# Docker 容器入口 — 模型准备 + 服务启动
# ═══════════════════════════════════════════════════
set -e

MODEL_DIR="${WHISPER_MODELS_DIR:-/app/models}"
MODEL_FILE="$MODEL_DIR/ggml-medium.bin"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin"

echo "╔══════════════════════════════════════╗"
echo "║   教师助手 — Docker 容器启动          ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 检查/下载 Whisper 模型 ──
if [ -f "$MODEL_FILE" ]; then
    MODEL_SIZE=$(du -h "$MODEL_FILE" | cut -f1)
    echo "[✓] Whisper 模型已就绪: $MODEL_FILE ($MODEL_SIZE)"
else
    echo "[ ] Whisper 模型未找到，开始下载..."
    echo "    文件: $MODEL_FILE"
    echo "    大小: ~1.5GB（仅首次需要，后续启动跳过）"
    echo ""
    mkdir -p "$MODEL_DIR"
    wget -O "$MODEL_FILE" --show-progress "$MODEL_URL" 2>&1
    echo ""
    echo "[✓] 模型下载完成"
fi

echo ""

# ── 启动服务 ──
echo "[✓] 启动 FastAPI 服务..."
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info
