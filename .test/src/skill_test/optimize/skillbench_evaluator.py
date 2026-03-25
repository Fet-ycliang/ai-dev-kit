"""SkillBench 評估器：透過含技能 vs 不含技能比較來衡量技能效能。

透過在真實任務上衡量 Agent 在含技能與不含技能時的表現來評估技能。
使用三個聚焦的 MLflow 評判器（correctness、completeness、
guideline adherence）作為主要評分機制——每個評判器都提供
類別判決以及供 GEPA reflection LM 使用的豐富 rationale。

  Phase 1: 含技能  -- LLM 在 context 中包含 SKILL.md 產生回應
  Phase 2: 不含技能 -- LLM 在沒有技能的情況下產生回應（快取一次）
  Phase 3: 評判器 -- correctness + completeness（含技能+不含技能）、guideline_adherence（僅含技能），
           regression（當 delta < -0.05 時）
  Phase 4: 斷言 -- 決定性的事實/模式檢查（LLM 成本為 0）

評分權重：
  30% 效能差值（correctness_delta + completeness_delta 的平均）
  20% 品質綜合分數（含技能的 correctness + completeness + guideline_adherence 分數平均）
  15% 事實/模式覆蓋率（來自 assertions.py 的決定性斷言）
  10% 準則遵循率（實務作法的獨立權重）
   5% 結構（語法有效性）
  10% Token 效率（候選內容越小分數越高）
  10% 回歸懲罰（當 regression_judge 觸發時的明確懲罰）
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Callable

from mlflow.entities import Feedback

from ..scorers.universal import python_syntax, sql_syntax, no_hallucinated_apis
from .assertions import run_all_assertions, summarize_failures
from .judges import (
    JudgeFeedback,
    _safe_parse_score,
    create_correctness_judge,
    create_completeness_judge,
    create_guideline_adherence_judge,
    create_regression_judge,
    discover_skill_paths,
    run_judge_safe,
    completion_with_fallback,
)
from .utils import count_tokens

logger = logging.getLogger(__name__)


def _prompt_hash(prompt: str) -> str:
    """用於依 prompt 快取基準結果的穩定雜湊。"""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


class _RateLimiter:
    """供 LLM API 呼叫使用的執行緒安全 token-bucket rate limiter。"""

    def __init__(self, max_concurrent: int = 2, min_interval: float = 1.0):
        self._semaphore = threading.Semaphore(max_concurrent)
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._last_call: float = 0.0

    def acquire(self) -> None:
        self._semaphore.acquire()
        with self._lock:
            now = time.monotonic()
            wait = self._last_call + self._min_interval - now
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def release(self) -> None:
        self._semaphore.release()


# 模組層級的 rate limiter，由所有評估器實例共用。
# 可透過環境變數配置，以支援 rate limit 更嚴格的工作區。
_rate_limiter = _RateLimiter(
    max_concurrent=int(os.environ.get("GEPA_MAX_CONCURRENT_LLM", "4")),
    min_interval=float(os.environ.get("GEPA_MIN_LLM_INTERVAL", "0.2")),
)


def _completion_with_backoff(*, max_retries: int = 3, **kwargs) -> Any:
    """以 rate limiting 與 model fallback 呼叫 litellm.completion。

    使用集中式的 completion_with_fallback，其會處理：
    - 使用指數退避處理 rate limit 錯誤
    - 持續 rate limit 時的 model fallback chain
    - 已配置時的 AI Gateway 路由
    """
    _rate_limiter.acquire()
    try:
        return completion_with_fallback(max_retries=max_retries, **kwargs)
    finally:
        _rate_limiter.release()


def _run_structure_scorers(text: str) -> float:
    """對文字執行結構驗證評分器，回傳 0.0-1.0 的綜合分數。"""
    outputs = {"response": text}
    scores: list[float] = []
    for scorer_fn in [python_syntax, sql_syntax, no_hallucinated_apis]:
        try:
            result = scorer_fn(outputs=outputs)
            if isinstance(result, list):
                for fb in result:
                    if fb.value == "yes":
                        scores.append(1.0)
                    elif fb.value == "no":
                        scores.append(0.0)
            elif isinstance(result, Feedback):
                if result.value == "yes":
                    scores.append(1.0)
                elif result.value == "no":
                    scores.append(0.0)
        except Exception:
            pass
    return sum(scores) / len(scores) if scores else 1.0


def _effectiveness_score(verdict: str | float) -> float:
    """將效能判決轉換為用於加權的數值分數。"""
    if isinstance(verdict, (int, float)):
        return max(0.0, min(1.0, float(verdict)))
    v = str(verdict).strip().lower()
    if v == "improved":
        return 1.0
    elif v == "same":
        return 0.5
    elif v == "regressed":
        return 0.0
    # 回退：嘗試 bool 類型
    if v in ("yes", "true"):
        return 1.0
    if v in ("no", "false"):
        return 0.0
    return 0.5


class SkillBenchEvaluator:
    """使用三個聚焦評判器進行評分與診斷的 GEPA 相容評估器。

    使用 correctness、completeness 與 guideline adherence 評判器，
    並採用二元 ``Literal["yes", "no"]`` 回饋型別。
    產生可供 GEPA reflection LM 使用的拆解訊號。

    參數:
        gen_model: 用於產生回應的 LLM model。必填。
        original_token_counts: 原始成品的 Token 計數，用於效率評分。
        token_budget: 硬性 Token 上限；超出的候選內容會被懲罰。
        skill_guidelines: 從 ground_truth.yaml 去重後取得、供評判器使用的 guidelines。
        judge_model: 評判器使用的 LLM model。預設為 GEPA_JUDGE_LM 環境變數
            或 databricks/databricks-claude-sonnet-4-6。
    """

    def __init__(
        self,
        gen_model: str,
        original_token_counts: dict[str, int] | None = None,
        token_budget: int | None = None,
        skill_guidelines: list[str] | None = None,
        judge_model: str | None = None,
        tool_context: str | None = None,
        assessment_by_task: dict[str, list] | None = None,
    ):
        if not gen_model:
            raise ValueError("SkillBench evaluator requires a gen_model. Pass --gen-model or set GEPA_GEN_LM env var.")
        self.gen_model = gen_model
        self._baseline_response_cache: dict[str, str] = {}
        # 各評判器的基準快取（不含技能的回應在各次迭代中是穩定的）
        self._baseline_correctness_cache: dict[str, JudgeFeedback] = {}
        self._baseline_completeness_cache: dict[str, JudgeFeedback] = {}
        self._original_token_counts = original_token_counts or {}
        self._total_original_tokens = sum(self._original_token_counts.values())
        self._token_budget = token_budget
        self._tool_context = tool_context or ""
        self._assessment_by_task = assessment_by_task or {}

        # 以 (prompt_hash, candidate_hash) 為鍵快取含技能的評估結果
        # 避免當 GEPA 多次對
        # 相同候選內容-任務配對呼叫評估器時重複評估。
        self._with_skill_cache: dict[str, tuple[float, dict]] = {}

        # 探索 eval criteria 技能路徑（靜態骨幹 + 自適應層）
        skill_paths = discover_skill_paths()

        # 建立三個聚焦的評判器實例
        self._correctness_judge = create_correctness_judge(skill_paths=skill_paths, judge_model=judge_model)
        self._completeness_judge = create_completeness_judge(skill_paths=skill_paths, judge_model=judge_model)
        self._guideline_adherence_judge = create_guideline_adherence_judge(
            skill_paths=skill_paths, skill_guidelines=skill_guidelines, judge_model=judge_model
        )
        self._regression_judge = create_regression_judge(judge_model=judge_model)

    def _generate_response(self, prompt: str, skill_context: str | None = None) -> str:
        """在有或沒有技能 context 的情況下產生回應。"""
        messages = []
        if skill_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Use ONLY the following skill documentation to answer "
                        "the user's question. Do not use any other knowledge.\n\n"
                        f"{skill_context}"
                    ),
                }
            )
        messages.append({"role": "user", "content": prompt})

        resp = _completion_with_backoff(
            model=self.gen_model,
            messages=messages,
            temperature=0,
        )
        return resp.choices[0].message.content or ""

    def _get_baseline_response(self, prompt: str) -> str:
        """取得不含技能的基準回應；計算一次後快取。"""
        key = _prompt_hash(prompt)
        if key not in self._baseline_response_cache:
            response = self._generate_response(prompt, skill_context=None)
            self._baseline_response_cache[key] = response
        return self._baseline_response_cache[key]

    def __call__(
        self,
        candidate: dict[str, str],
        example: dict,
    ) -> tuple[float, dict]:
        """根據單一任務範例評估候選技能。

        GEPA 相容簽章：(candidate, example) -> (score, side_info)
        """
        skill_md = candidate.get("skill_md", "")

        # 檢查候選內容層級的快取
        prompt = example.get("input", "")
        candidate_hash = hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()[:16]
        cache_key = f"{_prompt_hash(prompt)}:{candidate_hash}"
        if cache_key in self._with_skill_cache:
            return self._with_skill_cache[cache_key]

        # 建立合併 context：技能 + 唯讀工具描述
        # 在技能優化期間，工具來自 self._tool_context（唯讀）。
        # 在工具優化期間，工具來自 candidate 的鍵（可優化）。
        tool_parts = []
        for key in sorted(candidate):
            if key.startswith("tools_"):
                tool_parts.append(candidate[key])

        full_context = skill_md
        if tool_parts:
            full_context += "\n\n## Available MCP Tools\n\n" + "\n\n".join(tool_parts)
        elif self._tool_context:
            full_context += "\n\n## Available MCP Tools\n\n" + self._tool_context

        # 解碼 expectations
        expectations: dict[str, Any] = {}
        expectations_json = example.get("additional_context", {}).get("expectations", "")
        if expectations_json:
            try:
                expectations = json.loads(expectations_json)
            except (json.JSONDecodeError, TypeError):
                pass

        if not prompt or not expectations:
            return 0.0, {"_error": "No prompt or expectations for this task"}

        # Phase 1：產生含技能回應
        with_response = self._generate_response(prompt, skill_context=full_context)

        # Phase 2：產生不含技能回應（已快取）
        without_response = self._get_baseline_response(prompt)

        # Phase 3：多評判器評分
        facts = expectations.get("expected_facts", [])
        patterns = expectations.get("expected_patterns", [])
        guidelines = expectations.get("guidelines", [])

        # 為評判器範本建立扁平字串——make_judge 只支援
        # 頂層的 {{ inputs }}、{{ outputs }}、{{ expectations }} 變數。
        facts_str = "\n".join(f"- {f}" for f in facts) if facts else "None specified"
        patterns_str = (
            "\n".join(
                f"- {p}" if isinstance(p, str) else f"- {p.get('description', p.get('pattern', ''))}" for p in patterns
            )
            if patterns
            else "None specified"
        )
        guidelines_str = "\n".join(f"- {g}" for g in guidelines) if guidelines else "None specified"

        expectations_text = (
            f"Expected facts:\n{facts_str}\n\nExpected patterns:\n{patterns_str}\n\nGuidelines:\n{guidelines_str}"
        )

        # make_judge 要求 expectations 為 dict，inputs/outputs 為 Any。
        expectations_dict = {"criteria": expectations_text}

        baseline_key = _prompt_hash(prompt)

        # --- Correctness 評判器：含技能 + 不含技能（不含技能已快取）---
        correctness_with_fb = run_judge_safe(
            self._correctness_judge,
            inputs=prompt,
            outputs=with_response,
            expectations=expectations_dict,
            name="correctness_with",
        )
        if baseline_key not in self._baseline_correctness_cache:
            self._baseline_correctness_cache[baseline_key] = run_judge_safe(
                self._correctness_judge,
                inputs=prompt,
                outputs=without_response,
                expectations=expectations_dict,
                name="correctness_without",
            )
        correctness_without_fb = self._baseline_correctness_cache[baseline_key]

        # --- Completeness 評判器：含技能 + 不含技能（不含技能已快取）---
        completeness_with_fb = run_judge_safe(
            self._completeness_judge,
            inputs=prompt,
            outputs=with_response,
            expectations=expectations_dict,
            name="completeness_with",
        )
        if baseline_key not in self._baseline_completeness_cache:
            self._baseline_completeness_cache[baseline_key] = run_judge_safe(
                self._completeness_judge,
                inputs=prompt,
                outputs=without_response,
                expectations=expectations_dict,
                name="completeness_without",
            )
        completeness_without_fb = self._baseline_completeness_cache[baseline_key]

        # --- 準則遵循評判器：僅含技能（不含技能沒有意義）---
        guideline_adherence_fb = run_judge_safe(
            self._guideline_adherence_judge,
            inputs=prompt,
            outputs=with_response,
            expectations=expectations_dict,
            name="guideline_adherence",
        )

        # 將類別判決轉換為 float 分數
        correctness_with = _safe_parse_score(correctness_with_fb.value)
        correctness_without = _safe_parse_score(correctness_without_fb.value)
        completeness_with = _safe_parse_score(completeness_with_fb.value)
        completeness_without = _safe_parse_score(completeness_without_fb.value)
        guideline_adherence_score = _safe_parse_score(guideline_adherence_fb.value)

        # 各維度的效能差值
        correctness_delta = correctness_with - correctness_without
        completeness_delta = completeness_with - completeness_without
        effectiveness_delta = (correctness_delta + completeness_delta) / 2.0

        # 品質綜合分數：三個含技能分數的平均
        quality_composite = (correctness_with + completeness_with + guideline_adherence_score) / 3.0

        # 推導效能判決
        if effectiveness_delta > 0.05:
            effectiveness_verdict = "improved"
        elif effectiveness_delta < -0.05:
            effectiveness_verdict = "regressed"
        else:
            effectiveness_verdict = "same"

        # --- Regression 評判器：僅在 delta < -0.05 時啟用 ---
        regression_penalty = 0.0
        regression_fb = None
        if effectiveness_delta < -0.05:
            comparison_input = (
                f"QUESTION:\n{prompt}\n\n"
                f"WITH-SKILL RESPONSE:\n{with_response}\n\n"
                f"WITHOUT-SKILL RESPONSE:\n{without_response}"
            )
            regression_fb = run_judge_safe(
                self._regression_judge,
                inputs=comparison_input,
                expectations=expectations_dict,
                name="regression",
            )
            # bool/yes → 1.0（發現 regression），no → 0.0
            reg_val = regression_fb.value
            if isinstance(reg_val, bool):
                regression_penalty = 1.0 if reg_val else 0.0
            elif isinstance(reg_val, str) and reg_val.strip().lower() in ("yes", "true"):
                regression_penalty = 1.0

        # Phase 4：決定性的事實/模式斷言（LLM 成本為 0）
        with_results = run_all_assertions(with_response, expectations)
        without_results = run_all_assertions(without_response, expectations)

        fact_results = [r for r in with_results if r.assertion_type == "fact"]
        pattern_results = [r for r in with_results if r.assertion_type == "pattern"]
        fact_score = sum(1 for r in fact_results if r.passed) / len(fact_results) if fact_results else 1.0
        pattern_score = sum(1 for r in pattern_results if r.passed) / len(pattern_results) if pattern_results else 1.0

        # 來自斷言比較的 GEPA 友善診斷
        failure_summary = summarize_failures(with_results, without_results)

        # 對技能本身做結構驗證
        structure = _run_structure_scorers(skill_md) if skill_md else 1.0

        # Token 效率評分
        total_candidate_tokens = sum(count_tokens(v) for v in candidate.values())

        if self._total_original_tokens > 0:
            ratio = total_candidate_tokens / self._total_original_tokens
            if ratio <= 1.0:
                efficiency = 1.0 + 0.15 * (1.0 - ratio)
            else:
                efficiency = max(0.0, 2.0 - ratio)

            if self._token_budget and total_candidate_tokens > self._token_budget:
                over_ratio = total_candidate_tokens / self._token_budget
                efficiency = min(efficiency, max(0.0, 2.0 - over_ratio))
        else:
            efficiency = 1.0

        # 使用新的多評判器權重計算加權最終分數
        fact_pattern = 0.5 * fact_score + 0.5 * pattern_score
        final_score = max(
            0.0,
            min(
                1.0,
                0.30 * effectiveness_delta
                + 0.20 * quality_composite
                + 0.15 * fact_pattern
                + 0.10 * guideline_adherence_score
                + 0.05 * structure
                + 0.10 * efficiency
                - 0.10 * regression_penalty,
            ),
        )

        # 以完整評判器 rationale 建立 side_info（不截斷！）
        reference_answer = example.get("answer", "")

        side_info: dict[str, Any] = {}

        # 任務 context
        if prompt:
            side_info["Task"] = prompt[:500]

        # 各維度評判器回饋——GEPA 會將每個視為獨立區段
        side_info["Judge_correctness_with"] = {
            "verdict": str(correctness_with_fb.value),
            "score": correctness_with,
            "rationale": correctness_with_fb.rationale,
        }
        side_info["Judge_correctness_without"] = {
            "verdict": str(correctness_without_fb.value),
            "score": correctness_without,
            "rationale": correctness_without_fb.rationale,
        }
        side_info["Judge_completeness_with"] = {
            "verdict": str(completeness_with_fb.value),
            "score": completeness_with,
            "rationale": completeness_with_fb.rationale,
        }
        side_info["Judge_completeness_without"] = {
            "verdict": str(completeness_without_fb.value),
            "score": completeness_without,
            "rationale": completeness_without_fb.rationale,
        }
        side_info["Judge_guideline_adherence"] = {
            "verdict": str(guideline_adherence_fb.value),
            "score": guideline_adherence_score,
            "rationale": guideline_adherence_fb.rationale,
        }

        # 各維度的效能差值
        side_info["Judge_effectiveness"] = {
            "verdict": effectiveness_verdict,
            "correctness_delta": correctness_delta,
            "completeness_delta": completeness_delta,
            "overall_delta": effectiveness_delta,
        }

        # Regression 分析（僅在偵測到 regression 時）
        if regression_fb and regression_penalty > 0:
            side_info["Regression_Analysis"] = {
                "rationale": regression_fb.rationale,
            }

        # 基於斷言的結構化回饋——GEPA 會將每個鍵渲染為 Markdown 標題
        side_info["Missing_Facts"] = [r.rationale for r in fact_results if not r.passed]
        side_info["Missing_Patterns"] = [r.rationale for r in pattern_results if not r.passed]
        side_info["Passed_Facts"] = [r.rationale for r in fact_results if r.passed]
        side_info["Passed_Patterns"] = [r.rationale for r in pattern_results if r.passed]

        # skill_md_specific_info——僅在反思技能元件時顯示
        if failure_summary.get("Error") or failure_summary.get("Regressions"):
            side_info["skill_md_specific_info"] = {
                "Assertion_Diagnostics": failure_summary.get("Error", ""),
                "Regressions": failure_summary.get("Regressions", ""),
            }

        # 供 GEPA reflection 使用的 Expected vs Actual
        if reference_answer:
            side_info["Expected"] = reference_answer[:2000]
        if with_response:
            side_info["Actual"] = with_response[:2000]

        # 分數明細（scores dict 會送入 GEPA 的 Pareto frontier）
        side_info["scores"] = {
            "correctness_with": correctness_with,
            "correctness_without": correctness_without,
            "completeness_with": completeness_with,
            "completeness_without": completeness_without,
            "guideline_adherence": guideline_adherence_score,
            "quality_composite": quality_composite,
            "correctness_delta": correctness_delta,
            "completeness_delta": completeness_delta,
            "skill_effectiveness": effectiveness_delta,
            "regression_penalty": regression_penalty,
            "fact_coverage": fact_score,
            "pattern_adherence": pattern_score,
            "structure": structure,
            "token_efficiency": efficiency,
            "final": final_score,
        }

        # 供 GEPA Pareto 追蹤使用的 Token 計數
        side_info["token_counts"] = {
            "candidate_total": total_candidate_tokens,
            "original_total": self._total_original_tokens,
        }
        if self._token_budget:
            side_info["token_counts"]["budget"] = self._token_budget

        # 注入來自 MLflow traces 的已匹配真實世界 assessments
        if self._assessment_by_task:
            task_id = example.get("additional_context", {}).get("task_id", "")
            matched = self._assessment_by_task.get(task_id) or self._assessment_by_task.get(_prompt_hash(prompt), [])
            if matched:
                side_info["real_world_assessments"] = [
                    {"name": a.name, "value": a.value, "rationale": a.rationale} for a in matched
                ]

        # 根據斷言 + 評判器判決推導診斷標籤
        # 找出最弱維度，以提供更具針對性的 GEPA 回饋
        weakest_dim = "correctness" if correctness_with <= completeness_with else "completeness"
        weakest_score = min(correctness_with, completeness_with)

        if failure_summary.get("Error"):
            # 斷言偵測到特定的 NEEDS_SKILL/REGRESSION 項目
            side_info["Error"] = failure_summary["Error"]
        elif effectiveness_delta < -0.05:
            # 各維度 regression 資訊
            regressed_dims = []
            if correctness_delta < -0.05:
                regressed_dims.append(f"correctness({correctness_delta:+.2f})")
            if completeness_delta < -0.05:
                regressed_dims.append(f"completeness({completeness_delta:+.2f})")
            dims_str = ", ".join(regressed_dims) if regressed_dims else f"overall({effectiveness_delta:+.2f})"
            side_info["Error"] = (
                f"REGRESSION: {dims_str}. "
                f"correctness: {correctness_with:.2f} (was {correctness_without:.2f}), "
                f"completeness: {completeness_with:.2f} (was {completeness_without:.2f})"
            )
        elif weakest_score < 0.6:
            side_info["Error"] = (
                f"NEEDS_SKILL: weakest dimension is {weakest_dim}={weakest_score:.2f}. "
                f"correctness={correctness_with:.2f}, completeness={completeness_with:.2f}, "
                f"guideline_adherence={guideline_adherence_score:.2f}"
            )

        # 存入候選內容層級的快取
        self._with_skill_cache[cache_key] = (final_score, side_info)

        return final_score, side_info


def _collect_skill_guidelines(skill_name: str) -> list[str]:
    """從 ground_truth.yaml 與 manifest.yaml 收集並去重 guidelines。"""
    from pathlib import Path
    import yaml

    seen: set[str] = set()
    guidelines: list[str] = []

    # 從 ground_truth.yaml 測試案例收集
    gt_path = Path(".test/skills") / skill_name / "ground_truth.yaml"
    if gt_path.exists():
        try:
            with open(gt_path) as f:
                data = yaml.safe_load(f) or {}
            for tc in data.get("test_cases", []):
                for g in tc.get("expectations", {}).get("guidelines", []):
                    g_norm = g.strip()
                    if g_norm and g_norm not in seen:
                        seen.add(g_norm)
                        guidelines.append(g_norm)
        except Exception:
            pass

    # 從 manifest.yaml 的 default_guidelines 收集（包含 [FOCUS] guidelines）
    manifest_path = Path(".test/skills") / skill_name / "manifest.yaml"
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = yaml.safe_load(f) or {}
            for g in manifest.get("scorers", {}).get("default_guidelines", []):
                g_norm = g.strip()
                if g_norm and g_norm not in seen:
                    seen.add(g_norm)
                    guidelines.append(g_norm)
        except Exception:
            pass

    return guidelines


def create_skillbench_evaluator(
    skill_name: str,
    gen_model: str,
    original_token_counts: dict[str, int] | None = None,
    token_budget: int | None = None,
    judge_model: str | None = None,
    tool_context: str | None = None,
    assessment_by_task: dict[str, list] | None = None,
) -> Callable:
    """建立 SkillBench 風格評估器的工廠函式。

    回傳一個與 GEPA 相容的 callable：(candidate, example) -> (score, side_info)

    評判器一律啟用——它們是主要的評分機制。
    ground_truth.yaml 中的 guidelines 會納入 quality judge。

    參數:
        skill_name: 正在評估的技能名稱。
        gen_model: 用於產生回應的 LLM model。必填。
        original_token_counts: 原始成品的 Token 計數，用於效率評分。
        token_budget: 硬性 Token 上限；超出的候選內容會被懲罰。
        judge_model: 評判器使用的 LLM model。預設為 GEPA_JUDGE_LM 環境變數
            或 databricks/databricks-claude-sonnet-4-6。
        tool_context: 納入產生 context 但不會被優化的唯讀工具描述。
            在技能優化期間使用，讓工具能提供 context，
            但不會成為 GEPA 元件。
    """
    skill_guidelines = _collect_skill_guidelines(skill_name)
    if skill_guidelines:
        logger.info(
            "Loaded %d domain guidelines for quality judge",
            len(skill_guidelines),
        )

    from .judges import DEFAULT_JUDGE_LM

    effective_judge_model = judge_model or DEFAULT_JUDGE_LM
    logger.info("Judge model: %s", effective_judge_model)

    return SkillBenchEvaluator(
        gen_model=gen_model,
        original_token_counts=original_token_counts,
        token_budget=token_budget,
        skill_guidelines=skill_guidelines,
        judge_model=judge_model,
        tool_context=tool_context,
        assessment_by_task=assessment_by_task,
    )


def build_skillbench_background(
    skill_name: str,
    original_token_count: int,
    component_names: list[str] | None = None,
    baseline_scores: dict[str, float] | None = None,
    baseline_side_info: dict[str, dict] | None = None,
    token_budget: int | None = None,
    assessment_summary: str | None = None,
    focus_areas: list[str] | None = None,
) -> str:
    """為 SkillBench 優化建立精簡的 GEPA reflection context。

    保持簡短，讓 GEPA 的 reflection LM 能把 context 用在每個範例的
    診斷內容（評判器 rationale），而不是方法論。
    """
    baseline_desc = ""
    if baseline_scores:
        mean_score = sum(baseline_scores.values()) / len(baseline_scores)
        baseline_desc = f"\nBASELINE: mean {mean_score:.3f} across {len(baseline_scores)} tasks."

        if baseline_side_info:
            needs_skill_ids = []
            regression_ids = []
            for tid, info in baseline_side_info.items():
                error = info.get("Error", "")
                if "NEEDS_SKILL" in error:
                    needs_skill_ids.append(tid)
                if "REGRESSION" in error:
                    regression_ids.append(tid)
            if needs_skill_ids:
                baseline_desc += f"\n  NEEDS_SKILL ({len(needs_skill_ids)} tasks): {', '.join(needs_skill_ids[:5])}"
            if regression_ids:
                baseline_desc += f"\n  REGRESSION ({len(regression_ids)} tasks): {', '.join(regression_ids[:5])}"

    components_desc = ""
    if component_names and any(c.startswith("tools_") for c in component_names):
        tool_modules = [c.replace("tools_", "") for c in component_names if c.startswith("tools_")]
        components_desc = (
            f"\nAlso optimizing MCP tool descriptions for: {', '.join(tool_modules)}. "
            "Keep docstrings accurate and concise — every token counts toward the budget."
        )

    token_desc = (
        f"\nTOKEN EFFICIENCY (15% of score): Current artifacts total {original_token_count:,} tokens. "
        "Smaller candidates score HIGHER. Be ruthlessly concise."
    )
    if token_budget:
        token_desc += f"\nTOKEN BUDGET: {token_budget:,} tokens. Candidates exceeding this are heavily penalized."

    assessment_desc = ""
    if assessment_summary:
        assessment_desc = f"\n\n{assessment_summary}"

    focus_desc = ""
    if focus_areas:
        focus_items = "\n".join(f"  - {f}" for f in focus_areas)
        focus_desc = (
            f"\n\nUSER FOCUS PRIORITIES:\n{focus_items}\n"
            "These are high-priority areas the user wants the skill to emphasize. "
            "Weight these heavily in your optimization decisions."
        )

    return (
        f"You are refining SKILL.md for '{skill_name}'.\n"
        "The skill is scored by THREE focused MLflow judges:\n"
        "  1. CORRECTNESS — facts, API references, code syntax accuracy\n"
        "  2. COMPLETENESS — all parts addressed, all expected info present\n"
        "  3. GUIDELINE ADHERENCE — Databricks-specific patterns and practices\n"
        "Each judge returns 'excellent', 'acceptable', or 'poor' with rationale.\n\n"
        "Judge rationale in side_info explains exactly WHAT failed and WHY per dimension.\n"
        "Use Judge_correctness_with/without for accuracy feedback.\n"
        "Use Judge_completeness_with/without for coverage feedback.\n"
        "Use Judge_guideline_adherence for pattern compliance feedback.\n"
        "Use Judge_effectiveness for per-dimension deltas (correctness_delta, completeness_delta).\n"
        "Missing_Facts and Missing_Patterns show exact pass/fail for each expected assertion.\n"
        "Passed_Facts and Passed_Patterns show what the skill already covers.\n"
        "Focus on: specific API syntax, version requirements, non-obvious patterns.\n"
        "Do NOT add generic knowledge the agent already has."
        f"{baseline_desc}"
        f"{components_desc}"
        f"{token_desc}"
        f"{assessment_desc}"
        f"{focus_desc}"
    )
