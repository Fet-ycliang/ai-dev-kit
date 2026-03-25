# 部署 Databricks Apps

三種部署方式：Databricks CLI（最簡單）、Asset Bundles（多環境）或 MCP 工具（程式化）。

**Cookbook 部署指南**：https://apps-cookbook.dev/docs/deploy

---

## 方式一：Databricks CLI

**最適用於**：快速部署、單一環境。

### 步驟一：建立 app.yaml

```yaml
command:
  - "python"        # 依框架調整——請見下方表格
  - "app.py"

env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: USE_MOCK_BACKEND
    value: "false"
```

### 各框架的 app.yaml 指令

| 框架 | 指令 |
|------|------|
| Dash | `["python", "app.py"]` |
| Streamlit | `["streamlit", "run", "app.py"]` |
| Gradio | `["python", "app.py"]` |
| Flask | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8000"]` |
| FastAPI | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]` |
| Reflex | `["reflex", "run", "--env", "prod"]` |

### 步驟二：建立並部署

```bash
# 建立應用程式
databricks apps create <app-name>

# 上傳原始碼
databricks workspace mkdirs /Workspace/Users/<user>/apps/<app-name>
databricks workspace import-dir . /Workspace/Users/<user>/apps/<app-name>

# 部署
databricks apps deploy <app-name> \
  --source-code-path /Workspace/Users/<user>/apps/<app-name>

# 透過 UI 新增資源（SQL warehouse、Lakebase 等）

# 確認狀態與 URL
databricks apps get <app-name>
```

### 重新部署

```bash
databricks workspace delete /Workspace/Users/<user>/apps/<app-name> --recursive
databricks workspace import-dir . /Workspace/Users/<user>/apps/<app-name>
databricks apps deploy <app-name> \
  --source-code-path /Workspace/Users/<user>/apps/<app-name>
```

---

## 方式二：Databricks Asset Bundles（DABs）

**最適用於**：多環境部署（dev/staging/prod）、版本控制的基礎設施。

**建議工作流程**：先以 CLI 部署驗證，再產生 bundle 設定。

### 從既有應用程式產生 Bundle

```bash
databricks bundle generate app \
  --existing-app-name <app-name> \
  --key <resource_key>
```

此指令會建立：
- `resources/<key>.app.yml` — 應用程式資源定義
- `src/app/` — 應用程式原始檔，包含 `app.yaml`

### 以 Bundles 部署

```bash
# 驗證
databricks bundle validate -t dev

# 部署
databricks bundle deploy -t dev

# 啟動應用程式（部署後必須執行）
databricks bundle run <resource_key> -t dev

# 正式環境
databricks bundle deploy -t prod
databricks bundle run <resource_key> -t prod
```

**與其他資源的關鍵差異**：環境變數須寫入 `src/app/app.yaml`，而非 `databricks.yml`。

完整 DABs 指引請使用 **databricks-bundles** skill。

---

## 方式三：MCP 工具

程式化應用程式生命週期管理，請見 [6-mcp-approach.md](6-mcp-approach.md)。

---

## 部署後驗證

### 查看日誌

```bash
databricks apps logs <app-name>
```

**日誌中的關鍵模式**：
- `[SYSTEM]` — 部署狀態、檔案更新、套件安裝
- `[APP]` — 應用程式輸出、框架訊息
- `Deployment successful` — 應用程式已成功部署
- `App started successfully` — 應用程式正在執行
- `Error:` — 請檢查 stack trace

### 確認

1. 存取應用程式 URL（從 `databricks apps get <app-name>` 取得）
2. 確認所有頁面正常載入
3. 驗證資料連線（查看日誌中的後端初始化訊息）
4. 若已啟用，測試使用者授權流程

### 設定權限

- 授予已核准的使用者／群組 `CAN USE`
- 僅授予受信任開發人員 `CAN MANAGE`
- 確認 service principal 擁有所需的資源存取權限
