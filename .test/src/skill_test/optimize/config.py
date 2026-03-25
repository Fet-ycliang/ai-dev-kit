"""技能優化的 GEPA 配置預設。

使用具備 GEPAConfig/EngineConfig/ReflectionConfig 的 optimize_anything API。
"""

import os
import warnings

from gepa.optimize_anything import GEPAConfig, EngineConfig, ReflectionConfig, RefinerConfig

DEFAULT_REFLECTION_LM = os.environ.get("GEPA_REFLECTION_LM", "databricks/databricks-claude-opus-4-6")

DEFAULT_GEN_LM = os.environ.get("GEPA_GEN_LM", "databricks/databricks-claude-sonnet-4-6")

DEFAULT_TOKEN_BUDGET: int | None = int(os.environ.get("GEPA_TOKEN_BUDGET", "0")) or None


# ---------------------------------------------------------------------------
# 向 litellm 註冊 Databricks model，讓它知道正確的 context
# window。否則，litellm 可能會模糊比對到限制不同的相似 model，
# 更糟的是，Databricks serving endpoint 可能會拒絕超過
# vLLM 設定之 max_model_len 的請求。
#
# 注意：這不會覆寫 endpoint 自身的 max_model_len 設定。
# 如果 Databricks endpoint 本身設定了較低限制（例如
# 8192），你必須重新配置該 endpoint，或改用其他
# provider（openai/、anthropic/），其 endpoint 支援更大的 context。
# ---------------------------------------------------------------------------
def _configure_litellm_retries() -> None:
    """配置 litellm 在暫時性錯誤（429、529、500）時進行重試。

    GEPA 會呼叫 litellm.completion() 而不傳入 num_retries，因此我們
    在全域層級設定它。這可處理 Anthropic 529「Overloaded」錯誤、
    rate limit，以及其他使用指數退避的暫時性失敗。

    對於 rate-limit 重試會給予額外嘗試次數（10），因為 --include-tools 會傳送
    大型 context，在 Opus 上很容易撞到每分鐘 Token 上限。
    """
    try:
        import litellm
        from litellm import RetryPolicy

        litellm.num_retries = 5
        litellm.request_timeout = 180  # 每次嘗試的秒數
        litellm.retry_policy = RetryPolicy(
            RateLimitErrorRetries=10,
            InternalServerErrorRetries=5,
            TimeoutErrorRetries=5,
        )
        # 降低重試造成的日誌噪音
        litellm.suppress_debug_info = True
    except ImportError:
        pass


def _register_litellm_models() -> None:
    """向 litellm 註冊 Databricks model 的 context window。"""
    try:
        import litellm

        _models = {
            "databricks/databricks-claude-opus-4-6": {
                "max_tokens": 32_000,
                "max_input_tokens": 200_000,
                "max_output_tokens": 32_000,
                "litellm_provider": "databricks",
                "mode": "chat",
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            },
            "databricks/databricks-claude-sonnet-4-6": {
                "max_tokens": 16_000,
                "max_input_tokens": 200_000,
                "max_output_tokens": 16_000,
                "litellm_provider": "databricks",
                "mode": "chat",
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            },
            "databricks/databricks-gpt-5-2": {
                "max_tokens": 128_000,
                "max_input_tokens": 272_000,
                "max_output_tokens": 128_000,
                "litellm_provider": "databricks",
                "mode": "chat",
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            },
            "databricks/databricks-gemini-3-1-pro": {
                "max_tokens": 65_536,
                "max_input_tokens": 1_048_576,
                "max_output_tokens": 65_536,
                "litellm_provider": "databricks",
                "mode": "chat",
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            },
            "databricks/databricks-claude-opus-4-5": {
                "max_tokens": 32_000,
                "max_input_tokens": 200_000,
                "max_output_tokens": 32_000,
                "litellm_provider": "databricks",
                "mode": "chat",
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            },
            "databricks/databricks-gpt-5": {
                "max_tokens": 100_000,
                "max_input_tokens": 1_048_576,
                "max_output_tokens": 100_000,
                "litellm_provider": "databricks",
                "mode": "chat",
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            },
            "databricks/databricks-claude-sonnet-4-5": {
                "max_tokens": 16_000,
                "max_input_tokens": 200_000,
                "max_output_tokens": 16_000,
                "litellm_provider": "databricks",
                "mode": "chat",
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            },
        }
        for model_name, model_info in _models.items():
            litellm.model_cost[model_name] = model_info
    except ImportError:
        pass


_register_litellm_models()
_configure_litellm_retries()


# 額外開銷乘數：reflection prompt 約為原始候選 Token 的這個倍數
# （包含 background、ASI、framing）。
_REFLECTION_OVERHEAD_MULTIPLIER = 3

