"""
教师助手 — 安装包构建脚本

自动化构建流程:
  python scripts/build_installer.py          # 完整构建（含模型）
  python scripts/build_installer.py --lite   # 轻量构建（不含模型，安装后下载）
  python scripts/build_installer.py --skip-download  # 跳过下载，仅编译

产出: dist/teacherAssist-setup-0.2.1.exe
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
BUILD_DIR = PROJECT_DIR / "build"
INSTALLER_SRC = BUILD_DIR / "installer"
DIST_DIR = PROJECT_DIR / "dist"
CACHE_DIR = BUILD_DIR / "cache"

PYTHON_VERSION = "3.11.9"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_EMBED_MIRROR = f"https://registry.npmmirror.com/-/binary/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_ZIP = CACHE_DIR / f"python-{PYTHON_VERSION}-embed-amd64.zip"

MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin"
MODEL_MIRROR = "https://hf-mirror.com/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin"
MODEL_FILE = CACHE_DIR / "ggml-medium.bin"

REQUIREMENTS = PROJECT_DIR / "requirements.txt"
SETUP_ISS = PROJECT_DIR / "scripts" / "setup.iss"
ISCC = Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe"

# Also check D drive custom install
_ISCC_D = Path("D:/teacherAssist-build/InnoSetup/ISCC.exe")
if not ISCC.exists() and _ISCC_D.exists():
    ISCC = _ISCC_D


def step(msg: str):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def download(url: str, dest: Path, description: str = ""):
    """下载文件，支持缓存和进度条。"""
    if dest.exists():
        size_mb = dest.stat().st_size / 1024 / 1024
        print(f"  [缓存] {dest.name} ({size_mb:.0f} MB) — 跳过下载")
        return

    if description:
        print(f"  {description}")
    print(f"  下载: {url}")
    print(f"  保存: {dest}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    def _hook(block_num, block_size, total_size):
        if total_size > 0:
            pct = min(100, int(block_num * block_size * 100 / total_size))
            mb_done = block_num * block_size / 1024 / 1024
            mb_total = total_size / 1024 / 1024
            bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct}%  {mb_done:.0f}/{mb_total:.0f} MB", end="", flush=True)

    try:
        urllib.request.urlretrieve(url, dest, reporthook=_hook)
        print()
        print(f"  [完成] {dest.name}")
    except Exception as e:
        print(f"\n  [失败] {e}")
        if dest.exists():
            dest.unlink()
        raise


def step1_clean(skip_installer: bool = False):
    """Step 1: 清理旧构建产物。

    Args:
        skip_installer: 为 True 时保留 build/installer/ 目录（用于 --skip-download）。
    """
    step("1/6 清理构建目录")
    if BUILD_DIR.exists():
        if skip_installer and INSTALLER_SRC.exists():
            # 只清理 dist/，保留 installer 和 cache
            for item in BUILD_DIR.iterdir():
                if item.name not in ("installer", "cache"):
                    if item.is_dir():
                        _rmtree_ignore_errors(item)
                    else:
                        try:
                            item.unlink()
                        except OSError:
                            pass
            print(f"  保留已构建目录: {INSTALLER_SRC}")
        else:
            # 只清理 installer 和 dist，保留 cache
            for item in BUILD_DIR.iterdir():
                if item.name not in ("cache",):
                    if item.is_dir():
                        _rmtree_ignore_errors(item)
                    else:
                        try:
                            item.unlink()
                        except OSError:
                            pass
            print("  保留下载缓存")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    INSTALLER_SRC.mkdir(parents=True, exist_ok=True)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    print("  完成")


def _rmtree_ignore_errors(path: Path):
    """删除目录树，忽略权限错误（文件被占用时跳过）。"""
    import stat
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            file_path = os.path.join(root, name)
            try:
                os.chmod(file_path, stat.S_IWRITE)
                os.unlink(file_path)
            except OSError:
                pass
        for name in dirs:
            dir_path = os.path.join(root, name)
            try:
                os.rmdir(dir_path)
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def step2_python():
    """Step 2: 下载并解压 Python 嵌入式运行时。"""
    step("2/6 准备 Python 运行时")

    # 下载 Python 嵌入式运行时
    # 先尝试官方源，失败再走镜像
    try:
        download(PYTHON_EMBED_URL, PYTHON_ZIP, "Python 嵌入式运行时 (~11MB) [官方]")
    except Exception:
        download(PYTHON_EMBED_MIRROR, PYTHON_ZIP, "Python 嵌入式运行时 (~11MB) [镜像]")

    # 解压到构建目录
    python_dir = INSTALLER_SRC / "python"
    print(f"  解压到: {python_dir}")
    with zipfile.ZipFile(PYTHON_ZIP, "r") as zf:
        zf.extractall(python_dir)

    # 配置 python._pth — 让嵌入式 Python 能找到 pip 安装的包
    pth_file = python_dir / "python311._pth"
    original = pth_file.read_text()
    # 取消 import site 的注释，启用 site-packages
    new_content = original.replace("#import site", "import site")
    # 添加 Lib 目录到搜索路径
    if "Lib" not in new_content:
        new_content += "\n..\\Lib\n"
    pth_file.write_text(new_content)
    print("  已配置 python._pth")

    # 安装 pip
    print("  安装 pip...")
    get_pip = CACHE_DIR / "get-pip.py"
    download("https://bootstrap.pypa.io/get-pip.py", get_pip)
    subprocess.run(
        [str(python_dir / "python.exe"), str(get_pip), "--no-warn-script-location"],
        cwd=str(INSTALLER_SRC), check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print("  pip 安装完成")


def step3_dependencies():
    """Step 3: 安装 Python 依赖到 Lib 目录。"""
    step("3/6 安装 Python 依赖 (~900MB 含 PyTorch)")

    python_exe = INSTALLER_SRC / "python" / "python.exe"
    lib_dir = INSTALLER_SRC / "Lib"

    PIP_CACHE = os.environ.get("PIP_CACHE_DIR", os.path.expanduser("~/AppData/Local/pip/cache"))

    # pip install 到 Lib 目录（含 PyTorch CPU 版）
    print("  安装主依赖 (含 PyTorch CPU)...")
    subprocess.run(
        [str(python_exe), "-m", "pip", "install",
         "-r", str(REQUIREMENTS),
         "--target", str(lib_dir),
         "--cache-dir", PIP_CACHE,
         "--extra-index-url", "https://download.pytorch.org/whl/cpu",
         "--no-warn-script-location",
         "--progress-bar", "on"],
        cwd=str(INSTALLER_SRC), check=True,
    )

    print("  依赖安装完成")


def step4_model(lite: bool = False):
    """Step 4: 下载 Whisper 语音模型（可选）。"""
    step("4/6 语音识别模型")

    if lite:
        print("  [轻量模式] 跳过模型下载 — 用户首次启动时自动下载")
        return

    models_dir = INSTALLER_SRC / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    model_dest = models_dir / "ggml-medium.bin"

    if MODEL_FILE.exists():
        print(f"  从缓存复制: {MODEL_FILE}")
        shutil.copy2(MODEL_FILE, model_dest)
    else:
        print("  尝试下载 (~1.5GB)...")
        try:
            download(MODEL_MIRROR, MODEL_FILE, "从国内镜像下载")
        except Exception:
            download(MODEL_URL, MODEL_FILE, "从 HuggingFace 下载")
        shutil.copy2(MODEL_FILE, model_dest)

    size_mb = model_dest.stat().st_size / 1024 / 1024
    print(f"  模型就绪: {size_mb:.0f} MB")


def step5_copy_code():
    """Step 5: 复制应用代码和静态文件。"""
    step("5/6 复制应用代码")

    # 需要复制的目录
    for folder in ["app", "static", "scripts"]:
        src = PROJECT_DIR / folder
        dst = INSTALLER_SRC / folder
        if dst.exists():
            shutil.rmtree(dst)
        # 排除 __pycache__
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # 复制 .env.example（安装后用户改名为 .env）
    shutil.copy2(PROJECT_DIR / ".env.example", INSTALLER_SRC / ".env.example")
    shutil.copy2(PROJECT_DIR / "launcher.py", INSTALLER_SRC / "launcher.py")

    # 创建空的 data 目录占位
    (INSTALLER_SRC / "data").mkdir(parents=True, exist_ok=True)
    # 写一个 .gitkeep 确保目录被打包
    (INSTALLER_SRC / "data" / ".placeholder").write_text("")

    print(f"  应用代码已复制到 {INSTALLER_SRC}")


def step6_compile():
    """Step 6: 编译 Inno Setup 安装包。"""
    step("6/6 编译安装包")

    if not ISCC.exists():
        print(f"  [错误] 未找到 Inno Setup 编译器")
        print(f"  预期路径: {ISCC}")
        print(f"  请下载安装: https://jrsoftware.org/isdl.php")
        print()
        print(f"  手动编译命令:")
        print(f'  "{ISCC}" "{SETUP_ISS}"')
        return False

    print(f"  编译器: {ISCC}")
    print(f"  脚本: {SETUP_ISS}")
    print(f"  输出: {DIST_DIR}")
    print()

    result = subprocess.run(
        [str(ISCC), str(SETUP_ISS)],
        cwd=str(PROJECT_DIR), check=False,
    )

    if result.returncode == 0:
        exe_files = list(DIST_DIR.glob("*.exe"))
        if exe_files:
            size_mb = exe_files[0].stat().st_size / 1024 / 1024
            print(f"\n  安装包已生成: {exe_files[0].name} ({size_mb:.0f} MB)")
        return True
    else:
        print(f"\n  [失败] ISCC 返回错误码 {result.returncode}")
        print(f"  请检查上方编译日志")
        return False


def main():
    parser = argparse.ArgumentParser(description="教师助手 安装包构建器")
    parser.add_argument("--lite", action="store_true", help="轻量模式：不含语音模型")
    parser.add_argument("--skip-download", action="store_true", help="跳过所有下载（使用缓存）")
    parser.add_argument("--skip-compile", action="store_true", help="跳过 Inno Setup 编译")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    os.chdir(str(script_dir.parent))

    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║   教师助手 — 安装包构建器             ║")
    print("  ╚══════════════════════════════════════╝")
    print(f"  模式: {'轻量（不含模型）' if args.lite else '完整（含模型）'}")
    print(f"  输出: {DIST_DIR}")
    print()

    step1_clean(skip_installer=args.skip_download)
    if args.skip_download:
        print("  [跳过] Python 运行时 (--skip-download)")
        print("  [跳过] pip 依赖 (--skip-download)")
        print("  [跳过] 语音模型 (--skip-download)")
    else:
        step2_python()
        step3_dependencies()
        step4_model(lite=args.lite)
    step5_copy_code()

    if not args.skip_compile:
        success = step6_compile()
        if not success:
            print()
            print("  ┌─────────────────────────────────────────┐")
            print("  │  提示: 构建目录已准备就绪              │")
            print(f"  │  {INSTALLER_SRC}                        │")
            print("  │                                        │")
            print("  │  你可以:                                │")
            print("  │  1. 安装 Inno Setup 后重新运行本脚本    │")
            print("  │  2. 或手动将构建目录打包为 ZIP 分发      │")
            print("  │  3. 或直接在构建目录运行 run_server.py  │")
            print("  └─────────────────────────────────────────┘")
        else:
            print()
            print("  ╔══════════════════════════════════════╗")
            print("  ║  构建成功！                          ║")
            print(f"  ║  {DIST_DIR}                         ║")
            print("  ╚══════════════════════════════════════╝")
    else:
        print()
        print(f"  构建目录已就绪: {INSTALLER_SRC}")
        print(f"  手动编译: ISCC.exe {SETUP_ISS}")
        print(f"  或直接 ZIP 分发: {INSTALLER_SRC}")


if __name__ == "__main__":
    main()
