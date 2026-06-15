---
name: project-overview
description: teacherAssist 项目核心信息、技术栈和当前进度（更新至 2026-06-16）
metadata:
  type: project
---

teacherAssist 是一款面向 1v1 教学老师的桌面软件。

**核心功能：**
1. **课堂分析** — 录制课堂音频 → Whisper.cpp 语音转文字 → LLM 以知识点大纲为框架分析
2. **课后习题收集** — 教师可发布、收集、批改课后习题（待实现）

**技术栈（v0.2.0）：**
- Python 3.11+ / FastAPI (async)
- SQLite WAL（本地）/ PostgreSQL（生产）
- SQLAlchemy 2.0 (async) / 无 Redis / 无 Celery
- DeepSeek（默认 LLM）/ Anthropic Claude（备选）
- Whisper.cpp (pywhispercpp) — CPU / CUDA / API 三条路径
- JWT 认证 (python-jose + bcrypt)
- ruff (lint/format) / pytest (12 tests)

**知识点大纲 v4.0：**
- 6 级：科目 → 教材 → 年级 → 册 → 单元/章 → 节 → 知识点
- 168 单元 / 529 节 / 1642 知识点
- 6 套人教版教材：数学/历史/地理 × 初中(2024版) + 高中(2019版)
- 前端 6 级级联选择器，向后兼容旧 5 级格式

**部署（v0.2.0）：**
- 主要：原生 Windows 安装包（Inno Setup，自包含 Python 3.14 + 模型 1.5GB）
- 备选：Docker / 源码运行 / 云端
- 交付：teacherAssist-setup-0.2.0.exe + 安装说明.txt + 使用说明.txt

**项目路径：** `D:\AI_PROJ\TeacherAssit`
**Why:** 经过多轮迭代确定的架构和功能。
**How to apply:** 所有开发基于此。参见 [[architecture-conventions]]。
