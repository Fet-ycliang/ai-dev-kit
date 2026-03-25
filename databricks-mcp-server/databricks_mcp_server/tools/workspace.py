"""Workspace 管理工具 - 在執行階段切換 Databricks workspaces。"""

import configparser
import os
import subprocess
from typing import Any, Dict, List, Optional

from databricks_tools_core.auth import (
    clear_active_workspace,
    get_active_workspace,
    get_workspace_client,
    set_active_workspace,
)

from ..server import mcp

_DATABRICKS_CFG_PATH = os.path.expanduser("~/.databrickscfg")
_VALID_ACTIONS = ("status", "list", "switch", "login")

_TOKEN_EXPIRED_PATTERNS = (
    "refresh token is invalid",
    "token is expired",
    "access token could not be retrieved",
    "invalid_grant",
    "token has expired",
    "unauthenticated",
    "invalid access token",
)


def _read_profiles() -> List[Dict[str, str]]:
    """解析 ~/.databrickscfg 並回傳 profile 字典清單。

    configparser 會將 [DEFAULT] 視為不會出現在 cfg.sections() 中的特殊區段，
    因此我們透過 cfg.defaults() 明確處理它。
    """
    cfg = configparser.ConfigParser()
    try:
        cfg.read(_DATABRICKS_CFG_PATH)
    except Exception:
        return []
    profiles = []
    # 若 DEFAULT 區段有任何 key，則一併納入
    if cfg.defaults():
        host = cfg.defaults().get("host", None)
        profiles.append({"profile": "DEFAULT", "host": host or "(no host configured)"})
    for section in cfg.sections():
        host = cfg.get(section, "host", fallback=None)
        profiles.append({"profile": section, "host": host or "(no host configured)"})
    return profiles


def _derive_profile_name(host: str) -> str:
    """從 workspace URL 推導 profile 名稱。

    例如 https://adb-1234567890.7.azuredatabricks.net -> adb-1234567890
    """
    # 去除 scheme 與結尾斜線
    name = host.rstrip("/")
    if "://" in name:
        name = name.split("://", 1)[1]
    # 取第一個 hostname 片段（第一個點之前）
    name = name.split(".")[0]
    return name or "workspace"


def _validate_and_switch(profile: Optional[str] = None, host: Optional[str] = None) -> Dict[str, Any]:
    """設定目前 workspace 狀態，並透過呼叫 current_user.me() 進行驗證。

    若驗證失敗則回復先前狀態。

    成功時回傳成功 dict，失敗時會拋出例外。
    """
    previous = get_active_workspace()
    set_active_workspace(profile=profile, host=host)
    try:
        client = get_workspace_client()
        me = client.current_user.me()
        return {
            "host": client.config.host,
            "profile": profile or host,
            "username": me.user_name,
        }
    except Exception as exc:
        # 回復先前狀態
        set_active_workspace(
            profile=previous["profile"],
            host=previous["host"],
        )
        raise exc


