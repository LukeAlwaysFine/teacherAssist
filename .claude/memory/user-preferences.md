---
name: user-preferences
description: 用户决策历史和开发偏好（更新至 2026-06-16）
metadata:
  type: user
---

## 技术决策历史

- **大模型**：默认 DeepSeek，可切换到 Anthropic Claude（改 .env）
- **STT 引擎**：Whisper.cpp，CPU/CUDA/API 三条路径
- **数据库**：本地 SQLite WAL（零配置），生产 PostgreSQL
- **异步方案**：asyncio.create_task，不要 Celery/Redis
- **说话人分离**：1v1 场景 LLM 从语义推断，不要 pyannote.audio
- **知识点大纲**：6 级级联选择器，1642 知识点，6 套人教版教材
- **LLM 分析**：以知识点大纲为唯一框架，逐条分析
- **bcrypt**：直用 bcrypt，不要 passlib
- **部署**：原生 Windows 安装包优先（用户双击即装），不需要装 Python/Docker
- **分发**：单个 setup.exe + 两个 txt 说明文件

## 工作偏好

- 架构设计 → 代码生成 → 代码审查 → 测试编写
- 先规划后实现
- 中文交流，中文输出
- UI 交互优先考虑老师实际场景
- 用户视角优先：傻瓜式一键操作，不要技术术语

**Why:** 记录完整决策链。
**How to apply:** 后续开发遵循。参见 [[project-overview]] 和 [[architecture-conventions]]。
