# 以 MCP 工具管理應用程式生命週期

使用 MCP 工具以程式化方式建立、部署及管理 Databricks Apps。此方式與 CLI 工作流程相同，但可由 AI agent 呼叫。

---

## 工作流程

### 步驟一：在本地撰寫應用程式檔案

在本地資料夾建立應用程式檔案：

```
my_app/
├── app.py             # 主應用程式
├── models.py          # Pydantic 資料模型
├── backend.py         # 資料存取層
├── requirements.txt   # 額外的套件依賴
└── app.yaml           # Databricks Apps 設定
```

### 步驟二：上傳至 Workspace

```python
# MCP 工具：upload_folder
upload_folder(
    local_folder="/path/to/my_app",
    workspace_folder="/Workspace/Users/user@example.com/my_app"
)
```

### 步驟三：建立並部署應用程式

```python
# MCP 工具：create_or_update_app（若不存在則建立 + 部署）
result = create_or_update_app(
    name="my-dashboard",
    description="Customer analytics dashboard",
    source_code_path="/Workspace/Users/user@example.com/my_app"
)
# 回傳：{"name": "my-dashboard", "url": "...", "created": True, "deployment": {...}}
```

### 步驟四：驗證

```python
# MCP 工具：get_app（含日誌）
app = get_app(name="my-dashboard", include_logs=True)
# 回傳：{"name": "...", "url": "...", "status": "RUNNING", "logs": "...", ...}
```

### 步驟五：迭代

1. 修正本地檔案的問題
2. 以 `upload_folder` 重新上傳
3. 以 `create_or_update_app` 重新部署（若已存在則更新 + 部署）
4. 檢查 `get_app(name=..., include_logs=True)` 是否有錯誤
5. 重複直到應用程式運作正常

---

## 快速參考：MCP 工具

| 工具 | 說明 |
|------|------|
| **`create_or_update_app`** | 若應用程式不存在則建立，傳入 `source_code_path` 可選擇部署 |
| **`get_app`** | 依名稱取得應用程式詳情（傳入 `include_logs=True` 可取得日誌），或列出所有應用程式 |
| **`delete_app`** | 刪除應用程式 |
| **`upload_folder`** | 將本地資料夾上傳至 workspace（共用工具） |

---

## 注意事項

- 建立應用程式後，透過 Databricks Apps UI 新增資源（SQL warehouse、Lakebase 等）
- MCP 工具使用 service principal 的權限——確認其有存取所需資源的權限
- 手動部署方式請見 [4-deployment.md](4-deployment.md)
