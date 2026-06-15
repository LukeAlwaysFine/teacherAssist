# teacherAssist — 教师智能助手

面向教育机构老师的桌面软件，提供 **课堂录制分析** 和 **家长反馈报告** 两大核心能力。

## 功能概览

| 功能 | 说明 |
|------|------|
| 🎙️ 课堂录制 | 实时录音（chunk 上传）或文件上传（mp3/wav/m4a/webm 等格式直送转录） |
| 📝 语音转文字 | 本地 Whisper.cpp / GPU 加速 / 云端 API 三种引擎，实时进度 + 心跳平滑推进 |
| 🤖 AI 课堂分析 | 基于 6 级知识点大纲分析覆盖程度、掌握程度、互动表现 |
| 📨 家长反馈报告 | 首次生成后缓存，再次查看即时显示；支持强制重新生成 |
| 📷 报告图片导出 | 一键生成 PNG 图片，可下载分享 |
| 🔐 用户系统 | JWT 登录/注册，数据隔离 |

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
1. 注册/登录
2. 新建课堂 → 填写学生姓名、标题、上课时间、选择知识点大纲
3. 录制或上传音频 → 选择转录引擎 → 等待转录完成
4. AI 分析 → 查看报告（知识点覆盖、掌握程度、互动、巩固建议）
5. 生成家长报告 → 一键导出 PNG 图片
```

## 知识点大纲

6 级结构：科目 → 教材 → 年级 → 册 → 单元/章 → 节 → 知识点

- 168 单元、529 节、1642 知识点
- 覆盖 6 套人教版教材（数学 / 历史 / 地理 × 初中 2024 版 + 高中 2019 版）

## API 文档

服务启动后访问 `http://localhost:8000/docs`（Swagger UI）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 用户注册 |
| POST | `/api/v1/auth/login` | 用户登录 |
| POST | `/api/v1/sessions` | 创建课堂 |
| GET | `/api/v1/sessions` | 课堂列表 |
| GET | `/api/v1/sessions/{id}` | 课堂详情 |
| POST | `/api/v1/sessions/{id}/upload` | 上传音频 |
| POST | `/api/v1/sessions/{id}/analyze` | AI 分析 |
| POST | `/api/v1/sessions/{id}/parent-report` | 家长报告 |
| POST | `/api/v1/sessions/{id}/report-image` | 报告图片 |
| POST | `/api/v1/maintenance/clear-uploads` | 清空上传 |

统一响应格式：`{ "code": 200, "message": "ok", "data": {...} }`

## 项目结构

```
teacherAssist/
├── app/                    # 后端：FastAPI + SQLAlchemy + AI 服务
├── static/                 # 前端 SPA + 知识点大纲 JSON
├── scripts/                # 构建/部署脚本
├── tests/                  # pytest 测试（12 个）
├── launcher.py             # 开发启动器
├── start.bat               # Windows 开发一键启动
├── Dockerfile              # Docker 镜像（备选）
├── docker-compose.yml      # Docker 编排（备选）
├── requirements.txt        # Python 依赖
└── *.md                    # 文档
```

## 配置项

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key（必填） |
| `SECRET_KEY` | JWT 签名密钥（生产环境务必修改） |
| `LLM_PROVIDER` | AI 提供商：deepseek / anthropic |
| `DATABASE_URL` | 数据库连接（默认 SQLite） |

## 部署方式

| 方式 | 说明 |
|------|------|
| **原生安装包** | Inno Setup 打包，用户双击即装（推荐分发方式） |
| **Docker** | `docker compose up -d`（开发者备选） |
| **云端** | Railway / 阿里云 / 腾讯云（备选，详见下方） |

云端部署参考：

| 平台 | 月费 | 适用场景 |
|------|------|---------|
| Railway | ~$5-8 | 海外用户 |
| 阿里云 ECS | ¥50-100 | 国内用户 |
| 腾讯云 | ¥50-80 | 国内备选 |

## 测试

```bash
pytest    # 12 个测试，自动生成 test_report.xml
```

## 路线图

详见 [ROADMAP.md](ROADMAP.md)
