"""使用者工具 - 取得目前 Databricks 使用者的資訊。"""

from typing import Dict, Any

from databricks_tools_core.auth import get_current_username

from ..server import mcp


@mcp.tool
def get_current_user() -> Dict[str, Any]:
    """
    取得目前已通過驗證的 Databricks 使用者身分資訊。

    回傳 username（email）與使用者在 workspace 中的 home path。
    有助於判斷應在哪裡建立檔案、notebooks 與其他
    使用者專屬資源。

    回傳:
        包含以下內容的字典：
        - username: 使用者的 email 位址（若無法取得則為 None）
        - home_path: 使用者在 workspace 中的家目錄（例如 /Workspace/Users/user@example.com/）
    """
    username = get_current_username()
    home_path = f"/Workspace/Users/{username}/" if username else None
    return {
        "username": username,
        "home_path": home_path,
    }
