"""SkillBench 風格評估的二元斷言層。

將模式與事實檢查包裝為二元通過/失敗斷言，
呼應 SkillBench 類似 pytest 的二元做法。不使用模糊關鍵字
評分——每個斷言要麼通過，要麼失敗。
"""

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class AssertionResult:
    """單一二元斷言的結果。"""

    name: str
    passed: bool
    rationale: str
    assertion_type: str  # "pattern" | "fact"


def _run_pattern_assertions(response: str, expected_patterns: list) -> list[AssertionResult]:
    """對回應執行模式斷言。

    每個模式規格可以是純 regex 字串，或是包含
    ``pattern``、``min_count``、``max_count``、``description`` 鍵的 dict。
    """
    results = []
    for pattern_spec in expected_patterns:
        if isinstance(pattern_spec, str):
            pattern = pattern_spec
            min_count = 1
            max_count = None
            description = pattern[:40]
        else:
            pattern = pattern_spec["pattern"]
            min_count = pattern_spec.get("min_count", 1)
            max_count = pattern_spec.get("max_count", None)
            description = pattern_spec.get("description", pattern[:40])

        matches = len(re.findall(pattern, response, re.IGNORECASE))

        if max_count is not None:
            passed = min_count <= matches <= max_count
            rationale = f"Found {matches} matches (need {min_count}-{max_count})"
        else:
            passed = matches >= min_count
            rationale = f"Found {matches} matches (need >={min_count})"

        results.append(
            AssertionResult(
                name=f"pattern_{description}",
                passed=passed,
                rationale=rationale,
                assertion_type="pattern",
            )
        )
    return results


def _run_fact_assertions(response: str, expected_facts: list[str]) -> list[AssertionResult]:
    """對回應執行事實斷言。

    精確子字串比對（不區分大小寫）。不使用模糊關鍵字重疊。
    """
    response_lower = response.lower()
    results = []
    for fact in expected_facts:
        found = fact.lower() in response_lower
        results.append(
            AssertionResult(
                name=f"fact_{fact[:40]}",
                passed=found,
                rationale=f"{'Found' if found else 'Missing'}: {fact}",
                assertion_type="fact",
            )
        )
    return results


def run_all_assertions(response: str, expectations: dict[str, Any]) -> list[AssertionResult]:
    """執行所有模式 + 事實斷言，並回傳每個斷言的二元通過/失敗結果。

    參數:
        response: 要用來檢查斷言的文字。
        expectations: 可包含 ``expected_patterns`` 與 ``expected_facts`` 鍵的 dict。

    回傳:
        含有每個斷言二元通過/失敗結果的 AssertionResult 清單。
    """
    results: list[AssertionResult] = []

    patterns = expectations.get("expected_patterns", [])
    if patterns:
        results.extend(_run_pattern_assertions(response, patterns))

    facts = expectations.get("expected_facts", [])
    if facts:
        results.extend(_run_fact_assertions(response, facts))

    return results


def _classify_assertion(
    with_result: AssertionResult,
    without_result: AssertionResult,
) -> str:
    """藉由比較含技能與不含技能的結果來分類單一斷言。

    回傳下列其中之一：
        POSITIVE   — 不含技能時失敗，含技能時通過（技能有幫助）
        REGRESSION — 不含技能時通過，含技能時失敗（技能讓 Agent 混淆）
        NEEDS_SKILL — 含技能與不含技能都失敗（技能必須加入此內容）
        NEUTRAL    — 兩者結果相同（Agent 已經知道這點）
    """
    if with_result.passed and not without_result.passed:
        return "POSITIVE"
    elif not with_result.passed and without_result.passed:
        return "REGRESSION"
    elif not with_result.passed and not without_result.passed:
        return "NEEDS_SKILL"
    else:
        return "NEUTRAL"


def _extract_content(result: AssertionResult) -> str:
    """從斷言結果中擷取實際預期的內容。

    對於 facts，會移除 ``Missing: `` / ``Found: `` 前綴以取得原始
    事實文字。對於 patterns，則使用嵌入於斷言名稱中的描述
    （移除 ``pattern_`` 前綴）。
    """
    if result.assertion_type == "fact":
        for prefix in ("Missing: ", "Found: "):
            if result.rationale.startswith(prefix):
                return result.rationale[len(prefix) :]
        return result.rationale
    else:
        # 模式：名稱為 "pattern_{description}"，rationale 為符合次數
        return result.name.removeprefix("pattern_")


def summarize_failures(
    with_results: list[AssertionResult],
    without_results: list[AssertionResult],
) -> dict[str, str]:
    """根據斷言結果建立 GEPA 友善的診斷字串。

    只收集 NEEDS_SKILL 與 REGRESSION 斷言（略過 NEUTRAL/POSITIVE），
    並產生對應 GEPA 標準診斷鍵的結構化輸出。

    只會在回傳的 dict 中包含非空鍵，避免 GEPA 產生空的
    ``## Header`` 區段，浪費 Token 並讓 reflection LM 混淆。

    回傳:
        包含下列鍵子集的 dict：``Error``、``Regressions``。
        ``Error`` 會攜帶精簡的 NEEDS_SKILL/REGRESSION Token，供下游
        使用者（``_review_skillbench``、``build_skillbench_background``）解析。
        ``Regressions`` 則是精簡的自然語言摘要，僅在存在 regressions 時出現。
    """
    needs_skill: list[tuple[AssertionResult, AssertionResult]] = []
    regressions: list[tuple[AssertionResult, AssertionResult]] = []

    for w, wo in zip(with_results, without_results, strict=True):
        label = _classify_assertion(w, wo)
        if label == "NEEDS_SKILL":
            needs_skill.append((w, wo))
        elif label == "REGRESSION":
            regressions.append((w, wo))

    result: dict[str, str] = {}

    # Error：精簡斷言標籤（保留 NEEDS_SKILL/REGRESSION Token）
    error_lines: list[str] = []
    for w, _ in needs_skill:
        content = _extract_content(w)
        error_lines.append(f"NEEDS_SKILL: {w.assertion_type} — '{content}'")
    for w, _ in regressions:
        content = _extract_content(w)
        error_lines.append(f"REGRESSION: {w.assertion_type} — '{content}'")
    if error_lines:
        result["Error"] = "\n".join(error_lines)

    # Regressions：精簡自然語言（僅在非空時）
    if regressions:
        lines: list[str] = []
        for i, (w, _wo) in enumerate(regressions, 1):
            content = _extract_content(w)
            lines.append(f"{i}. '{content}' — passes without skill, fails with it")
        result["Regressions"] = "\n".join(lines)

    return result
