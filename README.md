# teacherAssist — 教师智能助手

面向教育机构老师的桌面软件，提供 **课堂录制分析** 和 **家长反馈报告** 两大核心能力。

🌐 **项目主页**: [Gitee Pages（国内快）](https://lukealwaysfine.gitee.io/teacher-assistant) | [GitHub Pages](https://lukealwaysfine.github.io/teacherAssist/)  
📥 **下载**: [夸克网盘（国内高速）](https://pan.quark.cn/s/3014cec4fcef) | [GitHub Release](https://github.com/LukeAlwaysFine/teacherAssist/releases/tag/v0.2.1) (154 MB, Windows 10/11)

## 功能概览

| 功能 | 说明 |
|------|------|
| 🎙️ 课堂录制 | 实时录音（chunk 上传）或文件上传（mp3/wav/m4a/webm 等格式） |
| 📝 语音转文字 | 本地 Whisper.cpp / GPU 加速 / 云端 API 三种引擎，实时进度追踪 |
| 🤖 AI 课堂分析 | 基于知识大纲分析覆盖程度、掌握程度、互动表现 |
| 📨 家长反馈报告 | 首次生成后缓存；支持自定义模板 + 教师定性观察 + LLM 修订 |
| 📂 报告模板管理 | 用户可上传自定义 .txt 模板，支持 8 个占位符变量 |
| ⚙️ 自配 LLM | 用户自行配置 API Key，不限厂商（DeepSeek/OpenAI/Anthropic/Ollama 等） |
| 💬 教师定性观察 | 分析前输入对学生的观察，AI 结合生成更准确的报告 |
| 📷 报告图片导出 | 一键生成 PNG 图片，可下载分享 |
| 🔐 用户系统 | JWT 持久登录（30 天有效），数据隔离 |
| 🗑️ 课堂管理 | 删除单个课堂或清空全部记录 |

## 安装

> 📖 **用户安装指南**: 详见 **[INSTALL.md](INSTALL.md)**


### 普通用户（推荐）

1. 获取 `teacherAssist-setup-x.x.x.exe`
2. 双击 → 选择安装路径 → 下一步 → 完成
3. 浏览器自动打开，注册账号即可使用
4. 不需要安装 Python 或任何其他软件

### 开发者

```bash
pip install -r requirements.txt
python launcher.py
```

浏览器打开 `http://localhost:8000`

## 使用流程

```
1. 注册/登录 → 首次使用先配置 LLM API（右上角 ⚙️ API）
2. 新建课堂 → 填写学生姓名、标题、上课时间、选择知识点大纲
3. 录制或上传音频 → 选择转录引擎 → 等待转录完成
4. 输入教师定性观察（可选）→ AI 分析课堂
5. 生成家长报告 → 可选自定义模板 → 一键导出 PNG
```

## 知识点大纲

6 级结构：科目 → 教材 → 年级 → 册 → 单元/章 → 节 → 知识点

- **人教版数学/历史/地理** — 168 单元、529 节、1642 知识点（初中 2024 + 高中 2019）
- **浙教版初中科学** — 24 单元、150 节、529 知识点（七/八/九年级上下册）
- **合计：4 科目，2171 知识点**

## LLM 配置

系统不预设 AI 服务。用户需通过右上角 **⚙️ API** 按钮自行配置：

| 字段 | 说明 |
|------|------|
| 提供商名称 | 如 deepseek / openai / anthropic / groq / ollama |
| API Key | 你的 API 密钥（必填） |
| 模型 ID | 如 deepseek-chat / gpt-4o / claude-sonnet-4-6 |
| API 地址 | OpenAI 兼容端点 URL（必填） |

支持所有 OpenAI 兼容协议的 API 服务。

## 报告模板变量

| 变量 | 说明 |
|------|------|
| `{subject}` `{date}` `{time}` `{student_name}` | 基础信息 |
| `{total_knowledge_points}` `{covered_count}` | 知识点统计 |
| `{mastered_count}` `{engagement_level}` | 掌握程度 / 参与度 |

## API 文档

服务启动后访问 `http://localhost:8000/docs`（Swagger UI）

核心端点：`/api/v1/auth/*` `/api/v1/sessions/*` `/api/v1/templates/*` `/api/v1/users/me/*`

统一响应格式：`{ "code": 200, "message": "ok", "data": {...} }`

## 项目结构

```
teacherAssist/
├── app/                    # FastAPI + SQLAlchemy + AI 服务（6 个模型）
├── static/                 # SPA + 知识点大纲 JSON（v4.1）
├── tests/                  # pytest（12 个）
├── launcher.py             # 开发启动器
├── ARCHITECTURE.md         # 架构文档
└── *.md                    # 项目文档
```

## 配置项

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` | JWT 签名密钥（生产环境务必修改） |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token 有效期（默认 43200 = 30 天） |
| `DATABASE_URL` | 数据库连接（默认 SQLite） |

LLM 配置通过 UI 完成，无需修改 `.env`。

## 测试

```bash
pytest    # 12 个测试，自动生成 test_report.xml
```
