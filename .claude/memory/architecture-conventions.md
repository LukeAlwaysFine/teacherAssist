---
name: architecture-conventions
description: 项目架构约定和代码规范（更新至 2026-06-16）
metadata:
  type: project
---

## 分层架构

Router → Service → Model（严格单向依赖）

- **Router**：路由绑定、参数解析、依赖注入，不含业务逻辑
- **Service**：核心业务逻辑、LLM/STT 编排、事务管理
- **Model**：SQLAlchemy ORM，无独立 Repository 层

## 响应格式

```json
{ "code": 200, "data": {...}, "message": "ok" }
```

## 代码规范

- PEP 8 + ruff（pyproject.toml 配置）
- 完整类型注解 / Google 风格 docstring
- 异步优先（所有 I/O 用 async/await）/ 蛇形命名

## LLM：多 Provider 可插拔

- `BaseLLMProvider` → `chat()` 统一接口
- `DeepSeekProvider`（默认）/ `AnthropicProvider`（备选）
- 切换：`.env` 中 `LLM_PROVIDER`
- Prompt 以大纲为唯一框架 / JSON 截断三道防线

## STT：Whisper.cpp 引擎层

- `BaseSTTEngine` → `transcribe()` + `transcribe_chunk()`
- `WhisperCPUEngine` / `WhisperCUDAEngine` / `WhisperAPIEngine`
- 支持 `WHISPER_MODELS_DIR` 环境变量自定义模型路径
- 工厂函数自动检测 CUDA

## 知识点大纲 v4.0

- 6 级：科目→教材→年级→册→单元→节→知识点
- 数据：`static/knowledge_outline.json`（1642 知识点）
- 前端：`getSections()` 向后兼容旧 5 级格式

## 前端：static/index.html (20250615-v4)

- FastAPI StaticFiles mount，API 路由优先
- 大纲 6 级级联选择器 + 手动补充

## 部署

- 主要：Inno Setup 打包 → setup.exe（自包含 Python + 依赖 + 模型）
- 备选：Docker / 源码 / 云端

## 关键修复记录

- 数据库建表：lifespan 中 `Base.metadata.create_all`
- bcrypt：直用 bcrypt（不用 passlib），截断 72 字节
- StaticFiles mount 必须在 API 路由注册之后
- 数据库默认路径：`./data/teacher_assist.db`

**Why:** 所有决策经过迭代验证。
**How to apply:** 代码生成和审查以本文档为基准。参见 [[project-overview]]。