PRESETS: dict[str, GEPAConfig] = {
    "minimal": GEPAConfig(
        engine=EngineConfig(max_metric_calls=8, parallel=True),
        reflection=ReflectionConfig(reflection_lm=DEFAULT_REFLECTION_LM),
        refiner=RefinerConfig(max_refinements=1),
    ),
    "quick": GEPAConfig(
        engine=EngineConfig(max_metric_calls=15, parallel=True),
        reflection=ReflectionConfig(reflection_lm=DEFAULT_REFLECTION_LM),
        refiner=RefinerConfig(max_refinements=1),
    ),
    "standard": GEPAConfig(
        engine=EngineConfig(max_metric_calls=50, parallel=True),
        reflection=ReflectionConfig(
            reflection_lm=DEFAULT_REFLECTION_LM,
            reflection_minibatch_size=3,
        ),
        refiner=RefinerConfig(max_refinements=1),
    ),
    "thorough": GEPAConfig(
        engine=EngineConfig(max_metric_calls=150, parallel=True),
        reflection=ReflectionConfig(
            reflection_lm=DEFAULT_REFLECTION_LM,
            reflection_minibatch_size=3,
        ),
        refiner=RefinerConfig(max_refinements=1),
    ),
}

# 每個預設的基礎 max_metric_calls（用於依元件數量縮放）
PRESET_BASE_CALLS: dict[str, int] = {
    "minimal": 8,
    "quick": 15,
    "standard": 50,
    "thorough": 150,
}

# 各預設的上限：安全機制，避免元件縮放超出合理上限。
# 對具有許多 tool 元件的 --tools-only 模式尤其重要。
PRESET_MAX_CALLS: dict[str, int] = {
    "minimal": 15,
    "quick": 45,
    "standard": 150,
    "thorough": 300,
}

# 每個 pass 的最大總 metric 呼叫數，以避免失控的執行時間。
# 元件很多時，未設上限的縮放（例如 50 * 17 = 850）可能會導致
# 像 Sonnet 這樣較慢的 reflection model 卡住數小時。
MAX_METRIC_CALLS_PER_PASS = 300

# 已知足夠快、能處理大型多元件優化的 models。
# 其他 model 會套用 metric-call 上限。
_FAST_REFLECTION_MODELS = {
    "databricks/databricks-claude-opus-4-6",
    "databricks/databricks-gpt-5-2",
    "openai/gpt-4o",
    "anthropic/claude-opus-4-6",
}


def validate_databricks_env() -> None:
    """檢查 DATABRICKS_API_BASE 是否已針對 litellm 正確設定。

    litellm 的 Databricks provider 需要：
        DATABRICKS_API_BASE=https://<workspace>.cloud.databricks.com/serving-endpoints

    常見錯誤是漏掉 /serving-endpoints，這會導致 404 錯誤。
    """
    api_base = os.environ.get("DATABRICKS_API_BASE", "")
    if api_base and not api_base.rstrip("/").endswith("/serving-endpoints"):
        fixed = api_base.rstrip("/") + "/serving-endpoints"
        warnings.warn(
            f"DATABRICKS_API_BASE={api_base!r} is missing '/serving-endpoints' suffix. "
            f"litellm will get 404 errors. Automatically fixing to: {fixed}",
            stacklevel=2,
        )
        os.environ["DATABRICKS_API_BASE"] = fixed


def validate_reflection_context(
    reflection_lm: str,
    total_candidate_tokens: int,
) -> None:
    """若候選內容對 reflection model 而言可能過大則發出警告。

    會查詢 litellm 的 model registry 以取得 model 的 max_input_tokens，
    並與估計的 reflection prompt 大小比較。

    注意：這裡檢查的是 litellm 對 model 的*用戶端*認知。Databricks
    serving endpoint 可能透過 vLLM 的 ``max_model_len`` 設定了*不同*
    （更低）的限制。如果你看到訊息中含有 ``max_model_len`` 的
    ``BadRequestError``，瓶頸就在 endpoint 本身——
    請改用其 endpoint 支援所需 context 的 provider（例如
    ``openai/gpt-4o`` 或 ``anthropic/claude-sonnet-4-5-20250514``）。
    """
    try:
        import litellm

        info = litellm.get_model_info(reflection_lm)
        limit = info.get("max_input_tokens") or info.get("max_tokens") or 0
    except Exception:
        return  # 無法判定限制——略過檢查

    if limit <= 0:
        return

    estimated_prompt = total_candidate_tokens * _REFLECTION_OVERHEAD_MULTIPLIER
    if estimated_prompt > limit:
        raise ValueError(
            f"\nReflection model '{reflection_lm}' has a {limit:,}-token input limit "
            f"(per litellm), but the estimated reflection prompt is ~{estimated_prompt:,} "
            f"tokens ({total_candidate_tokens:,} candidate tokens x "
            f"{_REFLECTION_OVERHEAD_MULTIPLIER} overhead).\n\n"
            f"Fix: use a model with a larger context window:\n"
            f"  --reflection-lm 'databricks/databricks-claude-opus-4-6'   (200K)\n"
            f"  --reflection-lm 'openai/gpt-4o'                           (128K)\n"
            f"  --reflection-lm 'anthropic/claude-sonnet-4-5-20250514'    (200K)\n\n"
            f"Or set the environment variable:\n"
            f"  export GEPA_REFLECTION_LM='databricks/databricks-claude-opus-4-6'\n\n"
            f"If you already use a large-context model and still see 'max_model_len'\n"
            f"errors, the Databricks serving endpoint itself has a low context limit.\n"
            f"Switch to a non-Databricks provider (openai/ or anthropic/) instead.\n\n"
            f"  Current GEPA_REFLECTION_LM={os.environ.get('GEPA_REFLECTION_LM', '(not set)')}"
        )


