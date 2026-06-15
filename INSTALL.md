# 教师助手 — 安装指南

> 版本 0.2.0

## 你需要准备什么

| 准备项 | 说明 |
|--------|------|
| Windows 电脑 | Windows 10/11（64 位），建议 8GB+ 内存，10GB+ 磁盘空间 |
| DeepSeek API Key | [免费注册获取](https://platform.deepseek.com/api_keys)（注册即送额度） |
| 安装包 | `teacherAssist-setup-0.2.0.exe` |

> **不需要**安装 Python 或任何其他软件——安装包已包含全部运行环境。

## 安装步骤

### 1. 双击安装包

双击 `teacherAssist-setup-0.2.0.exe`，点击 **下一步**。

### 2. 选择安装路径

```
默认: C:\Program Files\TeacherAssist
                        [浏览...]
```

可点击 **浏览** 选择其他位置。点击 **下一步**。

### 3. 选择组件

| 组件 | 建议 |
|------|------|
| ☑ 桌面快捷方式 | 推荐勾选 |
| ☐ 开机自启 | 按需选择 |

### 4. 等待安装

进度条完成后点击 **完成**。

### 5. 首次配置

首次启动时输入 DeepSeek API Key（可跳过，之后编辑安装目录下的 `.env` 文件填入）。

### 6. 开始使用

浏览器自动打开 `http://localhost:8000`，注册账号即可。

## 日常使用

| 操作 | 方法 |
|------|------|
| 启动 | 双击桌面"教师助手"图标 |
| 停止 | 关闭启动时弹出的命令窗口 |
| 修改 API Key | 记事本打开安装目录下的 `.env`，修改 `DEEPSEEK_API_KEY=你的Key` |
| 修改端口 | 编辑 `.env`，添加 `PORT=8080`，重新启动 |

## 安装后目录

```
安装目录\
├── python\          ← Python 运行环境
├── DLLs\            ← 系统扩展
├── Lib\             ← 依赖库（含 PyTorch、FastAPI 等）
├── app\             ← 程序代码
├── static\          ← 网页界面
├── models\          ← 语音识别模型 (1.5GB)
├── data\            ← 课堂数据
├── .env             ← 配置文件
├── 启动教师助手.bat  ← 启动脚本
└── unins000.exe     ← 卸载程序
```

## 常见问题

### 双击桌面图标没反应？

进入安装目录，双击 `启动教师助手.bat`。如提示"缺少 VCRUNTIME140.dll"，安装 [VC++ 运行库](https://aka.ms/vs/17/release/vc_redist.x64.exe)。

### 语音转录很慢？

45 分钟音频约需 12 分钟。首次转录需加载模型（~10 秒）。确认 `models\ggml-medium.bin` 存在且为 1.5GB。

### 局域网共享？

1. 查看本机 IP：`Win+R` → `cmd` → `ipconfig`
2. 其他人浏览器访问 `http://你的IP:8000`
3. 如无法访问，在 Windows 防火墙添加 8000 端口入站规则

### 如何备份？

复制安装目录下的 `data\teacher_assist.db` 即可。

## 卸载

**控制面板** → **程序和功能** → **教师助手** → **卸载**

卸载时可选保留数据，下次重装可恢复。

## 开发者

### 从源码构建

```bash
pip install -r requirements.txt
python scripts/build_installer.py    # 完整构建
python scripts/build_installer.py --lite  # 轻量（不含模型）
```