def _manage_workspace_impl(
    action: str,
    profile: Optional[str] = None,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """manage_workspace 的業務邏輯。與 MCP decorator 分離，
    以便可直接匯入並測試，而不需經過 FastMCP 包裝。"""

    if action not in _VALID_ACTIONS:
        return {"error": f"Invalid action '{action}'. Valid actions: {', '.join(_VALID_ACTIONS)}"}

    # -------------------------------------------------------------------------
    # status: 回傳目前連線中的 workspace 資訊
    # -------------------------------------------------------------------------
    if action == "status":
        try:
            client = get_workspace_client()
            me = client.current_user.me()
            active = get_active_workspace()
            env_profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
            return {
                "host": client.config.host,
                "profile": active["profile"] or env_profile or "(default)",
                "username": me.user_name,
            }
        except Exception as exc:
            return {"error": f"Failed to get workspace status: {exc}"}

    # -------------------------------------------------------------------------
    # list: 顯示 ~/.databrickscfg 中的所有 profile
    # -------------------------------------------------------------------------
    if action == "list":
        profiles = _read_profiles()
        if not profiles:
            return {
                "profiles": [],
                "message": f"No profiles found in {_DATABRICKS_CFG_PATH}. "
                "Run manage_workspace(action='login', host='...') to add one.",
            }
        active = get_active_workspace()
        env_profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
        current_profile = active["profile"] or env_profile

        for p in profiles:
            p["active"] = p["profile"] == current_profile

        return {"profiles": profiles}

    # -------------------------------------------------------------------------
    # switch: 切換到現有的 profile 或 host
    # -------------------------------------------------------------------------
    if action == "switch":
        if not profile and not host:
            return {"error": "Provide either 'profile' (name from ~/.databrickscfg) or 'host' (workspace URL)."}

        if profile:
            # 驗證 profile 是否存在於設定中
            known = {p["profile"] for p in _read_profiles()}
            if profile not in known:
                suggestions = ", ".join(sorted(known)) if known else "none configured"
                return {
                    "error": f"Profile '{profile}' not found in {_DATABRICKS_CFG_PATH}. "
                    f"Available profiles: {suggestions}. "
                    "Use action='login' to authenticate a new workspace."
                }

        try:
            result = _validate_and_switch(profile=profile, host=host)
            result["message"] = f"Switched to workspace: {result['host']}"
            return result
        except Exception as exc:
            err_str = str(exc).lower()
            is_expired = any(p in err_str for p in _TOKEN_EXPIRED_PATTERNS)
            if is_expired:
                # 查出此 profile 對應的 host，讓 LLM 能直接呼叫 login
                profile_host = host
                if not profile_host and profile:
                    for p in _read_profiles():
                        if p["profile"] == profile:
                            profile_host = p["host"]
                            break
                return {
                    "error": "Token expired or invalid for this workspace.",
                    "token_expired": True,
                    "profile": profile,
                    "host": profile_host,
                    "action_required": f"Run manage_workspace(action='login', host='{profile_host}') "
                    "to re-authenticate via browser OAuth.",
                }
            return {
                "error": f"Failed to connect to workspace: {exc}",
                "hint": "Check your credentials or use action='login' to re-authenticate.",
            }

    # -------------------------------------------------------------------------
    # login: 透過 Databricks CLI 執行 OAuth 後再切換
    # -------------------------------------------------------------------------
    if action == "login":
        if not host:
            return {"error": "Provide 'host' (workspace URL) for the login action."}

        derived_profile = _derive_profile_name(host)

        try:
            proc = subprocess.run(
                ["databricks", "auth", "login", "--host", host, "--profile", derived_profile],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return {
                "error": "OAuth login timed out after 120 seconds. "
                "Please complete the browser authorization flow promptly, "
                "or run 'databricks auth login --host <url>' manually in a terminal."
            }
        except FileNotFoundError:
            return {
                "error": "Databricks CLI not found. Install it with: pip install databricks-cli "
                "or brew install databricks/tap/databricks"
            }

        if proc.returncode != 0:
            stderr = proc.stderr.strip() or proc.stdout.strip()
            return {"error": f"databricks auth login failed (exit {proc.returncode}): {stderr}"}

        try:
            conn = _validate_and_switch(profile=derived_profile, host=host)
            conn["message"] = f"Logged in and switched to workspace: {conn['host']}"
            return conn
        except Exception as exc:
            return {
                "error": f"Login succeeded but validation failed: {exc}",
                "hint": f"Try manage_workspace(action='switch', profile='{derived_profile}') manually.",
            }


@mcp.tool
def manage_workspace(
    action: str,
    profile: Optional[str] = None,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """管理目前使用中的 Databricks workspace 連線。

    允許在執行階段切換 workspaces，而無需重新啟動
    MCP server。切換僅限於目前 session，server 重新啟動後會重設。

    動作:
    - status: 回傳目前 workspace 資訊（host、profile、username）。
    - list: 列出 ~/.databrickscfg 中所有已設定的 profiles。
    - switch: 切換到現有的 profile 或 workspace URL。
    - login: 透過 Databricks CLI 為新的 workspace 執行 OAuth login，
             然後切換到該 workspace。

    參數:
        action: "status"、"list"、"switch" 或 "login" 其中之一。
        profile: ~/.databrickscfg 中的 profile 名稱（用於 switch）。
        host: Workspace URL，例如 https://adb-123.azuredatabricks.net
              （用於 switch 或 login）。

    回傳:
        包含操作結果的字典。對 status/switch/login 而言，包含 host、
        profile 與 username。對 list 而言，則為包含 host URLs 的 profile 清單。

    範例:
        >>> manage_workspace(action="status")
        {"host": "https://adb-123.net", "profile": "DEFAULT", "username": "user@company.com"}
        >>> manage_workspace(action="list")
        {"profiles": [{"profile": "DEFAULT", "host": "...", "active": true}, ...]}
        >>> manage_workspace(action="switch", profile="prod")
        {"host": "...", "profile": "prod", "username": "user@company.com"}
        >>> manage_workspace(action="login", host="https://adb-999.azuredatabricks.net")
        {"host": "...", "profile": "adb-999", "username": "user@company.com"}
    """
    return _manage_workspace_impl(action=action, profile=profile, host=host)
