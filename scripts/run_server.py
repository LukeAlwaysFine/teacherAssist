"""
教师助手 — Windows 服务启动器

双击此脚本启动服务（含系统托盘图标 + 自动打开浏览器）。
支持参数: --port 8000 --no-browser --no-tray

使用 pystray 创建系统托盘图标，右键菜单可打开/停止/退出。
如 pystray 不可用，降级为命令行模式。
"""
import argparse
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# 安装目录（exe / 脚本所在目录的上一层或当前目录）
if getattr(sys, 'frozen', False):
    INSTALL_DIR = Path(sys.executable).parent
else:
    INSTALL_DIR = Path(__file__).resolve().parent.parent

MODELS_DIR = INSTALL_DIR / "models"
DATA_DIR = INSTALL_DIR / "data"
ENV_FILE = INSTALL_DIR / ".env"
MODEL_FILE = MODELS_DIR / "ggml-medium.bin"
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin"
MIRROR_URL = "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin"


def find_python() -> str:
    """查找嵌入式 Python 或系统 Python。"""
    # 优先使用安装目录下的嵌入式 Python
    embedded = INSTALL_DIR / "python" / "pythonw.exe"  # pythonw 无控制台窗口
    if embedded.exists():
        return str(embedded)
    # 其次找带窗口的 python.exe
    embedded_cmd = INSTALL_DIR / "python" / "python.exe"
    if embedded_cmd.exists():
        return str(embedded_cmd)
    # 兜底用系统 Python
    return sys.executable


def check_model() -> bool:
    """检查语音模型是否存在，不存在则尝试下载。"""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if MODEL_FILE.exists():
        return True
    return False


def download_model():
    """下载语音模型（阻塞，显示进度）。"""
    import urllib.request

    print("正在下载语音识别模型（约 1.5GB，仅首次需要）...")
    print(f"保存位置: {MODEL_FILE}")
    print()

    urls = [MODEL_URL, MIRROR_URL]
    for url in urls:
        try:
            _download_with_progress(url, MODEL_FILE)
            print("\n模型下载完成！")
            return
        except Exception as e:
            print(f"下载失败 ({url}): {e}")
            print("尝试备用地址...")

    print("\n自动下载失败。请手动下载模型：")
    print(f"  1. 用浏览器下载: {MIRROR_URL}")
    print(f"  2. 保存到: {MODEL_FILE}")
    print(f"  3. 重新启动教师助手")
    input("按回车退出...")


def _download_with_progress(url: str, dest: Path):
    """带进度条的下载。"""
    import urllib.request

    def _hook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100, int(downloaded * 100 / total_size))
            mb_done = downloaded / 1024 / 1024
            mb_total = total_size / 1024 / 1024
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct}%  {mb_done:.0f}MB / {mb_total:.0f}MB", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=_hook)


def ensure_config():
    """确保 .env 配置文件存在。"""
    if ENV_FILE.exists():
        return

    print("首次运行 — 正在初始化配置文件...")
    print()

    secret = __import__('secrets').token_urlsafe(32)

    ENV_FILE.write_text(f"""# 教师助手 — 环境配置
PROJECT_NAME=teacherAssist
DEBUG=false
DATABASE_URL=sqlite+aiosqlite:///./data/teacher_assist.db
SECRET_KEY={secret}
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
LLM_PROVIDER=
LLM_DEFAULT_MAX_TOKENS=4096
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_MAX_TOKENS=4096
DEEPSEEK_BASE_URL=
ANTHROPIC_API_KEY=
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_MAX_TOKENS=4096
OPENAI_API_KEY=
WHISPER_MODEL=whisper-1
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
""", encoding="utf-8")

    print("配置已保存！AI 服务请在启动后通过网页右上角 [设置] 按钮进行配置。")
    print()


def start_uvicorn(host: str, port: int) -> subprocess.Popen:
    """启动 uvicorn 服务进程。"""
    python = find_python()

    # 设置环境变量
    env = os.environ.copy()
    env["WHISPER_MODELS_DIR"] = str(MODELS_DIR)

    # 切换到安装目录运行
    return subprocess.Popen(
        [python, "-m", "uvicorn", "app.main:app",
         "--host", host, "--port", str(port)],
        cwd=str(INSTALL_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def open_browser(url: str):
    """打开浏览器，多种方式兜底。"""
    try:
        os.startfile(url)
        return
    except Exception:
        pass
    try:
        webbrowser.open(url, new=2)
        return
    except Exception:
        pass
    print(f"请手动打开浏览器访问: {url}")


def wait_for_server(port: int, timeout: float = 30.0) -> bool:
    """轮询等待服务就绪。"""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/status", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def run_tray(port: int):
    """系统托盘模式（Windows 任务栏图标）。"""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        print("(pystray 未安装，使用命令行模式；pip install pystray 可启用托盘图标)")
        run_console(port)
        return

    # 创建简单的托盘图标
    icon_img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon_img)
    draw.ellipse([4, 4, 28, 28], fill=(26, 115, 232))
    draw.text((10, 6), "TA", fill=(255, 255, 255))

    url = f"http://127.0.0.1:{port}"
    process = None
    monitor_thread = None

    def on_open():
        open_browser(url)

    def on_stop():
        nonlocal process
        if process:
            process.terminate()

    def on_exit(icon):
        nonlocal process
        icon.stop()
        if process:
            process.terminate()

    menu = pystray.Menu(
        pystray.MenuItem("打开教师助手", on_open, default=True),
        pystray.MenuItem("停止服务", on_stop),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_exit),
    )

    icon = pystray.Icon("teacherassist", icon_img, "教师助手", menu)

    # 在新线程启动托盘
    def run_icon():
        icon.run()

    # 在后台监控服务状态
    def monitor():
        nonlocal process
        while process and process.poll() is None:
            time.sleep(1)

    process = start_uvicorn("127.0.0.1", port)
    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()

    if wait_for_server(port):
        open_browser(url)

    run_icon()


def run_console(port: int):
    """命令行模式（无托盘时降级）。"""
    print()
    print("  ╔══════════════════════════════════╗")
    print("  ║   教师助手 — 教师智能助手         ║")
    print("  ╚══════════════════════════════════╝")
    print()

    # 检查模型
    if not check_model():
        download_model()

    # 检查配置
    ensure_config()

    # 确保数据目录
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 启动
    url = f"http://127.0.0.1:{port}"
    print(f"启动服务 ({url}) ...")
    process = start_uvicorn("127.0.0.1", port)

    if wait_for_server(port):
        print(f"服务已就绪")
        open_browser(url)
    else:
        print(f"启动超时，请手动访问 {url}")

    print()
    print("按 Ctrl+C 停止服务")
    print("浏览器访问: " + url)
    print()

    try:
        # 持续输出服务日志
        for line in process.stdout:
            print(line, end="")
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        process.terminate()
        process.wait(timeout=5)
        print("服务已停止")


def main():
    parser = argparse.ArgumentParser(description="教师助手 启动器")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-tray", action="store_true")
    args = parser.parse_args()

    # 首次运行检查
    if not check_model():
        download_model()
    ensure_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.no_tray or sys.platform != "win32":
        run_console(args.port)
    else:
        run_tray(args.port)


if __name__ == "__main__":
    main()
