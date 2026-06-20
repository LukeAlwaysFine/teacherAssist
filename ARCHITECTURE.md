# TeacherAssit 架构文档

## 目录

1. [总览](#总览)
2. [目录结构](#目录结构)
3. [请求流水线](#请求流水线)
4. [数据模型](#数据模型)
5. [认证体系](#认证体系)
6. [LLM 抽象层](#llm-抽象层)
7. [STT 语音识别层](#stt-语音识别层)
8. [服务层](#服务层)
9. [前端架构](#前端架构)
10. [关键设计决策](#关键设计决策)

---

## 总览

TeacherAssit 是面向教师的桌面软件，工作流为：录制音频 → 语音转文字 → AI 分析课堂 → 生成家长报告。

```
┌──────────┐    ┌──────────────┐    ┌──────────┐
│  音频录制  │ → │ Whisper.cpp  │ → │ LLM 分析  │ → 家长报告
│ (浏览器)   │    │ 语音转文字    │    │ 课堂分析   │
└──────────┘    └──────────────┘    └──────────┘
```

**技术栈**：Python 3.11+ / FastAPI (async) / SQLAlchemy 2.0 / JWT / 原生 JS SPA

**零 AI 框架依赖**：不使用 LangChain / LlamaIndex，直接调用 Anthropic SDK 和 OpenAI 兼容协议。

---

## 目录结构

```
TeacherAssit/
│
├── app/                              # 后端 (FastAPI)
│   ├── main.py                       #   应用入口：创建 FastAPI、注册中间件/路由、异常处理、自动迁移
│   │
│   ├── core/                         #   基础设施
│   │   ├── config.py                 #     Settings (pydantic-settings)：所有可配置项
│   │   ├── db.py                     #     AsyncEngine + AsyncSession 工厂
│   │   └── security.py              #     bcrypt 密码哈希 + JWT 生成/解码
│   │
│   ├── models/                       #   数据模型 (SQLAlchemy ORM)
│   │   ├── user.py                   #     User：邮箱/密码/角色
│   │   ├── session.py                #     Session：课堂记录 + 状态机
│   │   ├── transcript.py             #     Transcript：转录全文 + 时间轴
│   │   ├── analysis.py               #     AnalysisReport：AI 分析结果 + 家长报告缓存
│   │   ├── template.py               #     ReportTemplate：用户自定义报告模板
│   │   └── user_llm_config.py        #     UserLLMConfig：用户个人 LLM 配置
│   │
│   ├── schemas/                      #   Pydantic 请求/响应模型
│   │   ├── session.py                #     SessionCreate/Response/Detail/APIResponse...
│   │   └── user.py                   #     User 相关 schema
│   │
│   ├── api/                          #   路由层
│   │   ├── deps.py                   #     依赖注入：get_db() / get_current_user()
│   │   └── routes/
│   │       ├── auth.py               #     /api/v1/auth/*      注册/登录/刷新
│   │       ├── users.py              #     /api/v1/users/*     LLM 配置 CRUD
│   │       ├── sessions.py           #     /api/v1/*           课堂 CRUD / 录制 / 分析 / 报告 / 模板
│   │       ├── exercises.py          #     /api/v1/exercises/*
│   │       └── maintenance.py        #     /api/v1/maintenance/*  清理上传
│   │
│   ├── services/                     #   业务逻辑层
│   │   ├── auth_service.py           #     AuthService：注册/登录/刷新
│   │   ├── ai_service.py             #     AIService：LLM 调用 + 重试 + 分析/报告生成
│   │   ├── audio_service.py          #     AudioService：实时音频接收 + SSE 推送
│   │   ├── transcription_tracker.py  #     转录进度追踪（内存）
│   │   ├── stt/                      #     语音识别引擎
│   │   │   ├── base.py               #       BaseSTTEngine (ABC)
│   │   │   ├── whisper_cpu.py        #       WhisperCPUEngine
│   │   │   ├── whisper_cuda.py       #       WhisperCUDAEngine
│   │   │   ├── whisper_api.py        #       WhisperAPIEngine
│   │   │   └── __init__.py           #       create_stt_engine() 工厂 + 自动选引擎
│   │   └── llm/                      #     LLM 抽象层
│   │       ├── base.py               #       BaseLLMProvider (ABC) + ChatMessage/ChatResponse
│   │       ├── anthropic.py          #       AnthropicProvider (官方 SDK)
│   │       ├── deepseek.py           #       DeepSeekProvider (OpenAI 兼容协议)
│   │       └── __init__.py           #       create_llm_provider() 工厂
│   │
│   └── prompts/                      #   AI Prompt 模板 (.txt)
│       ├── classroom_analysis.txt    #     课堂分析 prompt
│       ├── parent_report.txt         #     家长报告 prompt（系统默认模板）
│       └── parent_report_revision.txt #    报告修订 prompt
│
├── static/                           # 前端 (SPA)
│   ├── index.html                    #    ~3000 行单页应用 (v18)，纯 JS，零框架
│   └── knowledge_outline.json       #    知识点大纲 (v4.1, 4 科目 2171 知识点)
│
├── tests/                            # 测试 (pytest + httpx)
│   ├── conftest.py                   #    fixtures：测试 DB + 认证 client
│   ├── test_sessions.py              #    5 个 session 相关测试
│   └── test_stt.py                   #    7 个 STT/AI 服务测试
│
├── scripts/                          # 构建/工具脚本
│   └── build_outline.py              #    大纲构建
│
├── .claude/                          # Claude Code 项目配置
│   └── settings.json                 #    共享设置（权限/hooks）
│
├── CLAUDE.md                         # AI 开发参考手册
├── ARCHITECTURE.md                   # 本文档
├── README.md                         # 项目说明
├── ROADMAP.md                        # 路线图
├── USER_GUIDE.md                     # 用户使用手册
├── .env.example                      # 环境变量模板
├── .gitignore
├── pyproject.toml                    # ruff + pytest 配置
└── launcher.py                       # 开发启动脚本
```

---

## 请求流水线

```
HTTP 请求
  │
  ├── CORS 中间件 (allow_origins / methods / headers)
  ├── 错误日志中间件 (记录所有 4xx/5xx)
  │
  ├── 路由匹配
  │   /api/v1/auth/*       → auth.py
  │   /api/v1/users/*      → users.py
  │   /api/v1/*            → sessions.py
  │   /api/v1/exercises/*  → exercises.py
  │   /api/v1/maintenance/* → maintenance.py
  │   /*                   → StaticFiles (index.html)
  │
  ├── 依赖注入链
  │   get_db()         → AsyncSession → 自动 commit/rollback
  │   get_current_user() → HTTPBearer → JWT 解码 → User ORM
  │
  ├── 路由处理器
  │   参数校验 (Pydantic) → 业务委托 (Service) → 组装响应 (APIResponse)
  │
  └── 全局异常兜底 → JSON {code, message, data}
```

### 三个优先级保证路由正确

1. API 路由通过 `app.include_router()` 显式注册
2. 静态文件 `StaticFiles` 最后 mount 到 `/`
3. FastAPI 按注册顺序匹配，确保 `/api/v1/*` 优先于 `/*` 静态文件

---

## 数据模型

### ER 图

```
User (1) ──────< (N) Session (1) ──────< (N) Transcript
  │                    │
  │                    └── (1:1) ── AnalysisReport
  │
  ├── (1:1) ── UserLLMConfig
  └── (1:N) ── ReportTemplate
```

### 模型详情

| 模型 | 表名 | 关键字段 |
|------|------|----------|
| **User** | `users` | id, email, hashed_password, full_name, role(teacher/student) |
| **Session** | `sessions` | id, teacher_id(FK), title, subject, student_name, status, audio_file_path, knowledge_outline(JSON), source(realtime/upload) |
| **Transcript** | `transcripts` | id, session_id(FK), full_text, raw_segments(JSON) |
| **AnalysisReport** | `analysis_reports` | id, session_id(FK), knowledge_points(JSON), classroom_performance(JSON), reinforcement_plan(JSON), parent_report, teacher_feedback |
| **ReportTemplate** | `report_templates` | id, user_id(FK), name, content, is_default |
| **UserLLMConfig** | `user_llm_configs` | id, user_id(FK, unique), provider, api_key, model, max_tokens, base_url, reasoning_effort |

### Session 状态机

```
created → recording → transcribing → analyzing → completed
  │         │            │              │            │
  └─────────┴────────────┴──────────────┴─────────→ failed
```

- `source="realtime"` 时直接从 `recording` 开始
- `source="upload"` 时从 `created` → 上传后 → `transcribing`
- 启动时检测 `transcribing` 超 30 分钟未更新 → 标记为 `failed`（僵尸恢复）
- 所有状态转换由路由处理器控制，不是 ORM 事件

---

## 认证体系

### 密码处理

```
用户注册 → hash_password(raw) → bcrypt (截断 72 字节) → 存 hashed_password
用户登录 → verify_password(raw, hashed) → bcrypt 比较 → 生成 JWT
```

### JWT 双令牌

| 令牌 | 用途 | 有效期 | 声明 |
|------|------|--------|------|
| access_token | 所有 API 鉴权 | 30 天 (43200 min) | `{sub: user_id, type: "access"}` |
| refresh_token | 换取新 access_token | 7 天 | `{sub: user_id, type: "refresh"}` |

签名算法：HS256，密钥来自 `SECRET_KEY` 环境变量。

### 鉴权流程

```
请求 → Authorization: Bearer <access_token>
         │
         ├── HTTPBearer 提取 token
         ├── jose.jwt.decode(token, SECRET_KEY)
         ├── 验证 type == "access"
         ├── 查找 User
         └── 返回 User ORM 对象（注入路由处理器）
```

### 路由保护

所有需要认证的路由通过 `Depends(get_current_user)` 保护，底层依赖 `get_db()`：

```python
@router.post("/sessions")
async def create_session(
    request: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ...
```

---

## LLM 抽象层

### 类层次

```
BaseLLMProvider (ABC)
├── chat(messages, temperature, max_tokens) → ChatResponse
│
├── AnthropicProvider
│   └── 官方 AsyncAnthropic SDK
│       自动处理 system message 分离
│
└── DeepSeekProvider
    └── OpenAI 兼容协议 (openai.AsyncOpenAI)
        覆盖: DeepSeek / OpenAI / 通义千问 / 智谱 / Groq / Ollama / ...
        支持 reasoning_effort 控制思考链深度
```

### 工厂函数

```python
create_llm_provider(
    provider="deepseek",    # 用户配置或系统默认
    api_key="sk-xxx",
    model="deepseek-chat",
    max_tokens=4096,
    base_url="https://api.deepseek.com",
    reasoning_effort="high",  # none / low / medium / high / max
) → BaseLLMProvider

决策逻辑：
  "anthropic" → AnthropicProvider
  其他/空      → DeepSeekProvider (OpenAI 兼容)
  未知名称     → 记录 warning，仍按 OpenAI 兼容处理
```

### AIService 封装

```
AIService.__init__(provider=None, user_config=None)
  ├── 有 user_config.is_configured() → 用用户配置
  ├── 有 provider                   → 用指定 provider
  └── 都没有                        → _has_valid_key = False

AIService.chat() / generate_*()
  → _call_llm()
    ├── 检查 _has_valid_key
    ├── @retry (tenacity, 最多 3 次, 指数退避)
    ├── provider.chat(messages)
    └── 返回 ChatResponse.content
```

### 三层 API Key 校验

```
第一道: Provider 构造时
        AsyncOpenAI 不允许空 key → 用 "sk-placeholder" 占位绕过

第二道: AIService._call_llm() 调用前
        _has_valid_key == False → 返回中文错误 "未配置 LLM API Key"

第三道: max_tokens 扩容
        检测 JSON 输出截断 → 自动扩大 max_tokens 重试
```

---

## STT 语音识别层

### 类层次

```
BaseSTTEngine (ABC)
├── transcribe(audio_path)      → STTResult
├── transcribe_chunk(bytes)     → STTResult
├── get_engine_info()           → dict (面向 UI)
│
├── WhisperCPUEngine    → pywhispercpp, 本地 CPU 推理
├── WhisperCUDAEngine   → pywhispercpp + CUDA, GPU 加速
└── WhisperAPIEngine    → OpenAI Whisper API, 云端
```

### 引擎自动选择

```python
create_stt_engine(force=None) → BaseSTTEngine

决策逻辑：
  1. 指定 force="cpu"|"cuda"|"api" → 直接使用
  2. 自动检测:
     torch.cuda.is_available() → WhisperCUDAEngine
     否则                       → WhisperCPUEngine
```

### STTResult

```python
@dataclass
class STTResult:
    text: str                    # 转写全文
    segments: list[dict]         # 分段时间轴
    engine_name: str             # "whisper-cpu" / "whisper-cuda" / "whisper-api"
    processing_time_seconds: float
    audio_duration_seconds: float
```

---

## 服务层

### 服务职责

| 服务 | 文件 | 职责 |
|------|------|------|
| **AuthService** | `auth_service.py` | 注册(邮箱唯一性检查) / 登录(bcrypt 验证) / 刷新令牌 |
| **AIService** | `ai_service.py` | LLM 调用封装(重试 + 截断修复) / 课堂分析 / 家长报告生成 / 报告修订 |
| **AudioService** | `audio_service.py` | 实时音频接收 / 临时文件管理 / SSE 推送转录进度 |
| **TranscriptionTracker** | `transcription_tracker.py` | 内存进度追踪 / 进度百分比轮询 |

### AIService 核心方法

```python
class AIService:
    # 课堂分析
    async def analyze_classroom(transcript, outline, subject) → dict
        # 知识点匹配、学生掌握情况、课堂互动、巩固建议

    # 家长报告
    async def generate_parent_report(analysis_result, subject, class_date,
        class_time, student_name, custom_template, teacher_feedback) → str
        # 模板占位符替换 → LLM 生成 → 友好报告

    # 报告修订
    async def revise_parent_report(existing_report, revision_instruction,
        analysis_result, subject, class_time) → str
        # 教师自然语言修改建议 → LLM 修订已有报告
```

### 模板占位符

用户可上传自定义 `.txt` 模板，支持 8 个占位符：

| 占位符 | 含义 |
|--------|------|
| `{subject}` | 科目 |
| `{date}` | 日期 |
| `{time}` | 时间 |
| `{student_name}` | 学生姓名 |
| `{total_knowledge_points}` | 知识点总数 |
| `{covered_count}` | 覆盖数量 |
| `{mastered_count}` | 掌握数量 |
| `{engagement_level}` | 参与度 |

---

## 前端架构

### 技术选型

- **纯 JS SPA**：零框架依赖（无 React/Vue），约 3000 行
- **路由**：基于 tab 切换的伪路由，无 History API
- **状态管理**：全局变量 + localStorage 草稿缓存
- **API 通信**：封装 `api()` 函数 → `fetch()` + JWT Bearer 头

### 页面结构

```
┌──────────────────────────────┐
│  Header: 用户信息 + 退出      │
├──────────────────────────────┤
│  Tab: 新建课堂 | 历史记录 | ⚙️  │
├──────────────────────────────┤
│  Step 1: 填写基础信息         │
│    - 学生姓名 / 科目 / 教材版本 │
│    - 选择知识点范围            │
│  Step 2: 录制或上传音频        │
│    - 实时录制 (MediaRecorder)  │
│    - 上传文件                  │
│    - 转录进度                  │
│  Step 3: 查看分析 + 报告       │
│    - AI 分析结果               │
│    - 家长报告 (可编辑/重生成)   │
│    - 教师定性反馈              │
│    - 报告图片导出              │
├──────────────────────────────┤
│  历史记录面板                  │
│    - 列表 / 详情 / 删除        │
├──────────────────────────────┤
│  设置面板                      │
│    - LLM 配置 (provider/key)  │
│    - 模板管理 (上传/设默认)    │
└──────────────────────────────┘
```

### 数据流

```
用户操作 → DOM 事件 → 函数
                      ├── 本地状态更新 (DOM 直接操作)
                      ├── api('GET/POST', url, data)
                      │     ├── fetch() + Authorization header
                      │     ├── 401 → logout()
                      │     └── 返回 {code, message, data}
                      └── 更新 DOM / 切换步骤
```

---

## 关键设计决策

### 1. 零 AI 框架

不使用 LangChain / LlamaIndex。原因：
- 业务场景是单次 LLM 调用，不需要链式编排
- Prompt 是静态模板，不需要动态组装
- 没有 RAG / Agent / Tool Use 需求
- 桌面软件场景下依赖越少越好

LLM 调用链只有三个依赖：`openai` / `anthropic` / `tenacity`。

### 2. 抽象工厂模式

两个 AI 子系统都使用 ABC + 工厂：

- **LLM**：`create_llm_provider()` 根据 provider 名路由到 Anthropic / OpenAI 兼容
- **STT**：`create_stt_engine()` 根据硬件能力路由到 CPU / CUDA / API

新增 provider 只需：实现 `BaseLLMProvider` ABC → 在工厂中注册。

### 3. 依赖注入

FastAPI `Depends` 贯穿所有横切关注点：

```python
db: AsyncSession = Depends(get_db)           # 数据库 session
user: User = Depends(get_current_user)       # JWT 认证
```

路由处理器保持轻量，只做参数校验和响应组装。

### 4. 用户可覆盖的 LLM 配置

```python
系统默认 → .env 文件 → 用户 UI 配置 (user_llm_configs 表) → 调用时传参
                                ↑ 优先级最高
```

每个用户可以设置自己的 API Key 和模型，AIService 自动加载。

### 5. 自动迁移（轻量级）

`_ensure_columns()` 在启动时运行：读取 SQLite PRAGMA → 对比模型定义 → ALTER TABLE ADD COLUMN。适用于桌面 SQLite 场景，避免引入 Alembic 的重量。

PostgreSQL 部署需手动执行 DDL。

### 6. 状态机

`Session.status` 的 6 个状态严格有序，防止非法操作：

- `created` 才能开始录制
- `transcribing` 完成才能触发分析
- 启动时恢复僵尸状态（超时未完成 → `failed`）

### 7. 统一 API 响应格式

```json
{
  "code": 200,
  "message": "成功",
  "data": {...}
}
```

所有端点返回 `APIResponse`，前端统一通过 `res.code` 判断成功/失败。

### 8. 报告缓存

`analysis.parent_report` 缓存家长报告文本，避免重复调用 LLM。仅在以下情况重新生成：

- 显式点击「重新生成」
- 通过修订接口修改
- 缓存为空时（如首次生成图片）
