# teacherAssist — AI 开发参考

## 项目概述

面向教师的桌面软件：录制音频 → Whisper.cpp 转录 → DeepSeek/Claude 分析课堂 → 生成家长报告。

## 技术栈

| 层级 | 技术 |
|------|------|
| Web 框架 | Python 3.11+ / FastAPI (async) |
| 数据库 | SQLite (开发) / PostgreSQL (生产) + SQLAlchemy 2.0 async |
| AI | 多 Provider：DeepSeek (默认) / Anthropic Claude |
| STT | Whisper.cpp (pywhispercpp) — CPU / CUDA / API |
| 认证 | JWT (python-jose) + bcrypt |
| 部署 | 原生 Windows 安装包 (Inno Setup) / Docker / 云 |
| 测试 | pytest + httpx (12 tests) |

## 目录结构

```
teacherAssist/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── api/routes/          # auth, sessions, users, maintenance, exercises
│   ├── core/                # config, security, db
│   ├── models/              # user, session, transcript, analysis, exercise
│   ├── schemas/             # Pydantic 请求/响应
│   ├── services/
│   │   ├── ai_service.py    # AI 分析 + 家长报告
│   │   ├── stt/             # whisper_cpu, whisper_cuda, whisper_api
│   │   └── llm/             # base, deepseek, anthropic
│   └── prompts/             # classroom_analysis.txt, parent_report.txt ...
├── static/
│   ├── index.html           # SPA (20250615-v4)
│   └── knowledge_outline.json  # v4.0 — 6级 1642知识点
├── scripts/                 # 构建/部署工具
├── tests/                   # 12 tests
└── *.md                     # 文档
```

## 关键架构决策

### API
- RESTful，统一格式 `{code, message, data}`
- 所有端点默认需认证（JWT）

### 知识点大纲 (v4.0)
- 6 级：科目→教材→年级→册→单元→节→知识点
- 168 单元 / 529 节 / 1642 知识点
- Prompt 以大纲为唯一分析框架
- STT 引擎支持 `WHISPER_MODELS_DIR` 环境变量

### AI 多 Provider
- 抽象基类 `BaseLLMProvider.chat()`
- 切换：修改 `.env` 中 `LLM_PROVIDER=deepseek|anthropic`
- JSON 截断三道防线：max_tokens 扩容 + 三级自修复

### 数据库
- 默认路径：`./data/teacher_assist.db`（SQLite WAL）
- 生产可切 PostgreSQL

### 部署
- 主要：Inno Setup 打包为 setup.exe
- 备选：Docker / 云部署

## 代码规范

- PEP 8 / ruff / 蛇形命名 / Google docstring
- 所有函数签名含类型注解
- 异步优先 (async/await)
- 业务异常：`AppException` → 全局 handler

## 开发命令

```bash
pytest                          # 运行测试
python launcher.py              # 启动开发服务器
python scripts/build_installer.py  # 构建安装包
```
