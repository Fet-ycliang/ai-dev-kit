# 設定和執行指南

本指南涵蓋所有合成資料產生的執行模式，依 Databricks Connect 版本和 Python 版本進行組織。

## 快速決策矩陣

| 您的環境 | 建議方法 |
|----------|---------|
| Python 3.12+ 搭配 databricks-connect >= 16.4 | 使用 withDependencies API 的 DatabricksEnv |
| Python 3.10/3.11 搭配舊版 databricks-connect | 使用 environments 參數的無伺服器工作 |
| 經典計算叢集（僅作為備用） | 手動叢集設定 |

## 選項 1：Databricks Connect 16.4+ 搭配無伺服器計算（推薦）

**適用於：** Python 3.12+、本地開發搭配無伺服器計算

**在本地安裝：**
```bash
# 首選
uv pip install "databricks-connect>=16.4,<17.4" faker numpy pandas holidays

# 若 uv 不可用則使用備用方案
pip install "databricks-connect>=16.4,<17.4" faker numpy pandas holidays
```

**設定 ~/.databrickscfg：**
```ini
[DEFAULT]
host = https://your-workspace.cloud.databricks.com/
serverless_compute_id = auto
auth_type = databricks-cli
```

**在您的指令碼中：**
```python
from databricks.connect import DatabricksSession, DatabricksEnv

# 將相依性傳遞為簡單的套件名稱字串
env = DatabricksEnv().withDependencies("faker", "pandas", "numpy", "holidays")

# 建立使用受管理相依性的工作階段
spark = (
    DatabricksSession.builder
    .withEnvironment(env)
    .serverless(True)
    .getOrCreate()
)

# Spark 操作現在在無伺服器計算上執行，具有受管理相依性
```

**版本檢測（如需要）：**
```python
import importlib.metadata

def get_databricks_connect_version():
    """取得 databricks-connect 版本為 (major, minor) 元組。"""
    try:
        version_str = importlib.metadata.version('databricks-connect')
        parts = version_str.split('.')
        return (int(parts[0]), int(parts[1]))
    except Exception:
        return None

db_version = get_databricks_connect_version()
if db_version and db_version >= (16, 4):
    # 使用 DatabricksEnv 搭配 withDependencies
    pass
```

**優點：**
- 瞬間啟動，無需等待叢集
- 本地偵錯和快速迭代
- 自動相依性管理
- 編輯檔案、立即重新執行

## 選項 2：舊版 Databricks Connect 或 Python < 3.12

**適用於：** Python 3.10/3.11、databricks-connect 15.1-16.3

舊版本中不提供 `DatabricksEnv()` 和 `withEnvironment()`。改用使用 environments 參數的無伺服器工作。

### 無伺服器工作設定需求

**必須在環境規格中使用 `"client": "4"`：**

```json
{
  "environments": [{
    "environment_key": "datagen_env",
    "spec": {
      "client": "4",
      "dependencies": ["faker", "numpy", "pandas"]
    }
  }]
}
```

> **注意：** 使用 `"client": "1"` 將導致環境設定錯誤失敗。

### 指令碼部署

將 Python 檔案 (.py) 部署到工作區供無伺服器工作使用：

```bash
databricks workspace import /Users/<user>@databricks.com/scripts/my_script.py \
  --file ./my_script.py --format AUTO

databricks workspace list /Users/<user>@databricks.com/scripts/
```

**工作設定必須參考工作區路徑：**

```json
{
  "spark_python_task": {
    "python_file": "/Users/<user>@databricks.com/scripts/my_script.py"
  },
  "environment_key": "datagen_env"
}
```

**DABs 套件設定：**
```yaml
# databricks.yml
bundle:
  name: synthetic-data-gen

resources:
  jobs:
    generate_data:
      name: "產生合成資料"
      tasks:
        - task_key: generate
          spark_python_task:
            python_file: ./src/generate_data.py
          environment_key: default

environments:
  default:
    spec:
      client: "4"
      dependencies:
        - faker
        - numpy
        - pandas
        - holidays
```

## 選項 3：經典叢集

**使用時機：** 無伺服器無法使用，或需要特定叢集功能（GPU、自訂初始化指令碼）

### 步驟 1：檢查 Python 版本相容性

Pandas UDF 需要本地和叢集之間的 Python 次要版本相符。

