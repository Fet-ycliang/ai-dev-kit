"""用於技能評估的 MLflow 評判器工廠。

聚焦的單一問題評判器，每個只會進行 1 次 LLM 呼叫：

    correctness_judge         — 回應在事實與技術上是否正確？
    completeness_judge        — 回應是否完整處理了問題？
    guideline_adherence_judge — 回應是否遵循 Databricks 慣例？
    regression_judge          — 技能是否傷害了回應？

每個評判器都使用二元 ``Literal["yes", "no"]`` 回饋，以產生明確判決
（Anthropic 最佳實務：「兩位領域專家會得到相同判決」）。
分數會透過 ``_safe_parse_score`` 轉換為 float。

eval criteria 會透過 ``make_judge()`` 上的 ``skills=`` 參數按需載入
（MLflow PR #21725）。當 ``skills=`` 尚未受支援時，評判器會在沒有
criteria 的情況下運作——決定性評分器與斷言會提供靜態骨幹。

評判器 model 解析（優先順序由高到低）：
    1. 傳給工廠函式的明確 ``judge_model`` 引數
    2. ``GEPA_JUDGE_LM`` 環境變數
    3. ``databricks:/databricks-claude-sonnet-4-6``（預設）

model 回退：
    遇到 rate limit 錯誤（REQUEST_LIMIT_EXCEEDED）時，會自動以
    fallback models 重試。可透過 ``GEPA_FALLBACK_MODELS`` 環境變數（逗號分隔）
    配置，或使用內建的 Databricks fallback chain。

AI Gateway 支援：
    設定 ``DATABRICKS_AI_GATEWAY_URL`` 以透過 Databricks AI Gateway 路由呼叫。
    範例：https://1444828305810485.ai-gateway.cloud.databricks.com/mlflow/v1
    可與標準 serving endpoint 方法一同使用。
"""

from __future__ import annotations

import concurrent.futures
import inspect
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from mlflow.genai.judges import make_judge

logger = logging.getLogger(__name__)

DEFAULT_JUDGE_LM = os.environ.get("GEPA_JUDGE_LM", "databricks:/databricks-claude-sonnet-4-6")

# ---------------------------------------------------------------------------
# rate limit 錯誤用的 fallback model chain
# ---------------------------------------------------------------------------

_DEFAULT_FALLBACK_MODELS = [
    "databricks/databricks-gpt-5-2",
    "databricks/databricks-gemini-3-1-pro",
    "databricks/databricks-claude-opus-4-5",
    "databricks/databricks-gpt-5",
    "databricks/databricks-claude-sonnet-4-6",
    "databricks/databricks-claude-sonnet-4-5",
]


def _get_fallback_models() -> list[str]:
    """從環境變數或預設值取得 fallback model chain。"""
    custom = os.environ.get("GEPA_FALLBACK_MODELS", "")
    if custom.strip():
        return [m.strip() for m in custom.split(",") if m.strip()]
    return list(_DEFAULT_FALLBACK_MODELS)


def _is_rate_limit_error(exc: Exception) -> bool:
    """檢查例外是否為 rate limit / request limit exceeded 錯誤。"""
    msg = str(exc).lower()
    return any(
        phrase in msg
        for phrase in [
            "rate_limit",
            "rate limit",
            "request_limit_exceeded",
            "request limit exceeded",
            "too many requests",
            "429",
            "token.*per.*minute",
        ]
    )


def _is_workspace_error(exc: Exception) -> bool:
    """偵測工作區層級錯誤，此時重試或回退都沒有意義。

    會攔截 403/IP ACL 封鎖、驗證失敗，以及表示
    整個工作區無法連線的網路錯誤——而不只是單一 model 的 rate limit。
    """
    msg = str(exc).lower()
    return any(
        phrase in msg
        for phrase in [
            "403",
            "forbidden",
            "ip access list",
            "ip acl",
            "not on the ip access list",
            "unauthorized",
            "401",
            "authentication failed",
            "invalid token",
            "could not resolve host",
            "connection refused",
            "connection error",
            "network is unreachable",
            "name or service not known",
            "no such host",
            "token refresh",
        ]
    )


# ---------------------------------------------------------------------------
# 全域 LLM 呼叫預算
# ---------------------------------------------------------------------------


