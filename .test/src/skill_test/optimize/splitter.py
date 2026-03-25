"""供 GEPA 優化使用的訓練/驗證資料集分割。

載入 ground_truth.yaml 測試案例，並在可行時依 metadata.category
進行分層 train/val 分割。

GEPA 的 DefaultDataInst 格式：{"input": str, "additional_context": dict[str, str], "answer": str}

我們會同時儲存內部任務表示，並在需要時透過 to_gepa_instances()
轉換為 GEPA 格式。
"""

import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, TypedDict

import yaml

from ..dataset import EvalRecord, get_dataset_source


class SkillTask(TypedDict, total=False):
    """內部任務表示（GEPA DefaultDataInst 的超集）。"""

    id: str
    input: str  # 提示文字（對應 DefaultDataInst.input）
    answer: str  # 預期回應（對應 DefaultDataInst.answer）
    additional_context: dict[str, str]  # 額外 context（對應 DefaultDataInst.additional_context）
    expectations: dict[str, Any]  # 評分器期望值（不直接傳給 GEPA）
    metadata: dict[str, Any]  # 類別、難度等


def _summarize_expectations(expectations: dict[str, Any]) -> str:
    """產生任務測試內容的人類可讀摘要。

    會放入 additional_context，讓 GEPA 的 reflection LM 不必解析 JSON，
    也能理解每個測試案例檢查的是什麼。
    """
    parts = []

    patterns = expectations.get("expected_patterns", [])
    if patterns:
        descs = []
        for p in patterns:
            if isinstance(p, str):
                descs.append(p[:40])
            elif isinstance(p, dict):
                descs.append(p.get("description", p.get("pattern", "")[:40]))
        parts.append(f"Patterns: {', '.join(descs)}")

    facts = expectations.get("expected_facts", [])
    if facts:
        parts.append(f"Facts: {', '.join(str(f) for f in facts)}")

    guidelines = expectations.get("guidelines", [])
    if guidelines:
        parts.append(f"Guidelines: {'; '.join(str(g) for g in guidelines[:3])}")

    return " | ".join(parts) if parts else "No specific expectations"


def _record_to_task(record: EvalRecord) -> SkillTask:
    """將 EvalRecord 轉換為我們的內部任務格式。"""
    task: SkillTask = {
        "id": record.id,
        "input": record.inputs.get("prompt", ""),
        "additional_context": {},
        "answer": "",
        "metadata": record.metadata or {},
    }
    if record.outputs:
        task["answer"] = record.outputs.get("response", "")
    if record.expectations:
        task["expectations"] = record.expectations
        # 也將 expectations 編碼進 additional_context，供 GEPA reflection 使用
        task["additional_context"]["expectations"] = json.dumps(record.expectations)
        # 給 GEPA reflection LM 的人類可讀摘要
        task["additional_context"]["evaluation_criteria"] = _summarize_expectations(record.expectations)
    return task


def to_gepa_instances(tasks: list[SkillTask]) -> list[dict[str, Any]]:
    """將內部任務轉換為 GEPA DefaultDataInst 格式。

    回傳 {"input": str, "additional_context": dict[str,str], "answer": str} 的清單
    """
    return [
        {
            "input": t["input"],
            "additional_context": t.get("additional_context", {}),
            "answer": t.get("answer", ""),
        }
        for t in tasks
    ]


def create_gepa_datasets(
    skill_name: str,
    val_ratio: float = 0.2,
    base_path: Path | None = None,
    seed: int = 42,
) -> tuple[list[SkillTask], list[SkillTask] | None]:
    """載入 ground_truth.yaml，依 metadata.category 分層，並切分為 train/val。

    對於少於 5 個測試案例的技能：全部作為 train，val=None（單任務模式）。
    對於至少 5 個測試案例的技能：採用分層 train/val 分割（泛化模式）。

    參數:
        skill_name: 要載入測試案例的技能名稱
        val_ratio: 要保留作為驗證集的測試案例比例
        base_path: 技能目錄基底路徑的覆寫值
        seed: 用於可重現分割的隨機種子

    回傳:
        (train_tasks, val_tasks) 的 tuple。若測試案例少於 5 個，val_tasks 會是 None。
    """
    source = get_dataset_source(skill_name, base_path)
    records = source.load()

    if not records:
        return [], None

    tasks = [_record_to_task(r) for r in records]

    # 數量太少，不足以做有意義的 val 分割
    if len(tasks) < 5:
        return tasks, None

    # 依類別分層
    by_category: dict[str, list[SkillTask]] = defaultdict(list)
    for task in tasks:
        cat = task.get("metadata", {}).get("category", "_uncategorized")
        by_category[cat].append(task)

    rng = random.Random(seed)
    train: list[SkillTask] = []
    val: list[SkillTask] = []

    for _cat, cat_tasks in by_category.items():
        rng.shuffle(cat_tasks)
        n_val = max(1, int(len(cat_tasks) * val_ratio))

        # 確保每個類別至少有 1 個 train 樣本
        if len(cat_tasks) - n_val < 1:
            n_val = len(cat_tasks) - 1

        if n_val <= 0:
            train.extend(cat_tasks)
        else:
            val.extend(cat_tasks[:n_val])
            train.extend(cat_tasks[n_val:])

    # 如果 val 最終為空，則回退
    if not val:
        return tasks, None

    return train, val


