"""
STT (Speech-to-Text) 引擎抽象层。

支持 Whisper.cpp CPU / CUDA / OpenAI Whisper API 三种后端。
通过工厂函数自动检测硬件并选择最优引擎。
"""
from app.services.stt.base import BaseSTTEngine
from app.services.stt.whisper_cpu import WhisperCPUEngine

__all__ = ["BaseSTTEngine", "WhisperCPUEngine", "create_stt_engine"]


def create_stt_engine(force: str | None = None) -> BaseSTTEngine:
    """工厂函数：根据硬件和配置创建 STT 引擎。

    Args:
        force: 强制指定引擎类型 ("cpu" | "cuda" | "api" 或其全名
               "whisper_cpu" | "whisper_cuda" | "whisper_api")。
               为 None 时自动选择最优可用的。

    Returns:
        BaseSTTEngine 实例。

    Raises:
        ValueError: 指定的引擎不可用。
    """
    # 规范化：支持短名和全名两种格式
    if force:
        force = force.removeprefix("whisper_")

    if force == "cpu":
        return WhisperCPUEngine()

    if force == "cuda":
        try:
            from app.services.stt.whisper_cuda import WhisperCUDAEngine
            return WhisperCUDAEngine()
        except ImportError as e:
            raise ValueError(f"CUDA 引擎不可用: {e}") from e

    if force == "api":
        try:
            from app.services.stt.whisper_api import WhisperAPIEngine
            return WhisperAPIEngine()
        except ImportError as e:
            raise ValueError(f"API 引擎不可用: {e}") from e

    # 自动选择：GPU > CPU
    if force is None:
        if _cuda_available():
            try:
                from app.services.stt.whisper_cuda import WhisperCUDAEngine
                return WhisperCUDAEngine()
            except ImportError:
                pass
        return WhisperCPUEngine()

    raise ValueError(f"未知引擎类型: {force}")


def _cuda_available() -> bool:
    """检测 CUDA 是否可用。"""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def get_system_info() -> dict:
    """获取服务器 STT 相关系统信息。

    Returns:
        dict: {
            gpu_available: bool,
            gpu_info: str | None,
            cpu_info: str,
            api_configured: bool,
            default_engine: str,
            available_engines: list[str],
        }
    """
    import platform
    from app.core.config import settings

    gpu = _cuda_available()
    gpu_info = None
    if gpu:
        try:
            import torch
            gpu_info = torch.cuda.get_device_name(0)
        except Exception:
            pass

    # 检查是否配置了 OpenAI Key（Whisper API 需要）
    whisper_api_ok = bool(getattr(settings, 'OPENAI_API_KEY', None))

    engines = ["whisper_cpu"]
    if gpu:
        engines.append("whisper_cuda")
    if whisper_api_ok:
        engines.append("whisper_api")

    return {
        "gpu_available": gpu,
        "gpu_info": gpu_info,
        "cpu_info": platform.processor() or "未知",
        "api_configured": whisper_api_ok,
        "default_engine": "whisper_cuda" if gpu else "whisper_cpu",
        "available_engines": engines,
    }
