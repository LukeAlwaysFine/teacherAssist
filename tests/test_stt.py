"""
STT 引擎单元测试。
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.stt.base import BaseSTTEngine, STTResult
from app.services.stt.whisper_cpu import WhisperCPUEngine


class TestBaseSTTEngine:
    """测试抽象基类。"""

    def test_cannot_instantiate_abstract(self):
        """不能直接实例化抽象基类。"""
        with pytest.raises(TypeError):
            BaseSTTEngine()


class TestWhisperCPUEngine:
    """测试 CPU 引擎。"""

    def test_engine_name(self):
        """引擎名称正确。"""
        engine = WhisperCPUEngine(model_name="medium")
        assert engine.engine_name == "whisper_cpu"

    def test_engine_label(self):
        """引擎显示名称。"""
        engine = WhisperCPUEngine()
        assert "CPU" in engine.engine_label

    def test_get_engine_info(self):
        """引擎信息结构完整。"""
        info = WhisperCPUEngine.get_engine_info()
        assert info["id"] == "whisper_cpu"
        assert "name" in info
        assert "speed" in info
        assert "cost" in info
        assert "pros" in info
        assert "cons" in info
        assert "hardware_requirements" in info


class TestSTTResult:
    """测试 STTResult 数据类。"""

    def test_stt_result_fields(self):
        """STTResult 字段正确。"""
        result = STTResult(
            text="测试转录文本",
            segments=[{"start": 0, "end": 2.0, "text": "测试"}],
            engine_name="test",
            processing_time_seconds=1.0,
            audio_duration_seconds=2.0,
        )
        assert result.text == "测试转录文本"
        assert len(result.segments) == 1
        assert result.engine_name == "test"
        assert result.processing_time_seconds == 1.0


class TestAIService:
    """测试 AI 服务。"""

    @pytest.mark.asyncio
    async def test_analyze_classroom_empty_transcript(self):
        """空转录文本应抛出异常。"""
        from app.services.ai_service import AIService, AIServiceError

        service = AIService()
        with pytest.raises(AIServiceError, match="转录文本为空"):
            await service.analyze_classroom(
                transcript="",
                knowledge_outline="知识点1\n知识点2",
            )

    @pytest.mark.asyncio
    async def test_analyze_classroom_empty_outline(self):
        """空大纲应抛出异常。"""
        from app.services.ai_service import AIService, AIServiceError

        service = AIService()
        with pytest.raises(AIServiceError, match="大纲为空"):
            await service.analyze_classroom(
                transcript="老师：今天我们来学习数学。",
                knowledge_outline="",
            )