def create_cross_skill_dataset(
    skill_names: list[str] | None = None,
    max_per_skill: int = 5,
    base_path: Path | None = None,
    seed: int = 42,
    tool_modules: list[str] | None = None,
) -> list[SkillTask]:
    """從多個技能建立合併資料集，用於跨技能工具優化。

    若 ``skill_names`` 為 None，則會探索所有具有 ``ground_truth.yaml`` 的技能。
    會從每個技能載入任務、以 ``max_per_skill`` 為上限，並在每個任務上標記
    ``metadata["source_skill"]``。

    參數:
        skill_names: 要納入的特定技能。None = 自動探索全部。
        max_per_skill: 每個技能保留的最大任務數，以維持資料集平衡。
        base_path: 技能目錄基底路徑的覆寫值。
        seed: 用於可重現抽樣的隨機種子。

    回傳:
        合併後的 SkillTask dict 清單，每個項目都標記了 source_skill。
    """
    if base_path is None:
        base_path = Path(".test/skills")

    # 自動探索具有 ground_truth.yaml 的技能
    if skill_names is None:
        if not base_path.exists():
            return []
        skill_names = sorted(
            d.name
            for d in base_path.iterdir()
            if d.is_dir() and (d / "ground_truth.yaml").exists() and not d.name.startswith("_")
        )

    # 依 tool_modules 關聯性篩選技能
    if tool_modules:
        tool_modules_set = set(tool_modules)
        filtered = []
        for name in skill_names:
            manifest_path = base_path / name / "manifest.yaml"
            if manifest_path.exists():
                manifest = yaml.safe_load(manifest_path.read_text()) or {}
                skill_tool_modules = manifest.get("tool_modules")
                if skill_tool_modules is None:
                    # 沒有此欄位 → 預設納入（向後相容）
                    filtered.append(name)
                elif tool_modules_set & set(skill_tool_modules):
                    filtered.append(name)
                # 否則：skill 宣告的模組與之無交集 → 略過
            else:
                filtered.append(name)  # 沒有 manifest → 納入
        skill_names = filtered

    if not skill_names:
        return []

    rng = random.Random(seed)
    merged: list[SkillTask] = []

    for skill_name in skill_names:
        try:
            source = get_dataset_source(skill_name, base_path)
            records = source.load()
        except Exception:
            continue

        tasks = [_record_to_task(r) for r in records]

        # 標記來源技能
        for t in tasks:
            meta = t.get("metadata", {})
            meta["source_skill"] = skill_name
            t["metadata"] = meta

        # 對每個技能設上限
        if len(tasks) > max_per_skill:
            rng.shuffle(tasks)
            tasks = tasks[:max_per_skill]

        merged.extend(tasks)

    return merged


def generate_bootstrap_tasks(skill_name: str, base_path: Path | None = None) -> list[SkillTask]:
    """當不存在 ground_truth.yaml 時，從 SKILL.md 產生合成任務。

    會解析 SKILL.md 中記錄的模式，並產生可測試各模式的基本 prompt。

    參數:
        skill_name: 技能名稱
        base_path: 技能目錄基底路徑的覆寫值

    回傳:
        合成 SkillTask dict 清單
    """
    if base_path is None:
        # 為路徑解析找出 repo 根目錄
        from .utils import find_repo_root

        repo_root = find_repo_root()
        skill_md_candidates = [
            repo_root / ".claude" / "skills" / skill_name / "SKILL.md",
            repo_root / "databricks-skills" / skill_name / "SKILL.md",
        ]
    else:
        skill_md_candidates = [base_path.parent / skill_name / "SKILL.md"]

    skill_content = None
    for path in skill_md_candidates:
        if path.exists():
            skill_content = path.read_text()
            break

    if not skill_content:
        return []

    tasks: list[SkillTask] = []

    # 擷取 h2/h3 標題作為主題區域
    headers = re.findall(r"^#{2,3}\s+(.+)$", skill_content, re.MULTILINE)

    for i, header in enumerate(headers):
        tasks.append(
            {
                "id": f"bootstrap_{i:03d}",
                "input": f"Using the {skill_name} skill, help me with: {header}",
                "additional_context": {},
                "answer": "",
                "metadata": {"category": "bootstrap", "source": "auto_generated"},
            }
        )

    # 擷取 code block 的語言提示，以產生更具針對性的 prompt
    code_langs = set(re.findall(r"```(\w+)\n", skill_content))
    for lang in code_langs:
        tasks.append(
            {
                "id": f"bootstrap_lang_{lang}",
                "input": f"Show me a {lang} example using {skill_name} patterns",
                "additional_context": {},
                "answer": "",
                "metadata": {"category": "bootstrap", "source": "auto_generated"},
            }
        )

    return tasks or [
        {
            "id": "bootstrap_general",
            "input": f"Explain the key patterns in {skill_name}",
            "additional_context": {},
            "answer": "",
            "metadata": {"category": "bootstrap", "source": "auto_generated"},
        }
    ]