class _LLMCallBudget:
    """對 LLM API 呼叫施加全域上限的執行緒安全計數器。

    可透過 GEPA_MAX_LLM_CALLS 環境變數配置。未設定或為 0 時，
    預算不限。
    """

    def __init__(self):
        import threading as _threading

        self._lock = _threading.Lock()
        self._count = 0
        max_str = os.environ.get("GEPA_MAX_LLM_CALLS", "0")
        try:
            self._max = int(max_str)
        except ValueError:
            self._max = 0

    @property
    def max_calls(self) -> int:
        return self._max

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def acquire(self) -> bool:
        """遞增計數器。若預算耗盡則回傳 False。"""
        with self._lock:
            if self._max > 0 and self._count >= self._max:
                return False
            self._count += 1
            return True

    def exhausted(self) -> bool:
        with self._lock:
            return self._max > 0 and self._count >= self._max


_llm_budget = _LLMCallBudget()


# ---------------------------------------------------------------------------
# AI Gateway 支援
# ---------------------------------------------------------------------------


def _get_gateway_base_url() -> str | None:
    """若已配置則回傳 AI Gateway base URL，否則回傳 None。

    會在呼叫時（而非 import 時）讀取 os.environ，讓
    runner.py 早期載入的環境變數能在建立評判器前生效。

    會移除使用者可能誤加的常見 API path 後綴（例如 ``/chat/completions``）——
    litellm 會自行將路徑附加到 base URL。
    """
    url = os.environ.get("DATABRICKS_AI_GATEWAY_URL", "").strip()
    if not url:
        return None
    url = url.rstrip("/")
    # 移除使用者可能誤加的 API path 後綴
    for suffix in ("/chat/completions", "/completions", "/embeddings"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


def _to_litellm_model(model: str) -> tuple[str, str | None, str | None]:
    """將 model 字串轉換為供 completion 呼叫使用的 (litellm_model, base_url, api_key)。

    若已配置 AI Gateway，且 model 是 databricks/ model，則會
    透過 gateway 作為與 OpenAI 相容的 endpoint 進行路由。litellm 中的 OpenAI
    provider 不會自動讀取 ``DATABRICKS_TOKEN``，因此我們會明確
    將它作為 ``api_key`` 傳入。

    回傳:
        (model_string, base_url_or_None, api_key_or_None)
    """
    gateway = _get_gateway_base_url()
    if gateway and model.startswith("databricks/"):
        # 透過 AI Gateway 以 OpenAI 相容 endpoint 路由
        endpoint_name = model.split("/", 1)[1]
        api_key = os.environ.get("DATABRICKS_TOKEN") or os.environ.get("DATABRICKS_API_KEY", "")
        return f"openai/{endpoint_name}", gateway, api_key or None
    return model, None, None


# ---------------------------------------------------------------------------
# URI 轉換
# ---------------------------------------------------------------------------


def _to_judge_uri(model: str) -> str:
    """將 litellm 風格的 model 字串轉換為 MLflow 評判器 URI 格式。

    litellm 使用 ``provider/model``（例如 ``databricks/databricks-claude-sonnet-4-6``）。
    MLflow 評判器使用 ``provider:/model``（例如 ``databricks:/databricks-claude-sonnet-4-6``）。
    """
    if ":/" in model:
        return model
    if "/" in model:
        provider, name = model.split("/", 1)
        return f"{provider}:/{name}"
    return model


def _judge_inference_params() -> dict[str, Any] | None:
    """若已配置 AI Gateway，則為 make_judge 建立 inference_params。"""
    gateway = _get_gateway_base_url()
    if gateway:
        api_key = os.environ.get("DATABRICKS_TOKEN") or os.environ.get("DATABRICKS_API_KEY", "")
        params: dict[str, Any] = {"base_url": gateway}
        if api_key:
            params["api_key"] = api_key
        return params
    return None


def _to_judge_model_and_params(model: str) -> tuple[str, dict[str, Any] | None]:
    """將 model 字串轉換為供 make_judge 使用的 (judge_uri, inference_params)。

    若已配置 AI Gateway，則會使用 ``openai:/endpoint-name``，並讓
    ``inference_params.base_url`` 指向 gateway。否則
    使用標準 ``provider:/model`` 格式。
    """
    gateway = _get_gateway_base_url()
    if gateway and model.startswith(("databricks/", "databricks:/")):
        # 擷取 endpoint 名稱
        if ":/" in model:
            endpoint_name = model.split(":/", 1)[1]
        else:
            endpoint_name = model.split("/", 1)[1]
        api_key = os.environ.get("DATABRICKS_TOKEN") or os.environ.get("DATABRICKS_API_KEY", "")
        params: dict[str, Any] = {"base_url": gateway}
        if api_key:
            params["api_key"] = api_key
        return f"openai:/{endpoint_name}", params
    return _to_judge_uri(model), _judge_inference_params()


# ---------------------------------------------------------------------------
# 使用 fallback 的 completion
# ---------------------------------------------------------------------------


def completion_with_fallback(*, model: str, max_retries: int = 3, **kwargs) -> Any:
    """在 rate limit 錯誤時，以 model fallback 呼叫 litellm.completion。

    會先嘗試主要 model。遇到 rate limit 錯誤時，會輪流使用
    fallback chain。每個 model 在切換到下一個之前都會以
    指數退避重試 ``max_retries`` 次。

    工作區層級錯誤（403/IP ACL/驗證）會立即拋出——
    fallback models 會打到相同被封鎖的工作區，因此同樣會失敗。

    會遵守全域 LLM 呼叫預算（``GEPA_MAX_LLM_CALLS``）。

    也支援 AI Gateway：若設定了 DATABRICKS_AI_GATEWAY_URL，
    databricks/ models 會透過 gateway 路由。
    """
    import litellm

    if not _llm_budget.acquire():
        raise RuntimeError(
            f"GEPA LLM call budget exhausted ({_llm_budget.max_calls} calls). "
            "Set GEPA_MAX_LLM_CALLS to increase or unset to disable."
        )

    models_to_try = [model] + [m for m in _get_fallback_models() if m != model]

    last_err: Exception | None = None
    for model_str in models_to_try:
        litellm_model, base_url, api_key = _to_litellm_model(model_str)

        call_kwargs = dict(kwargs)
        call_kwargs["model"] = litellm_model
        if base_url:
            call_kwargs["base_url"] = base_url
        if api_key:
            call_kwargs["api_key"] = api_key

        for attempt in range(max_retries):
            if attempt > 0:
                delay = min(2**attempt, 30)
                time.sleep(delay)
            try:
                return litellm.completion(**call_kwargs)
            except Exception as e:
                last_err = e
                # 工作區層級錯誤：快速失敗，不進行 fallback
                if _is_workspace_error(e):
                    logger.error(
                        "Workspace error (fail-fast): %s — not trying fallback models",
                        e,
                    )
                    raise
                if _is_rate_limit_error(e):
                    if attempt == max_retries - 1:
                        logger.warning(
                            "Model '%s' rate limited after %d attempts, trying next fallback",
                            model_str,
                            max_retries,
                        )
                    continue
                # 非 rate-limit 錯誤：不要重試，改試下一個 model
                logger.warning("Model '%s' failed (non-rate-limit): %s", model_str, e)
                break

    raise last_err  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 資料型別
# ---------------------------------------------------------------------------


@dataclass
class JudgeFeedback:
    """來自評判器呼叫的結構化回饋。"""

    value: float | str
    rationale: str
    name: str


def _safe_parse_score(raw_value: Any) -> float:
    """將評判器輸出轉換為 [0.0, 1.0] 範圍內的 float 分數。

    可處理：bool、"yes"/"no"、numeric、float-as-string。
    """
    if isinstance(raw_value, (int, float)):
        return max(0.0, min(1.0, float(raw_value)))
    if isinstance(raw_value, bool):
        return 1.0 if raw_value else 0.0
    if isinstance(raw_value, str):
        low = raw_value.strip().lower()
        if low == "yes":
            return 1.0
        if low == "no":
            return 0.0
        try:
            return max(0.0, min(1.0, float(low)))
        except ValueError:
            pass
    return 0.0


# ---------------------------------------------------------------------------
# 技能探索（靜態骨幹 + 來自 Issue #21255 的自適應層）
# ---------------------------------------------------------------------------


def discover_skill_paths(criteria_dir: str = ".test/eval-criteria", tool_modules: list[str] | None = None) -> list[str]:
    """回傳技能目錄路徑，可選擇依 applies_to metadata 篩選。

    靜態骨幹：``applies_to`` 為空的 criteria 一律納入。
    自適應層：只有在符合 ``tool_modules`` 時，才納入具有 ``applies_to`` 的 criteria。

    這些路徑會傳入 ``make_judge(skills=[...])``，當原生
    MLflow ``skills=`` 參數可用時使用（PR #21725）。
    """
    base = Path(criteria_dir)
    if not base.is_dir():
        return []
    paths = []
    for d in sorted(base.iterdir()):
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue
        if tool_modules:
            try:
                content = (d / "SKILL.md").read_text(encoding="utf-8")
                parts = content.split("---")
                if len(parts) >= 3:
                    fm = yaml.safe_load(parts[1]) or {}
                    applies_to = fm.get("metadata", {}).get("applies_to", [])
                    if applies_to and not any(m in applies_to for m in tool_modules):
                        continue
            except Exception:
                pass
        paths.append(str(d))
    if paths:
        logger.info("Discovered %d eval criteria skills: %s", len(paths), ", ".join(Path(p).name for p in paths))
        try:
            from .eval_criteria import SkillSet
            from .judge_tools import register_skill_tools

            register_skill_tools(SkillSet(paths))
        except Exception as exc:
            logger.debug("Could not register skill tools: %s", exc)
    return paths


def _make_judge_with_skills(
    *,
    name: str,
    instructions: str,
    model: str,
    feedback_value_type: Any,
    inference_params: dict[str, Any] | None = None,
    skill_paths: list[str] | None = None,
) -> Any:
    """建立評判器；若已安裝的 MLflow 支援，則傳入 skills=。

    向前相容：當 MLflow 取得 ``skills=`` 支援（PR #21725）後，
    eval criteria 將由評判器按需載入。在此之前，
    評判器會在沒有 criteria 的情況下運作，僅依賴指令本身。
    """
    kwargs: dict[str, Any] = {
        "name": name,
        "instructions": instructions,
        "model": model,
        "feedback_value_type": feedback_value_type,
    }
    if inference_params:
        kwargs["inference_params"] = inference_params

    # 若 make_judge 支援則傳入 skills=（原生路徑，PR #21725）
    if skill_paths:
        if "skills" in inspect.signature(make_judge).parameters:
            kwargs["skills"] = skill_paths
        else:
            # 針對不支援 skills= 的 MLflow 版本進行本地注入
            from .eval_criteria import SkillSet

            skill_set = SkillSet(skill_paths)
            criteria_block = skill_set.to_prompt_inline()
            if criteria_block:
                kwargs["instructions"] = criteria_block + "\n\n" + instructions

    return make_judge(**kwargs)


# ---------------------------------------------------------------------------
# Correctness 評判器——事實、API 參照、程式碼語法正確性（1 次 LLM 呼叫）
# ---------------------------------------------------------------------------

_CORRECTNESS_INSTRUCTIONS = """\
Is the response factually and technically correct?

Check:
- API names exist and are current (not deprecated)
- Code syntax is valid and runnable
- Function parameters and return types are correct
- No hallucinated features or invented APIs

{{ expectations }}

Question: {{ inputs }}
Response: {{ outputs }}

Return "yes" if correct, "no" if it contains significant factual errors.
"""


def create_correctness_judge(
    skill_paths: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """建立聚焦的 correctness 評判器，使用二元 yes/no 回饋。

    使用 ``{{ inputs }}/{{ outputs }}``（欄位式）——1 次 LLM 呼叫，沒有
    agentic tool-calling loop。
    """
    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return _make_judge_with_skills(
        name="correctness",
        instructions=_CORRECTNESS_INSTRUCTIONS,
        model=model_uri,
        feedback_value_type=Literal["yes", "no"],
        inference_params=inference_params,
        skill_paths=skill_paths,
    )


# ---------------------------------------------------------------------------
# Completeness 評判器——涵蓋所有部分、包含預期資訊（1 次 LLM 呼叫）
# ---------------------------------------------------------------------------

_COMPLETENESS_INSTRUCTIONS = """\
Does the response fully address the question?

Check:
- All parts of the question are answered
- Expected facts are present
- Expected code patterns are demonstrated
- Response is detailed enough to be actionable

{{ expectations }}

Question: {{ inputs }}
Response: {{ outputs }}

Return "yes" if complete, "no" if significant parts are missing.
"""


def create_completeness_judge(
    skill_paths: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """建立聚焦的 completeness 評判器，使用二元 yes/no 回饋。

    使用 ``{{ inputs }}/{{ outputs }}``（欄位式）——1 次 LLM 呼叫，沒有
    agentic tool-calling loop。
    """
    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return _make_judge_with_skills(
        name="completeness",
        instructions=_COMPLETENESS_INSTRUCTIONS,
        model=model_uri,
        feedback_value_type=Literal["yes", "no"],
        inference_params=inference_params,
        skill_paths=skill_paths,
    )


# ---------------------------------------------------------------------------
# 準則遵循評判器——Databricks 模式與實務（1 次 LLM 呼叫）
# ---------------------------------------------------------------------------

_GUIDELINE_ADHERENCE_INSTRUCTIONS = """\
Does the response follow Databricks conventions and best practices?

Check:
- Follows expected code patterns and conventions
- Uses recommended Databricks APIs and workflows
- Adheres to the specific guidelines listed below

{{ expectations }}

Question: {{ inputs }}
Response: {{ outputs }}

Return "yes" if guidelines are followed, "no" if important guidelines are violated.
"""


def create_guideline_adherence_judge(
    skill_paths: list[str] | None = None,
    skill_guidelines: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """建立聚焦的 guideline adherence 評判器，使用二元 yes/no 回饋。

    會接收所有 guidelines（default_guidelines + 每個測試的 guidelines +
    來自 ``--focus`` 的 [FOCUS] guidelines），讓聚焦區域可直接評估。
    """
    instructions = _GUIDELINE_ADHERENCE_INSTRUCTIONS
    if skill_guidelines:
        principles = "\n".join(f"- {g}" for g in skill_guidelines)
        instructions += f"\n\n## Required Guidelines\n{principles}\n"

    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return _make_judge_with_skills(
        name="guideline-adherence",
        instructions=instructions,
        model=model_uri,
        feedback_value_type=Literal["yes", "no"],
        inference_params=inference_params,
        skill_paths=skill_paths,
    )


# ---------------------------------------------------------------------------
# Regression 評判器——識別技能如何傷害回應（1 次 LLM 呼叫）
# ---------------------------------------------------------------------------

_REGRESSION_INSTRUCTIONS = """\
You are a regression detector for Databricks skill documents. Your job is
to identify specific ways that a skill document HARMS agent responses.

The inputs contain three fields separated by markers:
- QUESTION: the user's question
- WITH-SKILL RESPONSE: generated with the skill document in context
- WITHOUT-SKILL RESPONSE: generated without any skill document

## Input

{{ inputs }}

## Instructions

Identify specific regressions introduced by the skill. Return "yes" if
regressions are found, "no" if the skill is harmless.

Common regression patterns:
1. **Deprecated APIs** — skill teaches old APIs the model already uses correctly
2. **Verbosity** — skill adds noise that confuses the model
3. **Contradicting correct knowledge** — model was right, skill made it wrong
4. **Wrong examples** — skill's code examples have errors the model copies
5. **Over-specification** — skill's rigid patterns prevent correct alternatives

For each regression found, explain:
- WHAT specific content in the skill caused the regression
- WHY it made the response worse
- WHAT to remove or change in the skill to fix it
"""


def create_regression_judge(judge_model: str | None = None) -> Any:
    """建立 regression 偵測評判器。

    參數:
        judge_model: 評判器使用的 LLM model。預設為 GEPA_JUDGE_LM 環境變數，
            或 databricks/databricks-claude-sonnet-4-6。
    """
    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return make_judge(
        name="regression",
        model=model_uri,
        instructions=_REGRESSION_INSTRUCTIONS,
        feedback_value_type=bool,
        inference_params=inference_params,
    )


# ---------------------------------------------------------------------------
# 輔助函式：在 rate limit 下以 fallback 安全執行評判器
# ---------------------------------------------------------------------------


def run_judge_safe(
    judge: Any,
    *,
    inputs: Any = None,
    outputs: Any | None = None,
    expectations: Any | None = None,
    name: str = "judge",
    timeout: int = 90,
) -> JudgeFeedback:
    """以錯誤處理、timeout 與 model fallback 執行評判器。

    所有評判器都是欄位式（``inputs``/``outputs``/``expectations``），
    且每個恰好只會進行 1 次 LLM 呼叫。

    遇到 rate limit 錯誤時，會以 fallback models 重新建立評判器並
    重試。對於其他錯誤或 timeout，則回傳零分回饋，
    讓評估不會因評判器失敗而崩潰。
    """
    kwargs: dict[str, Any] = {}
    if inputs is not None:
        kwargs["inputs"] = inputs
    if outputs is not None:
        kwargs["outputs"] = outputs
    if expectations is not None:
        kwargs["expectations"] = expectations

    def _call_judge(j):
        return j(**kwargs)

    # 預算檢查——預算耗盡時平順地回傳零分
    if _llm_budget.exhausted():
        return JudgeFeedback(
            value=0.0,
            rationale=f"LLM call budget exhausted ({_llm_budget.max_calls} calls)",
            name=name,
        )

    # 先嘗試主要評判器
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(_call_judge, judge)
        try:
            fb = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.warning("Judge '%s' timed out after %ds", name, timeout)
            return JudgeFeedback(value=0.0, rationale=f"Judge timed out after {timeout}s", name=name)
        finally:
            # 使用 shutdown(wait=False)，讓仍在執行的評判器執行緒不會阻塞
            pool.shutdown(wait=False)
        return JudgeFeedback(
            value=fb.value,
            rationale=fb.rationale or "",
            name=name,
        )
    except concurrent.futures.TimeoutError:
        # 雖然上方已處理，但保留以策安全
        return JudgeFeedback(value=0.0, rationale=f"Judge timed out after {timeout}s", name=name)
    except Exception as e:
        pool.shutdown(wait=False)
        # 工作區層級錯誤：立即回傳零分，略過 fallback chain
        if _is_workspace_error(e):
            logger.error("Judge '%s' hit workspace error (fail-fast): %s", name, e)
            return JudgeFeedback(value=0.0, rationale=f"Workspace error: {e}", name=name)
        if not _is_rate_limit_error(e):
            logger.debug("Judge '%s' failed: %s", name, e)
            return JudgeFeedback(value=0.0, rationale=f"Judge error: {e}", name=name)

    # 撞到 rate limit——嘗試 fallback models
    logger.warning("Judge '%s' rate limited, trying fallback models", name)
    fallbacks = _get_fallback_models()

    for fallback_model in fallbacks:
        model_uri, inference_params = _to_judge_model_and_params(fallback_model)
        try:
            fallback_judge = make_judge(
                name=judge.name,
                model=model_uri,
                instructions=judge._instructions,
                feedback_value_type=judge._feedback_value_type,
                inference_params=inference_params,
            )
            fb_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = fb_pool.submit(_call_judge, fallback_judge)
                fb = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                fb_pool.shutdown(wait=False)
                logger.warning(
                    "Fallback '%s' timed out after %ds, trying next",
                    fallback_model,
                    timeout,
                )
                continue
            finally:
                fb_pool.shutdown(wait=False)
            logger.info("Judge '%s' succeeded with fallback model '%s'", name, fallback_model)
            return JudgeFeedback(
                value=fb.value,
                rationale=fb.rationale or "",
                name=name,
            )
        except Exception as fallback_err:
            # fallback 中的工作區錯誤：停止嘗試——同一個工作區
            if _is_workspace_error(fallback_err):
                logger.error("Fallback '%s' hit workspace error (fail-fast): %s", fallback_model, fallback_err)
                break
            if _is_rate_limit_error(fallback_err):
                logger.warning("Fallback '%s' also rate limited, trying next", fallback_model)
                continue
            logger.warning("Fallback '%s' failed: %s", fallback_model, fallback_err)
            continue

    # 所有 fallback 都已耗盡
    logger.error("Judge '%s': all models rate limited or timed out", name)
    return JudgeFeedback(
        value=0.0,
        rationale="All models rate limited or timed out — no judge score available",
        name=name,
    )
