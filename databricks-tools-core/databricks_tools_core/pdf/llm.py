"""使用 Databricks model serving 執行 PDF 產生的 LLM 呼叫。

使用與所有其他工具相同的 query_serving_endpoint。
"""

import json
import logging
import os
import re
from functools import lru_cache
from typing import Any, Optional, Union

from pydantic import BaseModel

from ..serving.endpoints import list_serving_endpoints, query_serving_endpoint

logger = logging.getLogger(__name__)


class LLMConfigurationError(Exception):
    """當 LLM 未正確設定時引發。"""


@lru_cache(maxsize=1)
def _discover_databricks_gpt_endpoints() -> tuple[Optional[str], Optional[str]]:
    """探索最新的 databricks-gpt endpoints。

    尋找以 'databricks-gpt' 開頭的 endpoints，並回傳：
    - 最新的非 nano 模型（最高版本）
    - 最新的 nano 模型（名稱中含有 'nano' 的最高版本）

    回傳：
        (main_model, nano_model) 的 tuple。若未找到，任一值都可能為 None。
    """
    try:
        # 取得所有 endpoints - SDK 會抓取全部，再由用戶端篩選 databricks-gpt-*
        endpoints = list_serving_endpoints(limit=None)
    except Exception as e:
        logger.warning(f"無法列出用於自動探索的 endpoints：{e}")
        return None, None

    # 篩選出狀態為 READY 的 databricks-gpt endpoints
    gpt_endpoints = [
        ep["name"] for ep in endpoints if ep["name"].startswith("databricks-gpt") and ep.get("state") == "READY"
    ]

    if not gpt_endpoints:
        logger.warning("找不到 databricks-gpt endpoints")
        return None, None

    # 從 endpoint 名稱（如 "databricks-gpt-5-4" 或 "databricks-gpt-5-4-nano"）解析版本
    def parse_version(name: str) -> tuple[int, ...]:
        """從 endpoint 名稱擷取版本號。"""
        # 比對像是 "5-4" 或 "5-4-nano" 的模式
        match = re.search(r"databricks-gpt-(\d+(?:-\d+)*)", name)
        if match:
            version_str = match.group(1)
            # 若有 'nano' 後綴，先移除再解析版本
            version_str = version_str.replace("-nano", "")
            return tuple(int(x) for x in version_str.split("-"))
        return (0,)

    # 分開處理 nano 與非 nano endpoints
    nano_endpoints = [ep for ep in gpt_endpoints if "nano" in ep.lower()]
    main_endpoints = [ep for ep in gpt_endpoints if "nano" not in ep.lower()]

    # 依版本排序（最高版本優先）
    main_endpoints.sort(key=parse_version, reverse=True)
    nano_endpoints.sort(key=parse_version, reverse=True)

    main_model = main_endpoints[0] if main_endpoints else None
    nano_model = nano_endpoints[0] if nano_endpoints else main_model  # 若無 nano，回退至 main

    logger.info(f"已探索到 databricks-gpt endpoints：main={main_model}，nano={nano_model}")
    return main_model, nano_model


def _get_model_name(mini: bool = False, model_name: Optional[str] = None) -> str:
    """取得模型 endpoint 名稱。

    優先順序：
    1. 明確傳入的 model_name 參數
    2. 環境變數（DATABRICKS_MODEL 或 DATABRICKS_MODEL_NANO）
    3. 自動探索到的 databricks-gpt endpoint

    參數：
        mini: 使用較小／較快的模型（nano 變體）
        model_name: 覆寫模型名稱

    回傳：
        模型 endpoint 名稱

    引發：
        LLMConfigurationError: 若找不到任何可用模型
    """
    if model_name:
        return model_name

    # 檢查環境變數
    if mini:
        env_model = os.getenv("DATABRICKS_MODEL_NANO")
        if env_model:
            return env_model
    else:
        env_model = os.getenv("DATABRICKS_MODEL")
        if env_model:
            return env_model

    # 從可用 endpoints 自動探索
    main_model, nano_model = _discover_databricks_gpt_endpoints()

    if mini and nano_model:
        return nano_model
    if main_model:
        return main_model

    raise LLMConfigurationError(
        "未設定 LLM 模型。請設定 DATABRICKS_MODEL 環境變數，"
        "或確認你的 workspace 中有可用的 databricks-gpt-* endpoint。"
    )


def call_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    mini: bool = False,
    max_tokens: int = 4000,
    temperature: float = 1.0,
    response_format: Optional[Union[str, dict[str, Any], type[BaseModel]]] = None,
    model_name: Optional[str] = None,
) -> str:
    """呼叫 Databricks model serving endpoint。

    使用與所有其他工具相同的 query_serving_endpoint（SDK auth chain）。

    參數：
        prompt: 使用者 prompt
        system_prompt: 可選的 system prompt
        mini: 使用較小／較快的模型（若可用則使用 nano 變體）
        max_tokens: 回應中的最大 token 數
        temperature: 模型 temperature（預設：1.0）
        response_format: 回應格式 - 'json_object'（注意：會透過 system prompt 提示傳遞）
        model_name: 覆寫模型名稱（若未設定則自動探索）

    回傳：
        產生的內容字串
    """
    endpoint_name = _get_model_name(mini=mini, model_name=model_name)

    # 建立 messages
    messages: list[dict[str, str]] = []

    # 若要求 json 回應，則在 system prompt 加入 JSON 提示
    effective_system_prompt = system_prompt or ""
    if response_format == "json_object":
        if effective_system_prompt:
            effective_system_prompt += "\n\n你必須只回應有效的 JSON。"
        else:
            effective_system_prompt = "你必須只回應有效的 JSON。"

    if effective_system_prompt:
        messages.append({"role": "system", "content": effective_system_prompt})
    messages.append({"role": "user", "content": prompt})

    logger.info(f"正在呼叫 Databricks endpoint：{endpoint_name}")

    try:
        response = query_serving_endpoint(
            name=endpoint_name,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature if temperature != 1.0 else None,
        )
    except Exception as e:
        logger.error(f"呼叫 {endpoint_name} 時發生錯誤：{type(e).__name__}：{e}")
        raise

    # 從回應擷取內容
    if not response.get("choices") or not response["choices"][0].get("message", {}).get("content"):
        finish_reason = response.get("choices", [{}])[0].get("finish_reason", "unknown")
        raise Exception(f"模型回應為空。finish_reason={finish_reason}")

    content = response["choices"][0]["message"]["content"]

    # 驗證 Pydantic 回應
    if isinstance(response_format, type) and issubclass(response_format, BaseModel):
        try:
            response_format.model_validate(json.loads(content))
        except Exception as e:
            logger.warning(f"回應驗證失敗：{e}")

    return content
