---
name: databricks-config
description: "管理 Databricks workspace 連線：檢查目前的 workspace、切換 profiles、列出可用 workspaces，或認證新的 workspace。當使用者提到 \"switch workspace\"、\"which workspace\"、\"current profile\"、\"databrickscfg\"、\"connect to workspace\" 或 \"databricks auth\" 時使用。"
---

對所有 workspace 操作都使用 `manage_workspace` MCP tool。不要編輯 `~/.databrickscfg`、使用 Bash，或使用 Databricks CLI。

## 步驟

1. 呼叫 `ToolSearch`，查詢 `select:mcp__databricks__manage_workspace` 以載入該 tool。

2. 將使用者意圖對應至動作：
   - status / which workspace / current → `action="status"`
   - list / available workspaces → `action="list"`
   - switch to X → 先呼叫 `list` 找出 profile 名稱，再使用 `action="switch", profile="<name>"`（若提供的是 URL，則使用 `host="<url>"`）
   - login / connect / authenticate → `action="login", host="<url>"`

3. 以該動作與相關參數呼叫 `mcp__databricks__manage_workspace`。

4. 呈現結果。對於 `status`/`switch`/`login`：顯示 host、profile、username。對於 `list`：以格式化表格顯示，並標示目前啟用的 profile。

> **注意：** 切換僅限目前 session——MCP server 重新啟動後就會重設。若要永久設定 profile，請使用 `databricks auth login -p <profile>`，並更新 `~/.databrickscfg` 中的 `cluster_id` 或 `serverless_compute_id = auto`。