```bash
# 檢查本地 Python
uv run python --version  # 或：python --version

# 檢查叢集 DBR 版本 → Python 版本
# DBR 17.x = Python 3.12
# DBR 15.4 LTS = Python 3.11
# DBR 14.3 LTS = Python 3.10
databricks clusters get <cluster-id> | grep spark_version
```

### 步驟 2a：如果版本相符 → 使用 Databricks Connect

```bash
# 安裝相符的 databricks-connect 版本（必須符合 DBR 主要版本.次要版本）
uv pip install "databricks-connect==17.3.*" faker numpy pandas holidays
```

```bash
# 在叢集上安裝程式庫
databricks libraries install --json '{"cluster_id": "<cluster-id>", "libraries": [{"pypi": {"package": "faker"}}, {"pypi": {"package": "holidays"}}]}'

# 等待 INSTALLED 狀態
databricks libraries cluster-status <cluster-id>
```

```python
# 透過 Databricks Connect 在本地執行
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.clusterId("<cluster-id>").getOrCreate()
# 您的 Spark 程式碼在叢集上執行
```

### 步驟 2b：如果版本不符 → 作為工作提交

**提交前請要求使用者批准。** 範例提示：
> "您的本地 Python (3.11) 與叢集 (3.12) 不符。Pandas UDF 需要版本相符。應該改為將其作為工作提交到叢集上直接執行嗎？"

```bash
# 上傳指令碼到工作區
databricks workspace import /Users/you@company.com/scripts/generate_data.py \
  --file generate_data.py --format AUTO --overwrite

# 提交工作到叢集執行
databricks jobs submit --json '{
  "run_name": "產生資料",
  "tasks": [{
    "task_key": "generate",
    "existing_cluster_id": "<cluster-id>",
    "spark_python_task": {
      "python_file": "/Users/you@company.com/scripts/generate_data.py"
    }
  }]
}'
```

### 經典叢集決策流程

```
本地 Python == 叢集 Python？
  ├─ 是 → 在叢集上安裝程式庫，透過 Databricks Connect 執行
  └─ 否 → 詢問使用者：「改為提交作為工作？」
           └─ 上傳指令碼 + 提交工作
```

## 必需程式庫

用於產生逼真合成資料的標準程式庫：

| 程式庫 | 目的 | 所需條件 |
|--------|------|---------|
| **faker** | 逼真的名字、地址、電子郵件、公司 | 文字資料產生 |
| **numpy** | 統計分佈 | 非線性分佈 |
| **pandas** | 資料操作、Pandas UDF | Spark UDF 定義 |
| **holidays** | 國家特定假日日曆 | 基於時間的模式 |

## 環境檢測模式

使用此模式自動偵測環境並選擇正確的工作階段建立方式：

```python
import os
import importlib.metadata

def is_databricks_runtime():
    """檢查是否在 Databricks Runtime 上執行，相對於本地。"""
    return "DATABRICKS_RUNTIME_VERSION" in os.environ

def get_databricks_connect_version():
    """取得 databricks-connect 版本為 (major, minor) 元組或 None。"""
    try:
        version_str = importlib.metadata.version('databricks-connect')
        parts = version_str.split('.')
        return (int(parts[0]), int(parts[1]))
    except Exception:
        return None

on_runtime = is_databricks_runtime()
db_version = get_databricks_connect_version()

# 使用 DatabricksEnv 如果：本地 + databricks-connect >= 16.4
use_auto_dependencies = (not on_runtime) and db_version and db_version >= (16, 4)

if use_auto_dependencies:
    from databricks.connect import DatabricksSession, DatabricksEnv
    env = DatabricksEnv().withDependencies("faker", "pandas", "numpy", "holidays")
    spark = DatabricksSession.builder.withEnvironment(env).serverless(True).getOrCreate()
else:
    from databricks.connect import DatabricksSession
    spark = DatabricksSession.builder.serverless(True).getOrCreate()
```

## 常見設定問題

| 問題 | 解決方案 |
|------|--------|
| `ModuleNotFoundError: faker` | 依執行模式安裝相依性 |
| `DatabricksEnv not found` | 升級到 databricks-connect >= 16.4 或使用具 environments 的工作 |
| `serverless_compute_id` 錯誤 | 在 ~/.databrickscfg 中新增 `serverless_compute_id = auto` |
| 經典叢集啟動緩慢 | 改用無伺服器計算（瞬間啟動） |
