"""評估準則的 SKILL.md 解析（對應 PR #21725 的 Skill/SkillSet 命名）。

每個 eval criteria 都是一個資料夾，包含 SKILL.md（YAML frontmatter + Markdown 內文）
以及可選的 ``references/`` 目錄，用來存放詳細 rubric。

``applies_to`` metadata 欄位會對應到 ``manifest.yaml`` 的 ``tool_modules``，
以便依技能領域自適應選擇準則。當原生
``make_judge(skills=[...])`` API 進入 MLflow 後，請以
``from mlflow.genai.skills import SkillSet`` 取代此模組。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 資料模型（對應 PR #21725 的 Skill Dataclass）
# ---------------------------------------------------------------------------


@dataclass
class Skill:
    """已解析的評估準則技能。

    對應 MLflow PR #21725 中的 ``Skill`` Dataclass::

        name, description, path, metadata, body, references, applies_to
    """

    name: str
    description: str
    path: Path
    metadata: dict[str, Any]
    body: str
    references: dict[str, str]  # {relative_path: content}
    applies_to: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 容器（對應 PR #21725 的 SkillSet）
# ---------------------------------------------------------------------------


class SkillSet:
    """評估準則技能的容器。

    建立時會立即解析 SKILL.md 檔案。提供 prompt 產生功能，
    供評判器指令注入，以及供工具呼叫時依名稱查找。
    """

    def __init__(self, paths: list[str | Path]):
        self.skills: list[Skill] = []
        for p in paths:
            try:
                self.skills.append(self._load_skill(p))
            except Exception as exc:
                logger.warning("Failed to load eval criteria from %s: %s", p, exc)
        self._by_name: dict[str, Skill] = {s.name: s for s in self.skills}

    # -- 公開 API --

    def get_skill(self, name: str) -> Skill | None:
        return self._by_name.get(name)

    def filter_by_modules(self, tool_modules: list[str]) -> "SkillSet":
        """回傳符合 *tool_modules* 的準則子集。

            ``applies_to`` 為空的準則一律會納入（通用型）。
            """
        filtered = [s for s in self.skills if not s.applies_to or any(m in s.applies_to for m in tool_modules)]
        result = SkillSet.__new__(SkillSet)
        result.skills = filtered
        result._by_name = {s.name: s for s in filtered}
        return result

    @property
    def names(self) -> list[str]:
        return [s.name for s in self.skills]

    def to_prompt_inline(self) -> str:
        """用於指令注入的完整本文 + references（目前使用方式）。

            會將每個 skill 的本文與 reference 檔案內嵌為單一 prompt 區塊，
            適合加到評判器指令前面。
            """
        if not self.skills:
            return ""
        sections: list[str] = ["# Evaluation Criteria\n"]
        for skill in self.skills:
            sections.append(f"## {skill.name}\n")
            sections.append(skill.body.strip())
            for ref_path, ref_content in skill.references.items():
                sections.append(f"\n### Reference: {ref_path}\n")
                sections.append(ref_content.strip())
            sections.append("")
        return "\n".join(sections)

    def to_prompt_summary(self) -> str:
        """僅含名稱 + 描述（未來的工具型用法）。

            會產生精簡摘要區塊，列出可用準則，讓
            agentic 評判器可決定要透過工具載入哪些準則。
            """
        if not self.skills:
            return ""
        lines = ["## Available Evaluation Criteria", ""]
        for s in self.skills:
            lines.append(f"- **{s.name}**: {s.description}")
        lines.append("")
        lines.append(
            "Use the read_skill tool to load relevant criteria. "
            "Use read_skill_file for detailed rubrics within a skill."
        )
        return "\n".join(lines)

    # -- 載入 --

    @staticmethod
    def _load_skill(path: str | Path) -> Skill:
        """解析 SKILL.md 檔案並立即載入 references。"""
        path = Path(path).resolve()
        skill_md = path / "SKILL.md" if path.is_dir() else path
        skill_dir = skill_md.parent

        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(content)

        name = frontmatter.get("name", skill_dir.name)
        description = frontmatter.get("description", "")
        metadata = frontmatter.get("metadata", {})
        applies_to = metadata.get("applies_to", [])
        if isinstance(applies_to, str):
            applies_to = [applies_to]

        references = _load_references(skill_dir)

        return Skill(
            name=name,
            description=description,
            path=skill_dir,
            metadata=metadata,
            body=body,
            references=references,
            applies_to=applies_to,
        )


# ---------------------------------------------------------------------------
# 探索
# ---------------------------------------------------------------------------


def discover_eval_criteria(
    criteria_dir: str | Path = ".test/eval-criteria",
) -> SkillSet:
    """自動探索 *criteria_dir* 中所有 eval-criteria 技能資料夾。"""
    base = Path(criteria_dir)
    if not base.is_dir():
        logger.debug("Eval criteria directory not found: %s", base)
        return SkillSet([])
    paths = sorted(d for d in base.iterdir() if d.is_dir() and (d / "SKILL.md").exists())
    if paths:
        logger.info(
            "Discovered %d eval criteria: %s",
            len(paths),
            ", ".join(p.name for p in paths),
        )
    return SkillSet(paths)


# ---------------------------------------------------------------------------
# 輔助函式
# ---------------------------------------------------------------------------


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """從 SKILL.md 檔案擷取 YAML frontmatter 與 Markdown 本文。"""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        return {}, content
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, match.group(2)


def _load_references(skill_dir: Path) -> dict[str, str]:
    """將 ``references/`` 中的所有文字檔立即載入記憶體。"""
    refs_dir = skill_dir / "references"
    if not refs_dir.is_dir():
        return {}
    result: dict[str, str] = {}
    for f in sorted(refs_dir.rglob("*")):
        if f.is_file() and f.suffix in (".md", ".txt", ".yaml", ".json"):
            rel = str(f.relative_to(skill_dir))
            try:
                result[rel] = f.read_text(encoding="utf-8")
            except Exception:
                logger.warning("Could not read reference file: %s", f)
    return result
