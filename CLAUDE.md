# teacherAssist — AI 开发参考

## 项目概述

面向教师的桌面软件：录制音频 → Whisper.cpp 转录 → AI 分析课堂 → 生成家长报告。支持 Anthropic / DeepSeek / 通义千问等任意 OpenAI 兼容 LLM。

## 技术栈

| 层级 | 技术 |
|------|------|
| Web 框架 | Python 3.11+ / FastAPI (async) |
| 数据库 | SQLite (开发) / PostgreSQL (生产) + SQLAlchemy 2.0 async |
| AI | 用户自配置：Anthropic SDK / OpenAI 兼容协议 (DeepSeek / 通义千问 / ...) |
| STT | Whisper.cpp (pywhispercpp) — CPU / CUDA / API |
| 认证 | JWT (python-jose) + bcrypt |
| 部署 | 原生 Windows 安装包 (Inno Setup) / Docker / 云 |
| 测试 | pytest + httpx (12 tests) |

## 目录结构

```
teacherAssist/
├── app/
│   ├── main.py              # FastAPI 入口（含自动迁移）
│   ├── api/routes/          # auth, sessions, users, maintenance, exercises
│   ├── core/                # config, security, db
│   ├── models/              # 6 个模型（User / Session / Transcript / AnalysisReport / ReportTemplate / UserLLMConfig）
│   ├── schemas/             # Pydantic 请求/响应
│   ├── services/
│   │   ├── ai_service.py    # AI 分析 + 家长报告生成/修订 + 用户 LLM 配置注入
│   │   ├── stt/             # whisper_cpu, whisper_cuda, whisper_api
│   │   └── llm/             # Anthropic SDK + OpenAI 兼容协议（用户自配置，不限厂商）
│   └── prompts/             # classroom_analysis / parent_report / parent_report_revision / exercise_scoring / feedback_summary
├── static/
│   ├── index.html           # SPA (20250618-v18)，含 LLM 配置、模板管理、报告修订 UI
│   └── knowledge_outline.json  # v4.1 — 4 科目 2171 知识点
├── USER_GUIDE.md            # 用户使用手册（面向教师的操作指南）
├── _downloaded.json         # 教材大纲下载缓存
├── scripts/                 # 构建/部署工具
├── tests/                   # 12 tests
└── *.md                     # 文档
```

## 关键架构决策

### API
- RESTful，统一格式 `{code, message, data}`
- 所有端点默认需认证（JWT）
- JWT Token 有效期 30 天（`ACCESS_TOKEN_EXPIRE_MINUTES=43200`）
- 新增端点：
  - `GET/PUT /users/me/llm-config` — 用户 LLM 配置
  - `POST/GET /templates` + `GET/PUT /templates/{id}` — 报告模板 CRUD
  - `POST /sessions/{id}/parent-report/revise` — AI 辅助报告修订
  - `DELETE /sessions/{id}` + `DELETE /sessions` — 删除课堂记录

### 报告模板
- 用户可上传自定义 .txt 模板，存储在 `report_templates` 表
- 支持 8 个占位符：`{subject} {date} {time} {student_name} {total_knowledge_points} {covered_count} {mastered_count} {engagement_level}`
- `template_id=0` 使用系统默认模板（`app/prompts/parent_report.txt`）；用户可设置默认模板，有默认模板时自动选用
- 占位符替换在 `AIService.generate_parent_report()` 中完成（用户模板和系统模板统一走替换逻辑）

### 家长报告修订
- 端点：`POST /sessions/{session_id}/parent-report/revise`
- 教师通过自然语言描述修改建议，LLM 结合原始分析数据和现有报告生成修订版
- 使用独立 prompt 文件 `app/prompts/parent_report_revision.txt`
- 修订后自动更新缓存的 `parent_report` 字段

### 教师定性反馈
- 生成家长报告时可附带 `teacher_feedback`（自然语言）
- 反馈作为补充上下文注入 LLM，但不完全覆盖课堂实际数据
- 存储在 `analysis_reports.teacher_feedback` 字段

### 知识点大纲 (v4.1)
- 6 级：科目→教材→年级→册→单元→节→知识点
- 4 科目（数学/历史/地理/科学），共 2171 知识点
- 人教版数学/历史/地理（1642 点）+ 浙教版初中科学（529 点）
- Prompt 以大纲为唯一分析框架
- STT 引擎支持 `WHISPER_MODELS_DIR` 环境变量

### AI 多 Provider
- 抽象基类 `BaseLLMProvider.chat()`
- 系统不预设 Provider（`LLM_PROVIDER=""`）；用户通过 ⚙️ 按钮自行配置
- `create_llm_provider()` 工厂函数接受可选覆盖参数（provider / api_key / model / max_tokens / base_url）
- Anthropic 走官方 SDK（`AnthropicProvider`）；其他所有厂商通过 OpenAI 兼容协议（`DeepSeekProvider`，底层为 `openai.AsyncOpenAI`）
- API Key 校验延迟到 `AIService._call_llm()` 调用时；未配置返回明确中文提示
- JSON 截断三道防线：max_tokens 扩容 + 三级自修复

### LLM 用户配置
- 配置存于 `user_llm_configs` 表（per-user，unique on user_id）
- 端点：`GET/PUT /users/me/llm-config`；首次 PUT 自动创建记录
- 支持字段：provider / api_key / model / max_tokens / base_url
- `AIService.__init__()` 接受 `user_config` 参数，自动加载用户配置覆盖系统默认
- Session 路由通过 `_create_ai_service()` 辅助函数统一注入用户 LLM 配置

### 数据库
- 默认路径：`./teacher_assist.db`（SQLite WAL）
- 6 张表（对应 6 个模型）；启动时通过 `_ensure_columns()` 自动补齐缺失列
- `_ensure_columns()` 读取 SQLite `PRAGMA table_info`，按需执行 `ALTER TABLE ADD COLUMN`
- 生产可切 PostgreSQL

### 课堂记录删除
- `DELETE /sessions/{session_id}` — 删除单个课堂，级联清理数据库记录 + 磁盘音频文件 + 上传目录
- `DELETE /sessions` — 清空当前用户所有课堂记录（不可逆）
- 删除前验证归属权（`session.teacher_id == current_user.id`）

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
