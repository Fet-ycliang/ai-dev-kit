"""ASI 診斷：將 MLflow Feedback 轉換為 optimize_anything SideInfo。

精簡轉接層，會將評判器 rationale 完整傳遞給 GEPA 的 reflection LM，
不做截斷。關鍵修正是：GEPA 的 reflection LM 會取得來自評判器的
完整診斷文字，而不是被截斷的片段。

另外也提供 ``feedback_to_score()``，以維持與測試的向後相容性。
"""

from __future__ import annotations

from typing import Any

from mlflow.entities import Feedback


def feedback_to_score(feedback: Feedback) -> float | None:
    """將單一 MLflow Feedback 轉換為數值分數。

    對應規則：
        "yes" -> 1.0
        "no"  -> 0.0
        "skip" -> None（不納入評分）
        numeric -> float(value)
    """
    value = feedback.value
    if value == "yes":
        return 1.0
    elif value == "no":
        return 0.0
    elif value == "skip":
        return None
    else:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def feedback_to_asi(feedbacks: list[Feedback]) -> tuple[float, dict[str, Any]]:
    """將 MLflow Feedback 物件轉換為 optimize_anything 的 (score, SideInfo)。

    會計算未略過 feedback 的平均分數，並建立一個
    含完整 rationale（不截斷）的 SideInfo dict。
    """
    scores = []
    side_info: dict[str, Any] = {}

    for fb in feedbacks:
        score = feedback_to_score(fb)
        name = fb.name or "unnamed"

        if score is None:
            side_info[name] = {
                "score": None,
                "value": fb.value,
                "rationale": fb.rationale or "",
                "status": "skipped",
            }
            continue

        scores.append(score)
        side_info[name] = {
            "score": score,
            "value": fb.value,
            "rationale": fb.rationale or "",
            "status": "pass" if score >= 0.5 else "fail",
        }

    composite = sum(scores) / len(scores) if scores else 0.0

    side_info["_summary"] = {
        "composite_score": composite,
        "total_scorers": len(feedbacks),
        "scored": len(scores),
        "skipped": len(feedbacks) - len(scores),
        "passed": sum(1 for s in scores if s >= 0.5),
        "failed": sum(1 for s in scores if s < 0.5),
    }

    return composite, side_info
