"""用於讓評判器與人工回饋對齊的 MemAlign 整合。

MemAlign 透過雙重記憶讓評判器與人工回饋對齊：
  - 語意記憶：可泛化的評估原則
  - 情節記憶：特定的邊界案例與修正

對齊 trace 會依技能儲存在：
    .test/skills/<skill>/alignment_traces.yaml

透過 ``scripts/review.py --align`` 來填充，此時人工會修正
評判結果。MemAlign 會從這些修正中學習原則，
隨時間提升評判準確度。

只需 2 到 10 個範例，就能看到明顯改善。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def load_alignment_traces(skill_name: str) -> list[dict[str, Any]]:
    """載入某個技能經人工修正的對齊 trace。

    trace 儲存在 .test/skills/<skill>/alignment_traces.yaml
    格式如下：
        - inputs: {prompt: "..."}
          outputs: {response: "..."}
          expected_value: true/false 或 0.0-1.0
          rationale: "人工對正確判決的說明"

    回傳:
        trace dict 清單；若找不到 trace 則回傳空清單。
    """
    traces_path = Path(".test/skills") / skill_name / "alignment_traces.yaml"
    if not traces_path.exists():
        return []

    try:
        with open(traces_path) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Failed to load alignment traces for %s: %s", skill_name, e)
        return []


def align_judge(
    skill_name: str,
    judge: Any,
    reflection_lm: str = "openai:/gpt-4o-mini",
) -> Any:
    """使用 MemAlign 將評判器與人工回饋對齊。

    若對齊 trace 少於 3 筆，會原樣回傳評判器。
    否則會使用 MemAlignOptimizer 從人工修正中學習評估原則，
    並回傳完成對齊的評判器。

    參數:
        skill_name: 要載入 trace 的技能名稱。
        judge: MLflow 評判器（由 make_judge 或類似方式建立）。
        reflection_lm: MemAlign reflection 步驟使用的 LLM。

    回傳:
        若有足夠 trace 則回傳對齊後的評判器，否則回傳原始評判器。
    """
    traces = load_alignment_traces(skill_name)
    if len(traces) < 3:
        if traces:
            logger.info(
                "Only %d alignment traces for %s (need >=3). Using base judge.",
                len(traces),
                skill_name,
            )
        return judge

    try:
        from mlflow.genai.judges.optimizers import MemAlignOptimizer

        optimizer = MemAlignOptimizer(reflection_lm=reflection_lm)
        aligned = judge.align(traces=traces, optimizer=optimizer)
        logger.info(
            "Aligned judge with %d traces for %s",
            len(traces),
            skill_name,
        )
        return aligned
    except ImportError:
        logger.warning("MemAlignOptimizer not available. Install mlflow-deepeval for alignment support.")
        return judge
    except Exception as e:
        logger.warning("MemAlign alignment failed for %s: %s", skill_name, e)
        return judge


def align_judges(
    skill_name: str,
    judges: dict[str, Any],
    reflection_lm: str = "openai:/gpt-4o-mini",
) -> dict[str, Any]:
    """使用 MemAlign 將多個評判器與人工回饋對齊。

    便利包裝函式，會對 dict 中的每個評判器呼叫 ``align_judge``。
    無法對齊的評判器（trace 不足）會原樣回傳。

    參數:
        skill_name: 要載入 trace 的技能名稱。
        judges: 對映評判器名稱到評判器實例的 dict
            （例如 ``{"correctness": cj, "completeness": cmj, "guideline_adherence": gj}``）。
        reflection_lm: MemAlign reflection 步驟使用的 LLM。

    回傳:
        鍵值不變的 dict；若可對齊則值為對齊後的評判器。
    """
    aligned: dict[str, Any] = {}
    for name, judge in judges.items():
        logger.info("Aligning judge '%s' for skill '%s'", name, skill_name)
        aligned[name] = align_judge(skill_name, judge, reflection_lm=reflection_lm)
    return aligned
