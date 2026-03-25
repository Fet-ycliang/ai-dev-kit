"""manage_workspace MCP 工具的測試。"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from databricks_mcp_server.tools.workspace import _manage_workspace_impl as manage_workspace
from databricks_tools_core.auth import clear_active_workspace, get_active_workspace

# Patch 目標
_CFG_PATH = "databricks_mcp_server.tools.workspace._DATABRICKS_CFG_PATH"
_VALIDATE_AND_SWITCH = "databricks_mcp_server.tools.workspace._validate_and_switch"
_GET_WORKSPACE_CLIENT = "databricks_mcp_server.tools.workspace.get_workspace_client"
_GET_ACTIVE_WORKSPACE = "databricks_mcp_server.tools.workspace.get_active_workspace"
_SUBPROCESS_RUN = "databricks_mcp_server.tools.workspace.subprocess.run"


@pytest.fixture(autouse=True)
def reset_active_workspace():
    """確保每個測試前後都會清除作用中的 workspace。"""
    clear_active_workspace()
    yield
    clear_active_workspace()


@pytest.fixture
def tmp_databrickscfg(tmp_path):
    """寫入一個含有三個已知 profile 的暫時 ~/.databrickscfg。"""
    cfg = tmp_path / ".databrickscfg"
    cfg.write_text(
        "[DEFAULT]\nhost = https://adb-111.azuredatabricks.net\n\n"
        "[prod]\nhost = https://adb-222.azuredatabricks.net\n\n"
        "[staging]\nhost = https://adb-333.azuredatabricks.net\n"
    )
    return cfg


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_returns_current_info():
    """action='status' 應回傳 host、profile 與 username。"""
    mock_client = MagicMock()
    mock_client.config.host = "https://adb-111.azuredatabricks.net"
    mock_client.current_user.me.return_value = MagicMock(user_name="user@example.com")

    with (
        patch(_GET_WORKSPACE_CLIENT, return_value=mock_client),
        patch(_GET_ACTIVE_WORKSPACE, return_value={"profile": "DEFAULT", "host": None}),
    ):
        result = manage_workspace(action="status")

    assert result["host"] == "https://adb-111.azuredatabricks.net"
    assert result["username"] == "user@example.com"
    assert result["profile"] == "DEFAULT"


def test_status_returns_error_on_failure():
    """當 SDK 拋出例外時，action='status' 應回傳 error dict。"""
    with patch(_GET_WORKSPACE_CLIENT, side_effect=Exception("auth failed")):
        result = manage_workspace(action="status")

    assert "error" in result
    assert "auth failed" in result["error"]


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_returns_all_profiles(tmp_databrickscfg):
    """action='list' 應回傳所有 profiles 的 host URL，並標示作用中的 profile。"""
    with (
        patch(_CFG_PATH, str(tmp_databrickscfg)),
        patch(_GET_ACTIVE_WORKSPACE, return_value={"profile": "prod", "host": None}),
    ):
        result = manage_workspace(action="list")

    assert "profiles" in result
    assert len(result["profiles"]) == 3
    profiles_by_name = {p["profile"]: p for p in result["profiles"]}
    assert profiles_by_name["prod"]["active"] is True
    assert profiles_by_name["DEFAULT"]["active"] is False
    assert "adb-222" in profiles_by_name["prod"]["host"]


def test_list_empty_config(tmp_path):
    """在空白設定下，action='list' 應回傳空清單與提示訊息。"""
    empty_cfg = tmp_path / ".databrickscfg"
    empty_cfg.write_text("")
    with patch(_CFG_PATH, str(empty_cfg)), patch(_GET_ACTIVE_WORKSPACE, return_value={"profile": None, "host": None}):
        result = manage_workspace(action="list")

    assert result["profiles"] == []
    assert "message" in result


def test_list_missing_config(tmp_path):
    """當設定檔不存在時，action='list' 應回傳空清單。"""
    with (
        patch(_CFG_PATH, str(tmp_path / "nonexistent.cfg")),
        patch(_GET_ACTIVE_WORKSPACE, return_value={"profile": None, "host": None}),
    ):
        result = manage_workspace(action="list")

    assert result["profiles"] == []


def test_list_profile_without_host(tmp_path):
    """即使 profile 沒有 host key，action='list' 仍應回傳該 profile。"""
    cfg = tmp_path / ".databrickscfg"
    cfg.write_text("[nohostprofile]\ntoken = abc123\n")
    with patch(_CFG_PATH, str(cfg)), patch(_GET_ACTIVE_WORKSPACE, return_value={"profile": None, "host": None}):
        result = manage_workspace(action="list")

    assert len(result["profiles"]) == 1
    assert result["profiles"][0]["profile"] == "nohostprofile"
    assert "no host configured" in result["profiles"][0]["host"]


# ---------------------------------------------------------------------------
# switch
# ---------------------------------------------------------------------------


def test_switch_valid_profile(tmp_databrickscfg):
    """使用已知 profile 時，action='switch' 應呼叫 _validate_and_switch 並回傳成功。"""
    success = {"host": "https://adb-222.azuredatabricks.net", "profile": "prod", "username": "user@example.com"}
    with patch(_CFG_PATH, str(tmp_databrickscfg)), patch(_VALIDATE_AND_SWITCH, return_value=success) as mock_validate:
        result = manage_workspace(action="switch", profile="prod")

    mock_validate.assert_called_once_with(profile="prod", host=None)
    assert result["profile"] == "prod"
    assert "message" in result


def test_switch_nonexistent_profile(tmp_databrickscfg):
    """使用未知 profile 名稱時，action='switch' 應回傳包含可用 profiles 的錯誤。"""
    with patch(_CFG_PATH, str(tmp_databrickscfg)):
        result = manage_workspace(action="switch", profile="unknown-profile")

    assert "error" in result
    assert "unknown-profile" in result["error"]
    assert "DEFAULT" in result["error"] or "prod" in result["error"]


def test_switch_with_host(tmp_databrickscfg):
    """使用 host URL 時，action='switch' 應以該 host 呼叫 _validate_and_switch。"""
    host = "https://adb-222.azuredatabricks.net"
    success = {"host": host, "profile": host, "username": "user@example.com"}
    with patch(_CFG_PATH, str(tmp_databrickscfg)), patch(_VALIDATE_AND_SWITCH, return_value=success) as mock_validate:
        result = manage_workspace(action="switch", host=host)

    mock_validate.assert_called_once_with(profile=None, host=host)
    assert "message" in result


def test_switch_rollback_on_auth_failure(tmp_databrickscfg):
    """當驗證失敗時，action='switch' 應回傳錯誤，且不得更新作用中的 workspace。"""
    with (
        patch(_CFG_PATH, str(tmp_databrickscfg)),
        patch(_VALIDATE_AND_SWITCH, side_effect=Exception("invalid credentials")),
    ):
        result = manage_workspace(action="switch", profile="prod")

    assert "error" in result
    assert "invalid credentials" in result["error"]
    assert get_active_workspace()["profile"] is None


def test_switch_expired_token_returns_structured_response(tmp_databrickscfg):
    """當 token 已過期時，action='switch' 應回傳含 token_expired 旗標的結構化回應。"""
    expired_msg = "default auth: databricks-cli: cannot get access token: refresh token is invalid"
    with patch(_CFG_PATH, str(tmp_databrickscfg)), patch(_VALIDATE_AND_SWITCH, side_effect=Exception(expired_msg)):
        result = manage_workspace(action="switch", profile="prod")

    assert result.get("token_expired") is True
    assert result["profile"] == "prod"
    assert "adb-222" in result["host"]
    assert "login" in result["action_required"]


def test_switch_no_profile_no_host():
    """缺少 profile 與 host 時，action='switch' 應回傳明確的錯誤。"""
    result = manage_workspace(action="switch")
    assert "error" in result
    assert "profile" in result["error"].lower() or "host" in result["error"].lower()


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------


def test_login_calls_cli():
    """action='login' 應執行 'databricks auth login --host ...'。"""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    success = {"host": "https://adb-999.net", "profile": "adb-999", "username": "u@x.com"}

    with patch(_SUBPROCESS_RUN, return_value=mock_proc) as mock_run, patch(_VALIDATE_AND_SWITCH, return_value=success):
        result = manage_workspace(action="login", host="https://adb-999.azuredatabricks.net")

    args = mock_run.call_args.args[0]
    assert "databricks" in args and "auth" in args and "login" in args
    assert "--host" in args and "https://adb-999.azuredatabricks.net" in args
    assert result["profile"] == "adb-999"


def test_login_passes_stdin_devnull():
    """action='login' 應設定 stdin=DEVNULL，以避免繼承 MCP 的 stdio pipe。"""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    success = {"host": "https://adb-999.net", "profile": "adb-999", "username": "u@x.com"}

    with patch(_SUBPROCESS_RUN, return_value=mock_proc) as mock_run, patch(_VALIDATE_AND_SWITCH, return_value=success):
        manage_workspace(action="login", host="https://adb-999.azuredatabricks.net")

    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("stdin") == subprocess.DEVNULL


def test_login_timeout():
    """當 OAuth 流程逾時時，action='login' 應回傳明確的錯誤。"""
    with patch(_SUBPROCESS_RUN, side_effect=subprocess.TimeoutExpired(cmd="databricks", timeout=120)):
        result = manage_workspace(action="login", host="https://adb-999.net")

    assert "error" in result
    assert "timed out" in result["error"].lower()


def test_login_cli_failure():
    """當 CLI 以非零狀態結束時，action='login' 應回傳錯誤。"""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "Error: invalid workspace URL"
    mock_proc.stdout = ""

    with patch(_SUBPROCESS_RUN, return_value=mock_proc):
        result = manage_workspace(action="login", host="https://bad-host.net")

    assert "error" in result
    assert "invalid workspace URL" in result["error"]


def test_login_cli_not_installed():
    """當找不到 Databricks CLI 時，action='login' 應回傳有幫助的錯誤。"""
    with patch(_SUBPROCESS_RUN, side_effect=FileNotFoundError):
        result = manage_workspace(action="login", host="https://adb-999.net")

    assert "error" in result
    assert "CLI" in result["error"] or "databricks" in result["error"].lower()


def test_login_switches_after_success():
    """在 CLI 成功呼叫後，action='login' 應更新作用中的 workspace。"""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    success = {"host": "https://adb-999.net", "profile": "adb-999", "username": "u@x.com"}

    with (
        patch(_SUBPROCESS_RUN, return_value=mock_proc),
        patch(_VALIDATE_AND_SWITCH, return_value=success) as mock_validate,
    ):
        result = manage_workspace(action="login", host="https://adb-999.azuredatabricks.net")

    mock_validate.assert_called_once()
    assert result["username"] == "u@x.com"
    assert "message" in result


def test_login_no_host():
    """缺少 host 時，action='login' 應回傳明確的錯誤。"""
    result = manage_workspace(action="login")
    assert "error" in result
    assert "host" in result["error"].lower()


# ---------------------------------------------------------------------------
# invalid action
# ---------------------------------------------------------------------------


def test_invalid_action():
    """未辨識的 action 應回傳列出有效 actions 的錯誤。"""
    result = manage_workspace(action="badaction")
    assert "error" in result
    for valid in ("status", "list", "switch", "login"):
        assert valid in result["error"]
