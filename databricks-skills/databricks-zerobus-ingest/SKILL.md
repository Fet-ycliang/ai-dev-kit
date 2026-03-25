---
name: databricks-zerobus-ingest
description: "透過 gRPC 建立 Zerobus Ingest 客戶端，以便將資料近即時攝取到 Databricks Delta 資料表。當建立可直接寫入 Unity Catalog 資料表而不需訊息匯流排的 producer、在 Python/Java/Go/TypeScript/Rust 中使用 Zerobus Ingest SDK、從 UC 資料表產生 Protobuf 結構描述，或實作具 ACK 處理與重試邏輯的 stream 型攝取時使用。"
---

# Zerobus Ingest

建立透過 Zerobus gRPC API 直接將資料攝取至 Databricks Delta 資料表的客戶端。

**狀態:** GA（自 2026 年 2 月起正式可用；依 Lakeflow Jobs Serverless SKU 計費）

**文件:**
- [Zerobus 總覽](https://docs.databricks.com/aws/en/ingestion/zerobus-overview)
- [Zerobus Ingest SDK](https://docs.databricks.com/aws/en/ingestion/zerobus-ingest)
- [Zerobus 限制](https://docs.databricks.com/aws/en/ingestion/zerobus-limits)

---

## 什麼是 Zerobus Ingest？

Zerobus Ingest 是一種 serverless connector，可讓你透過 gRPC 直接逐筆將資料攝取到 Delta 資料表。它免除了將資料送往 lakehouse 時所需的訊息匯流排基礎架構（Kafka、Kinesis、Event Hub）。此服務會驗證結構描述、將資料具體化到目標資料表，並將持久性確認回傳給客戶端。

**核心模式:** SDK 初始化 -> 建立 stream -> 攝取記錄 -> 處理 ACK -> flush -> close

---

## 快速判斷：你要建立什麼？

| 場景 | 語言 | 序列化 | 參考 |
|----------|----------|---------------|-----------|
| 快速原型 / 測試 harness | Python | JSON | [2-python-client.md](2-python-client.md) |
| 正式環境 Python producer | Python | Protobuf | [2-python-client.md](2-python-client.md) + [4-protobuf-schema.md](4-protobuf-schema.md) |
| JVM 微服務 | Java | Protobuf | [3-multilanguage-clients.md](3-multilanguage-clients.md) |
| Go 服務 | Go | JSON 或 Protobuf | [3-multilanguage-clients.md](3-multilanguage-clients.md) |
| Node.js / TypeScript 應用程式 | TypeScript | JSON | [3-multilanguage-clients.md](3-multilanguage-clients.md) |
| 高效能系統服務 | Rust | JSON 或 Protobuf | [3-multilanguage-clients.md](3-multilanguage-clients.md) |
| 從 UC 資料表產生結構描述 | Any | Protobuf | [4-protobuf-schema.md](4-protobuf-schema.md) |
| 重試 / 重新連線邏輯 | Any | Any | [5-operations-and-limits.md](5-operations-and-limits.md) |

若未特別指定，預設使用 python。

---

## 常用函式庫

以下函式庫是 ZeroBus 資料攝取的必要項目：

- **databricks-sdk>=0.85.0**：用於認證與中繼資料的 Databricks workspace client
- **databricks-zerobus-ingest-sdk>=1.0.0**：用於高效能 streaming 攝取的 ZeroBus SDK
- **grpcio-tools**
這些套件通常不會預先安裝在 Databricks 上。請使用 `execute_databricks_command` 工具安裝：
- `code`: "%pip install databricks-sdk>=VERSION databricks-zerobus-ingest-sdk>=VERSION"

請保存回傳的 `cluster_id` 與 `context_id` 供後續呼叫使用。

智慧安裝方式

# 先檢查 protobuf 版本，再安裝相容的
grpcio-tools
import google.protobuf
runtime_version = google.protobuf.__version__
print(f"執行階段 protobuf 版本: {runtime_version}")

if runtime_version.startswith("5.26") or
runtime_version.startswith("5.29"):
    %pip install grpcio-tools==1.62.0
else:
    %pip install grpcio-tools  # 對較新的 protobuf 使用最新版
版本
---

## 必要條件

在確認以下項目有效之前，絕不可執行此 skill：

1. **可供攝取的 Unity Catalog managed Delta 資料表**
2. **具有目標資料表 `MODIFY` 與 `SELECT` 權限的 service principal id 與 secret**
3. **你工作區所在區域的 Zerobus 伺服器端點**
4. **已為目標語言安裝的 Zerobus Ingest SDK**

完整設定指引請參閱 [1-setup-and-authentication.md](1-setup-and-authentication.md)。

---

## 最小 Python 範例（JSON）

```python
import json
from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import RecordType, StreamConfigurationOptions, TableProperties

sdk = ZerobusSdk(server_endpoint, workspace_url)
options = StreamConfigurationOptions(record_type=RecordType.JSON)
table_props = TableProperties(table_name)

stream = sdk.create_stream(client_id, client_secret, table_props, options)
try:
    record = {"device_name": "sensor-1", "temp": 22, "humidity": 55}
    stream.ingest_record(json.dumps(record))
    stream.flush()
finally:
    stream.close()
```

---

## 詳細指南

| 主題 | 檔案 | 適合閱讀時機 |
|-------|------|--------------|
| 設定與認證 | [1-setup-and-authentication.md](1-setup-and-authentication.md) | 端點格式、service principal、SDK 安裝 |
| Python 客戶端 | [2-python-client.md](2-python-client.md) | 同步/非同步 Python、JSON 與 Protobuf 流程、可重用的 client 類別 |
| 多語言 | [3-multilanguage-clients.md](3-multilanguage-clients.md) | Java、Go、TypeScript、Rust SDK 範例 |
| Protobuf 結構描述 | [4-protobuf-schema.md](4-protobuf-schema.md) | 從 UC 資料表產生 .proto、編譯、型別對應 |
| 操作與限制 | [5-operations-and-limits.md](5-operations-and-limits.md) | ACK 處理、重試、重新連線、吞吐量限制、約束 |

---

你必須始終遵循 Workflow 中的所有步驟

## Workflow
0. **顯示你的執行計畫**
1. **判定客戶端類型**
2. **取得結構描述** 一律使用 4-protobuf-schema.md。使用 `run_python_file_on_databricks` MCP 工具執行
3. **將 Python 程式碼寫入專案中的本機檔案，並依照相關指南使用 zerobus 攝取**（例如 `scripts/zerobus_ingest.py`）。
4. **使用 `run_python_file_on_databricks` MCP 工具在 Databricks 上執行**
5. **若執行失敗**：編輯本機檔案修正錯誤，然後重新執行
6. **重用 context**：傳入回傳的 `cluster_id` 與 `context_id` 以供後續執行

---

## 重要事項
- 永遠不要安裝本機套件
- 執行前一律驗證 MCP 伺服器需求
- **Serverless 限制**：Zerobus SDK 無法在 serverless compute 上以 pip 安裝。請改用 classic compute clusters，或在 notebook 中使用 [Zerobus REST API](https://docs.databricks.com/aws/en/ingestion/zerobus-rest-api)（Beta）進行無 SDK 的資料攝取。
- **明確的資料表授權**：Service principal 需要在目標資料表上明確具備 `MODIFY` 與 `SELECT` 授權。對 `authorization_details` OAuth flow 而言，schema 層級繼承的權限可能不足。

---

### Context 重用模式

第一次執行會自動選擇一個執行中的 cluster，並建立 execution context。**請在後續呼叫中重用這個 context** —— 速度會快很多（約 1 秒對比約 15 秒），而且會共享變數與匯入內容：

**第一次執行** - 使用 `run_python_file_on_databricks` 工具：
- `file_path`: "scripts/zerobus_ingest.py"

回傳：`{ success, output, error, cluster_id, context_id, ... }`

請保存 `cluster_id` 與 `context_id` 供後續呼叫使用。

**若執行失敗：**
1. 從結果中讀取錯誤
2. 編輯本機 Python 檔案以修正問題
3. 使用相同的 context 透過 `run_python_file_on_databricks` 工具重新執行：
   - `file_path`: "scripts/zerobus_ingest.py"
   - `cluster_id`: "<saved_cluster_id>"
   - `context_id`: "<saved_context_id>"

**後續執行**會重用這個 context（更快，且會共享狀態）：
- `file_path`: "scripts/validate_ingestion.py"
- `cluster_id`: "<saved_cluster_id>"
- `context_id`: "<saved_context_id>"

### 處理失敗情況

當執行失敗時：
1. 從結果中讀取錯誤
2. **編輯本機 Python 檔案**以修正問題
3. 使用相同的 `cluster_id` 與 `context_id` 重新執行（更快，且保留已安裝函式庫）
4. 若 context 已損壞，省略 `context_id` 以建立新的 context

---

### 安裝函式庫

Databricks 預設提供 Spark、pandas、numpy 與常見資料函式庫。**只有在發生 import 錯誤時才安裝函式庫。**

使用 `execute_databricks_command` 工具：
- `code`: "%pip install databricks-zerobus-ingest-sdk>=1.0.0"
- `cluster_id`: "<cluster_id>"
- `context_id`: "<context_id>"

該函式庫會立即在同一個 context 中可用。

**注意：** 持續使用相同的 `context_id`，表示已安裝的函式庫會在多次呼叫之間保留。

## 🚨 關鍵經驗：Timestamp 格式修正

**重大發現**：ZeroBus 要求 **timestamp 欄位必須是 Unix 整數 timestamp**，**不是**字串 timestamp。
針對 Databricks，timestamp 的產生必須使用微秒。

---

## 關鍵概念

- **gRPC + Protobuf**：Zerobus 使用 gRPC 作為傳輸協定。任何能透過 gRPC 通訊並建構 Protobuf 訊息的應用程式，都可以將資料寫入 Zerobus。
- **JSON 或 Protobuf 序列化**：JSON 適合快速開始；Protobuf 則提供型別安全、向前相容與較佳效能。
- **至少一次傳遞**：此 connector 提供至少一次傳遞保證。請將 consumer 設計成可處理重複資料。
- **持久性 ACK**：每筆攝取的記錄都會回傳 `RecordAcknowledgment`。使用 `flush()` 可確保所有緩衝記錄都已持久化寫入，或使用 `wait_for_offset(offset)` 進行以 offset 為基礎的追蹤。
- **不管理資料表**：Zerobus 不會建立或變更資料表。你必須先建立目標資料表，並自行管理結構描述演進。
- **單一 AZ 持久性**：此服務在單一 availability zone 中運作。請為可能的 zone 中斷做好規劃。

---

## 常見問題

| 問題 | 解法 |
|-------|----------|
| **連線被拒絕** | 確認伺服器端點格式與你的雲端環境相符（AWS 或 Azure）。檢查防火牆 allowlist。 |
| **認證失敗** | 確認 service principal 的 client_id/secret。驗證目標資料表上的 GRANT 陳述式。 |
| **結構描述不相符** | 確保記錄欄位與目標資料表結構描述完全一致。若資料表已變更，請重新產生 .proto。 |
| **Stream 意外關閉** | 請實作具指數退避的重試與 stream 重新初始化。請參閱 [5-operations-and-limits.md](5-operations-and-limits.md)。 |
| **觸及吞吐量限制** | 每個 stream 上限為 100 MB/s 與 15,000 rows/s。請開啟多個 streams，或聯絡 Databricks。 |
| **區域不受支援** | 請檢查 [5-operations-and-limits.md](5-operations-and-limits.md) 中的支援區域。 |
| **找不到資料表** | 確認資料表是位於支援區域中的 managed Delta 資料表，且使用正確的三段式名稱。 |
| **在 serverless 上安裝 SDK 失敗** | Zerobus SDK 無法在 serverless compute 上以 pip 安裝。請改用 classic compute clusters，或從 notebook 使用 REST API（Beta）。 |
| **Error 4024 / authorization_details** | Service principal 缺少明確的資料表層級授權。請直接在目標資料表上授與 `MODIFY` 與 `SELECT` —— schema 層級繼承的授權可能不足。 |

---

## 相關 Skills

- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - 一般 SDK 模式，以及用於資料表/結構描述管理的 WorkspaceClient
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - 對已攝取資料進行下游管線處理
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - 管理 Zerobus 會寫入的 catalogs、schemas 與 tables
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - 產生可供 Zerobus producer 使用的測試資料
- **[databricks-config](../databricks-config/SKILL.md)** - Profile 與認證設定

## 資源

- [Zerobus 總覽](https://docs.databricks.com/aws/en/ingestion/zerobus-overview)
- [Zerobus Ingest SDK](https://docs.databricks.com/aws/en/ingestion/zerobus-ingest)
- [Zerobus 限制](https://docs.databricks.com/aws/en/ingestion/zerobus-limits)
