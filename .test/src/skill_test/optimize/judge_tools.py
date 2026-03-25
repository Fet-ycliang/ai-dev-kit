"""供 MLflow JudgeToolRegistry 使用的評判器工具（對應 PR #21725 命名）。

實作 ``ReadSkillTool`` 與 ``ReadSkillFileTool``，並註冊到 MLflow
全域 ``JudgeToolRegistry``，讓任何以 trace 為基礎的評判器都能使用。

這些工具在目前以欄位為基礎的評判器中不會啟用（沒有 agentic loop），但已
為未來的 trace-based 評判器做好準備。

當原生 ``make_judge(skills=[...])`` API 進入 MLflow 後，請以 MLflow 內建的技能工具取代此
模組。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mlflow.entities.trace import Trace
from mlflow.genai.judges.tools.base import JudgeTool
from mlflow.genai.judges.tools.registry import register_judge_tool
from mlflow.types.llm import (
    FunctionToolDefinition,
    ParamProperty,
    ToolDefinition,
    ToolParamsSchema,
)

from .eval_criteria import SkillSet

logger = logging.getLogger(__name__)


class ReadSkillTool(JudgeTool):
    """讀取某個評估準則技能的完整本文。

    當某個準則的描述與它正在評估的 trace 相符時，
    評判器會呼叫此工具。
    """

    def __init__(self, skill_set: SkillSet):
        self._skill_set = skill_set

    @property
    def name(self) -> str:
        return "read_skill"

    def get_definition(self) -> ToolDefinition:
        available = self._skill_set.names
        return ToolDefinition(
            function=FunctionToolDefinition(
                name="read_skill",
                description=(
                    "Read the full content of an evaluation criteria skill to get "
                    "domain-specific rubrics, scoring rules, and reference material. "
                    "Use this when a criteria's description matches the trace content. "
                    f"Available criteria: {available}"
                ),
                parameters=ToolParamsSchema(
                    properties={
                        "skill_name": ParamProperty(
                            type="string",
                            description="Name of the evaluation criteria to read",
                        ),
                    },
                ),
            ),
        )

    def invoke(self, trace: Trace, skill_name: str) -> str:
        skill = self._skill_set.get_skill(skill_name)
        if not skill:
            available = self._skill_set.names
            return f"Error: No criteria named '{skill_name}'. Available: {available}"
        return skill.body


class ReadSkillFileTool(JudgeTool):
    """從某個準則的 ``references/`` 目錄讀取參考文件。

    用於詳細 rubric、邊界案例與評分範例。
    已防範 path traversal：會拒絕絕對路徑與 ``..`` 元件。
    """

    def __init__(self, skill_set: SkillSet):
        self._skill_set = skill_set

    @property
    def name(self) -> str:
        return "read_skill_file"

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            function=FunctionToolDefinition(
                name="read_skill_file",
                description=(
                    "Read a reference document from an evaluation criteria skill "
                    "for detailed rubrics, edge cases, or scoring examples."
                ),
                parameters=ToolParamsSchema(
                    properties={
                        "skill_name": ParamProperty(
                            type="string",
                            description="Name of the evaluation criteria",
                        ),
                        "file_path": ParamProperty(
                            type="string",
                            description="Relative path within the skill (e.g., 'references/RUBRIC.md')",
                        ),
                    },
                ),
            ),
        )

    def invoke(self, trace: Trace, skill_name: str, file_path: str) -> str:
        skill = self._skill_set.get_skill(skill_name)
        if not skill:
            available = self._skill_set.names
            return f"Error: No criteria named '{skill_name}'. Available: {available}"
        normalized = os.path.normpath(file_path)
        if normalized.startswith("..") or os.path.isabs(normalized):
            return f"Error: Invalid file path '{file_path}'. Must be relative."
        if normalized not in skill.references:
            return f"Error: File '{file_path}' not found in '{skill_name}'"
        return skill.references[normalized]


_registered = False


def register_skill_tools(skill_set: SkillSet) -> None:
    """在 MLflow 全域 ``JudgeToolRegistry`` 中註冊技能工具。

    可安全多次呼叫——每個 process 只會註冊一次工具。
    """
    global _registered
    if _registered:
        return
    if not skill_set.skills:
        logger.debug("No eval criteria loaded; skipping tool registration")
        return
    register_judge_tool(ReadSkillTool(skill_set))
    register_judge_tool(ReadSkillFileTool(skill_set))
    _registered = True
    logger.info(
        "Registered skill judge tools (%d criteria available)",
        len(skill_set.skills),
    )