def estimate_pass_duration(
    num_metric_calls: int,
    reflection_lm: str,
    total_candidate_tokens: int,
    num_dataset_examples: int = 7,
) -> float | None:
    """估計單一優化 pass 的實際耗時秒數。

    metric 呼叫大多是快速的本地評估。較慢的部分是
    reflection LLM 呼叫，約略每次迭代發生一次
    （num_metric_calls / num_dataset_examples 次迭代）。

    若無法估計則回傳 None。
    """
    # 依 model 類別粗略估計每次 reflection 的延遲（秒）
    if reflection_lm in _FAST_REFLECTION_MODELS:
        secs_per_reflection = 5.0
    elif "sonnet" in reflection_lm.lower():
        secs_per_reflection = 20.0
    elif "haiku" in reflection_lm.lower():
        secs_per_reflection = 8.0
    else:
        secs_per_reflection = 15.0

    # 依候選內容大小縮放（候選越大 → 越慢）
    size_factor = min(max(1.0, total_candidate_tokens / 10_000), 2.5)
    adjusted = secs_per_reflection * size_factor

    # 近似的迭代次數（每次迭代都會評估所有資料集範例）
    num_iterations = max(1, num_metric_calls // max(num_dataset_examples, 1))

    return num_iterations * adjusted


def get_preset(
    name: str,
    reflection_lm: str | None = None,
    num_components: int = 1,
    max_metric_calls_override: int | None = None,
) -> GEPAConfig:
    """依名稱取得 GEPA 配置預設，並依元件數量縮放。

    在優化多個元件（技能 + 工具模組）時，GEPA 的
    round-robin selector 會將預算分散到所有元件。我們會縮放
    ``max_metric_calls``，讓*每個元件*都能收到該預設的
    基礎預算，而不是彼此拆分。

    對於較慢的 reflection models（非 Opus/GPT-4o），
    總 metric 呼叫數會限制為 ``MAX_METRIC_CALLS_PER_PASS``，以避免長達數小時的卡住。

    參數:
        name: "quick"、"standard"、"thorough" 其中之一
        reflection_lm: 覆寫 reflection LM model 字串
        num_components: GEPA 元件數量（用於縮放預算）
        max_metric_calls_override: 每個 pass 的明確 metric 呼叫上限

    回傳:
        GEPAConfig 實例
    """
    if name not in PRESETS:
        raise KeyError(f"Unknown preset '{name}'. Choose from: {list(PRESETS.keys())}")

    # 若使用 databricks/ 前綴則驗證 Databricks 環境變數
    effective_lm = reflection_lm or DEFAULT_REFLECTION_LM
    if isinstance(effective_lm, str) and effective_lm.startswith("databricks/"):
        validate_databricks_env()

    base_calls = PRESET_BASE_CALLS[name]
    scaled_calls = base_calls * max(num_components, 1)

    # 若提供明確覆寫則套用
    if max_metric_calls_override is not None:
        scaled_calls = max_metric_calls_override
    else:
        # 先套用各預設上限（多元件模式的安全機制）
        preset_cap = PRESET_MAX_CALLS[name]
        if scaled_calls > preset_cap:
            scaled_calls = preset_cap

    # 對較慢的 model 設限，以避免卡住數小時
    if (
        max_metric_calls_override is None
        and effective_lm not in _FAST_REFLECTION_MODELS
        and scaled_calls > MAX_METRIC_CALLS_PER_PASS
    ):
        warnings.warn(
            f"Capping metric calls from {scaled_calls} to {MAX_METRIC_CALLS_PER_PASS} "
            f"for reflection model '{effective_lm}'. "
            f"Use --max-metric-calls to override, or use a faster model "
            f"(e.g., databricks/databricks-claude-opus-4-6).",
            stacklevel=2,
        )
        scaled_calls = MAX_METRIC_CALLS_PER_PASS

    config = PRESETS[name]
    config = GEPAConfig(
        engine=EngineConfig(
            max_metric_calls=scaled_calls,
            parallel=config.engine.parallel,
        ),
        reflection=ReflectionConfig(
            reflection_lm=reflection_lm or config.reflection.reflection_lm,
            reflection_minibatch_size=config.reflection.reflection_minibatch_size,
            skip_perfect_score=config.reflection.skip_perfect_score,
        ),
        merge=config.merge,
        refiner=config.refiner,
        tracking=config.tracking,
    )
    return config
