"""
TeacherAssist 启动器 — 双击运行或命令行调用均可。

用法:
    python launcher.py              # 默认端口 8000，自动打开浏览器
    python launcher.py --port 8080  # 指定端口
    python launcher.py --no-browser # 不打开浏览器
"""
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent


def find_python() -> str:
    """返回可用的 Python 解释器命令。"""
    return sys.executable


def check_dependencies() -> bool:
    """检查核心依赖，缺失则安装。"""
    for pkg in ("fastapi", "uvicorn", "sqlalchemy"):
        try:
            __import__(pkg)
        except ImportError:
            break
    else:
        print("依赖已就绪")
        return True

    print("正在安装依赖，首次运行需等待...")
    req = PROJECT_DIR / "requirements.txt"
    result = subprocess.run(
        [find_python(), "-m", "pip", "install", "-r", str(req), "-q"],
        cwd=str(PROJECT_DIR),
    )
    if result.returncode != 0:
        print(f"[错误] 依赖安装失败，请手动运行: pip install -r {req}")
        return False
    print("依赖已就绪")
    return True


def start_server(host: str, port: int) -> subprocess.Popen:
    """后台启动 uvicorn。"""
    return subprocess.Popen(
        [
            find_python(), "-m", "uvicorn",
            "app.main:app",
            "--host", host,
            "--port", str(port),
        ],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _open_browser(url: str) -> None:
    """打开浏览器，依次尝试三种方式确保成功。"""
    # 方式 1: os.startfile — Windows 最可靠
    try:
        import os
        os.startfile(url)
        return
    except Exception:
        pass

    # 方式 2: webbrowser 标准库
    try:
        webbrowser.open(url, new=2)
        return
    except Exception:
        pass

    # 方式 3: 兜底，打印 URL 让用户手动打开
    print(f"请手动打开浏览器访问: {url}")


def wait_for_server(port: int, timeout: float = 20.0) -> bool:
    """轮询等待服务就绪。"""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/v1/status", timeout=1
            )
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="TeacherAssist 启动器")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="127.0.0.1", help="绑定地址（局域网共享用 0.0.0.0）")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    print()
    print("  ╔══════════════════════════════════╗")
    print("  ║   TeacherAssist — 教师智能助手   ║")
    print("  ╚══════════════════════════════════╝")
    print()

    if not check_dependencies():
        input("按回车退出...")
        sys.exit(1)

    print(f"启动服务 (http://{args.host}:{args.port}) ...")
    process = start_server(args.host, args.port)

    url = f"http://{args.host}:{args.port}"
    if wait_for_server(args.port):
        print(f"服务已就绪: {url}")
    else:
        print(f"服务启动超时，请手动访问 {url}")

    if not args.no_browser:
        _open_browser(url)

    print()
    print("按 Ctrl+C 停止服务")
    try:
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=5)
        print("服务已停止")


if __name__ == "__main__":
    main()
