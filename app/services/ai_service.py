"""
AI 服务层。

提供课堂反馈总结、习题评分等 AI 能力。
底层通过可插拔的 LLMProvider 调用大模型，支持 DeepSeek / Claude 等厂商切换。
"""
import json
import logging
import re
from typing import Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.services.llm.base import BaseLLMProvider, ChatMessage
from app.services.llm import create_llm_provider

logger = logging.getLogger(__name__)


class AIServiceError(Exception):
    """AI 服务调用异常。"""
    pass


class AIService:
    """AI 服务 — 课堂反馈总结、习题评分等。

    通过工厂函数自动选择 LLM Provider（DeepSeek / Anthropic / ...）。
    如需自定义 Provider，可显式传入。
    """

    def __init__(self, provider: BaseLLMProvider | None = None) -> None:
        """初始化 AI 服务。

        Args:
            provider: LLM Provider 实例。为 None 时根据配置自动创建。
        """
        self.provider = provider or create_llm_provider()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((AIServiceError,)),
    )
    async def _call_llm(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """调用 LLM（带重试）。

        Args:
            system_prompt: 系统提示词。
            user_message: 用户消息内容。
            temperature: 采样温度。
            max_tokens: 本次调用最大 token 数，为 None 时使用 Provider 默认值。

        Returns:
            LLM 响应文本。

        Raises:
            AIServiceError: 调用失败时抛出。
        """
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_message),
        ]
        try:
            response = await self.provider.chat(
                messages, temperature=temperature, max_tokens=max_tokens
            )
            logger.info(
                f"LLM call success | provider={self.provider.provider_name} "
                f"model={response.model} "
                f"tokens_in={response.usage.get('input_tokens', 0)} "
                f"tokens_out={response.usage.get('output_tokens', 0)}"
            )
            return response.content
        except Exception as e:
            logger.error(f"LLM call failed via {self.provider.provider_name}: {e}")
            raise AIServiceError(f"AI 服务暂时不可用: {e}") from e

    async def summarize_feedback(
        self, feedback_texts: list[str]
    ) -> str:
        """汇总学生课堂反馈。

        Args:
            feedback_texts: 学生反馈文本列表。

        Returns:
            AI 生成的结构化总结。
        """
        if not feedback_texts:
            return "暂无反馈数据。"

        system_prompt = self._load_prompt("feedback_summary")
        user_message = "以下是学生课堂反馈，请汇总：\n\n" + "\n---\n".join(
            f"{i+1}. {text}" for i, text in enumerate(feedback_texts)
        )
        return await self._call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
        )

    async def suggest_exercise_score(
        self, question: str, student_answer: str, reference_answer: str
    ) -> str:
        """为课后习题提供评分建议。

        Args:
            question: 习题题目。
            student_answer: 学生答案。
            reference_answer: 参考答案。

        Returns:
            AI 评分建议（含分数和评语）。
        """
        system_prompt = self._load_prompt("exercise_scoring")
        user_message = (
            f"题目：{question}\n\n"
            f"参考答案：{reference_answer}\n\n"
            f"学生答案：{student_answer}"
        )
        return await self._call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
        )

    async def analyze_classroom(
        self,
        transcript: str,
        knowledge_outline: str,
    ) -> dict[str, Any]:
        """分析课堂教学：以知识点大纲为核心框架，完成纠错+角色标注+分析。

        大纲作为分析的唯一框架——LLM 围绕每个知识点进行纠错、
        覆盖判断、掌握评估和巩固建议。大纲外的内容不作为分析对象。

        Args:
            transcript: 完整转录文本。
            knowledge_outline: 知识点大纲（每行一个知识点）。

        Returns:
            dict: 结构化分析结果，包含:
                - cleaned_transcript: str 参照大纲纠错+角色标注后的转录
                - knowledge_points: list 逐条知识点覆盖分析
                - student_mastery: list 逐条知识点掌握程度
                - classroom_performance: dict 课堂互动（仅统计与大纲相关的互动）
                - reinforcement_plan: list 仅针对大纲薄弱点的巩固建议
        """
        if not transcript:
            raise AIServiceError("转录文本为空，无法分析")
        if not knowledge_outline:
            raise AIServiceError("知识点大纲为空，无法分析")

        system_prompt = self._load_prompt("classroom_analysis")
        user_message = (
            f"## 知识点大纲\n{knowledge_outline}\n\n"
            f"## 课堂转录\n{transcript}"
        )
        raw_response = await self._call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.3,
            max_tokens=32768,  # 课堂分析含整份转录+知识点数组，需大 token 上限
        )

        # 尝试解析 JSON 响应（含截断修复）
        try:
            result = self._parse_analysis_json(raw_response)
            return result
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            raise AIServiceError(
                f"LLM 返回格式异常，无法解析分析结果: {e}"
            ) from e

    @staticmethod
    def _parse_analysis_json(raw: str) -> dict[str, Any]:
        """解析 LLM 返回的 JSON，含截断自修复。

        课堂分析响应通常很长（含 cleaned_transcript + 知识点数组 +
        互动分析 + 巩固建议），可能因 token 限制被截断。
        此方法尝试逐步修复截断的 JSON。

        Args:
            raw: LLM 原始响应文本。

        Returns:
            解析后的 dict，自动附加 _raw_llm_response 字段。

        Raises:
            json.JSONDecodeError: 所有修复尝试均失败时抛出。
        """
        # 提取 JSON（可能在 ```json 代码块中）
        json_str = raw
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        json_str = json_str.strip()

        last_error = None

        # 尝试 1: 直接解析
        try:
            result = json.loads(json_str)
            result["_raw_llm_response"] = raw
            return result
        except json.JSONDecodeError as e:
            last_error = e
            logger.info(f"JSON parse attempt 1 failed: {e}, trying repair...")

        # 尝试 2: 修复未终止的字符串（补上引号）
        try:
            repaired = AIService._repair_truncated_json(json_str)
            result = json.loads(repaired)
            logger.warning("JSON repaired after truncation — response may be incomplete")
            result["_raw_llm_response"] = raw
            result["_json_truncated"] = True
            return result
        except json.JSONDecodeError as e:
            last_error = e
            logger.info(f"JSON parse attempt 2 failed: {e}")

        # 尝试 3: 补全未闭合的括号和花括号
        try:
            repaired = AIService._repair_truncated_json(json_str, close_braces=True)
            result = json.loads(repaired)
            logger.warning("JSON repaired with brace closing — response may be incomplete")
            result["_raw_llm_response"] = raw
            result["_json_truncated"] = True
            return result
        except json.JSONDecodeError as e:
            last_error = e

        # 所有修复失败，抛出最后一个错误
        raise last_error if last_error else json.JSONDecodeError(
            "All repair attempts failed", json_str, 0
        )

    @staticmethod
    def _repair_truncated_json(json_str: str, close_braces: bool = False) -> str:
        """尝试修复被截断的 JSON。

        Args:
            json_str: 可能被截断的 JSON 字符串。
            close_braces: 是否补齐未闭合的 {} 和 []。

        Returns:
            修复后的 JSON 字符串。
        """
        s = json_str.rstrip()

        # 1. 如果最后是未完成的字符串（奇数个引号），补上引号
        in_string = False
        escaped = False
        last_string_end = -1
        for i, ch in enumerate(s):
            if escaped:
                escaped = False
                continue
            if ch == '\\':
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                if not in_string:
                    last_string_end = i

        if in_string:
            # 字符串未闭合 — 补引号
            s = s + '"'

        # 2. 按需补齐括号
        if close_braces:
            open_braces = s.count('{') - s.count('}')
            open_brackets = s.count('[') - s.count(']')
            s = s + '}' * open_braces + ']' * open_brackets

        return s

    async def generate_parent_report(
        self,
        analysis_result: dict[str, Any],
        subject: str = "",
        class_date: str = "",
        class_time: str = "",
    ) -> str:
        """将课堂分析结果转化为家长友好的学习反馈报告。

        Args:
            analysis_result: analyze_classroom() 返回的分析结果字典。
            subject: 学科名称（如"地理""数学"）。
            class_date: 上课日期（如"2026年6月6日"）。
            class_time: 上课时间（如"16:30-18:30"）。

        Returns:
            纯文本格式的家长反馈报告。

        Raises:
            AIServiceError: LLM 调用失败时抛出。
        """
        # 提取关键字段，精简 token 消耗
        summary = {
            "knowledge_points": analysis_result.get("knowledge_points", []),
            "classroom_performance": analysis_result.get("classroom_performance"),
            "reinforcement_plan": analysis_result.get("reinforcement_plan", []),
        }

        system_prompt = self._load_prompt("parent_report")
        system_prompt = system_prompt.replace("{subject}", subject or "未指定")
        system_prompt = system_prompt.replace("{date}", class_date or "未指定")
        system_prompt = system_prompt.replace("{time}", class_time or "未指定")

        user_message = (
            f"请根据以下课堂分析数据，生成家长反馈报告：\n\n"
            f"```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```"
        )

        raw_response = await self._call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.5,
            max_tokens=16384,  # 家长报告需要足够篇幅，避免截断
        )
        return raw_response.strip()

    @staticmethod
    def _load_prompt(name: str) -> str:
        """加载 Prompt 模板。

        Args:
            name: Prompt 文件名（不含扩展名）。

        Returns:
            Prompt 文本内容。
        """
        import os
        prompt_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
        prompt_path = os.path.join(prompt_dir, f"{name}.txt")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"Prompt file not found: {prompt_path}, using default")
            return "你是一位专业的教育辅助 AI 助手。"
