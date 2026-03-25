# 疑難排除指南

合成資料產生的常見問題和解決方案。

## 環境問題

### ModuleNotFoundError: faker（或其他程式庫）

**問題：** 依賴性在執行環境中不可用。

**依執行模式提供解決方案：**

| 模式 | 解決方案 |
|------|---------|
| **DB Connect 16.4+** | 使用 `DatabricksEnv().withDependencies("faker", "pandas", ...)` |
| **舊版 DB Connect 搭配無伺服器** | 建立具有 `environments` 參數的工作 |
| **Databricks Runtime** | 使用 Databricks CLI 安裝 `faker holidays` |
| **經典叢集** | 使用 Databricks CLI 安裝程式庫。`databricks libraries install --json '{"cluster_id": "<cluster_id>", "libraries": [{"pypi": {"package": "faker"}}, {"pypi": {"package": "holidays"}}]}'` |

```python
# 對 DB Connect 16.4+
from databricks.connect import DatabricksSession, DatabricksEnv

env = DatabricksEnv().withDependencies("faker", "pandas", "numpy", "holidays")
spark = DatabricksSession.builder.withEnvironment(env).serverless(True).getOrCreate()
```

### DatabricksEnv 未找到

**問題：** 使用舊版 databricks-connect 版本。

**解決方案：** 升級到 16.4+ 或使用工作型方法：

```bash
# 升級（偏好 uv，回退到 pip）
uv pip install "databricks-connect>=16.4,<17.4"
# 或：pip install "databricks-connect>=16.4,<17.4"

# 或改用具 environments 參數的工作
```

### serverless_compute_id 錯誤

**問題：** 遺失無伺服器設定。

**解決方案：** 新增到 `~/.databrickscfg`：

```ini
[DEFAULT]
host = https://your-workspace.cloud.databricks.com/
serverless_compute_id = auto
auth_type = databricks-cli
```

---

## 執行問題

### 重要：無伺服器上不支援 cache() 和 persist()

**問題：** 在無伺服器計算上使用 `.cache()` 或 `.persist()` 失敗，錯誤為：
```
AnalysisException: [NOT_SUPPORTED_WITH_SERVERLESS] PERSIST TABLE is not supported on serverless compute.
```

**為什麼發生：** 無伺服器計算不支援在記憶體中快取 DataFrame。這是無伺服器架構的基本限制。

**解決方案：** 先將主表格寫入 Delta，然後讀取以進行外鍵連接：

```python
# 不好 - 會在無伺服器上失敗
customers_df = spark.range(0, N_CUSTOMERS)...
customers_df.cache()  # ❌ 失敗：「PERSIST TABLE is not supported on serverless compute」

# 好 - 寫入 Delta，然後讀取
customers_df = spark.range(0, N_CUSTOMERS)...
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
customer_lookup = spark.table(f"{CATALOG}.{SCHEMA}.customers")  # ✓ 從 Delta 讀取
```

**參照完整性最佳實踐：**
1. 產生主表格（例如顧客）
2. 寫入 Delta 表格
3. 讀取以進行外鍵查詢連接
4. 使用有效外鍵產生子表格（例如訂單、票務）
5. 將子表格寫入 Delta

---

### 無伺服器工作無法啟動

**可能原因：**
1. 工作區未啟用無伺服器
2. 統一目錄權限遺失
3. 無效的環境設定

**解決方案：**
```python
# 驗證無伺服器可用
# 先嘗試建立簡單工作進行測試

# 檢查統一目錄權限
spark.sql("SELECT current_catalog(), current_schema()")
```

### 經典叢集啟動緩慢（3-8 分鐘）

**問題：** 叢集需要時間啟動。

**解決方案：** 切換到無伺服器：

```python
# 不是：
# spark = DatabricksSession.builder.clusterId("xxx").getOrCreate()

# 使用：
spark = DatabricksSession.builder.serverless(True).getOrCreate()
```

### 「必須提供基礎環境或版本」

**問題：** 工作環境規格中遺失 `client`。

**解決方案：** 在規格中新增 `"client": "4"`：

```python
{
  "environments": [{
    "environment_key": "datagen_env",
    "spec": {
      "client": "4",  # 必需！
      "dependencies": ["faker", "numpy", "pandas"]
    }
  }]
}
```

---

## 資料產生問題

### AttributeError：'function' 物件沒有屬性 'partitionBy'

**問題：** 對分析視窗函式使用 `F.window` 而不是 `Window`。

```python
# 錯誤 - F.window 用於基於時間的翻轉/滑動視窗（串流）
window_spec = F.window.partitionBy("account_id").orderBy("contact_id")
# 錯誤：AttributeError：'function' 物件沒有屬性 'partitionBy'

# 正確 - Window 用於分析視窗規格
from pyspark.sql.window import Window
window_spec = Window.partitionBy("account_id").orderBy("contact_id")
```

**何時使用 Window：** 用於分析函式，例如 `row_number()`、`rank()`、`lead()`、`lag()`：

```python
from pyspark.sql.window import Window

# 將每個帳戶的第一個聯絡人標記為主要
window_spec = Window.partitionBy("account_id").orderBy("contact_id")
contacts_df = contacts_df.withColumn(
    "is_primary",
    F.row_number().over(window_spec) == 1
)
```

---

### Faker UDF 很慢

**問題：** 單列 UDF 無法良好平行化。

**解決方案：** 使用 `pandas_udf` 進行批次處理：

```python
# 慢 - 標量 UDF
@F.udf(returnType=StringType())
def slow_fake_name():
    return Faker().name()

# 快 - pandas UDF（批次處理）
@F.pandas_udf(StringType())
def fast_fake_name(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.name() for _ in range(len(ids))])
```

### 大型資料記憶體不足

**問題：** 資料大小的分區不足。

**解決方案：** 增加分區：

```python
# 針對大型資料集（1M+ 列）
customers_df = spark.range(0, N_CUSTOMERS, numPartitions=64)  # 從預設值增加
```

| 資料大小 | 建議分區數 |
|---------|----------|
| < 100K | 8 |
| 100K - 500K | 16 |
| 500K - 1M | 32 |
| 1M+ | 64+ |

### 經典叢集上的內容已損毀

**問題：** 陳舊的執行內容。

**解決方案：** 建立新鮮內容（省略 context_id），重新安裝程式庫：

```python
# 如果看到奇怪的錯誤，不要重複使用 context_id
# 讓它建立新內容
```

### 參照完整性違規

**問題：** 外鍵參考不存在的父記錄。

**解決方案：** 先將主表格寫入 Delta，然後讀取以進行外鍵連接：

```python
# 1. 產生並寫入主表格（不要搭配無伺服器計算使用 cache！）
customers_df = spark.range(0, N_CUSTOMERS)...
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# 2. 讀取以進行外鍵查詢
customer_lookup = spark.table(f"{CATALOG}.{SCHEMA}.customers").select("customer_id", "tier")

# 3. 使用有效外鍵產生子表格
orders_df = spark.range(0, N_ORDERS).join(
    customer_lookup,
    on=<mapping_condition>,
    how="left"
)
```

> **警告：** 不要搭配無伺服器計算使用 `.cache()` 或 `.persist()`。請參閱上面的專用章節。

---

## 資料品質問題

### 均勻分佈（不逼真）

**問題：** 所有顧客都有相似的訂單計數，金額均勻分佈。

**解決方案：** 使用非線性分佈：

```python
# 不好 - 均勻
amounts = np.random.uniform(10, 1000, N)

# 好 - 對數常態（逼真）
amounts = np.random.lognormal(mean=5, sigma=0.8, N)
```

### 遺失基於時間的模式

**問題：** 資料不反映工作日/週末或季節模式。

**解決方案：** 新增乘數：

```python
import holidays

US_HOLIDAYS = holidays.US(years=[2024, 2025])

def get_multiplier(date):
    mult = 1.0
    if date.weekday() >= 5:  # 週末
        mult *= 0.6
    if date in US_HOLIDAYS:
        mult *= 0.3
    return mult
```

### 列屬性不一致

**問題：** Enterprise 顧客有低價值訂單，critical 票務解決緩慢。

**解決方案：** 相關聯屬性：

```python
# 基於層級的優先順序
if tier == 'Enterprise':
    priority = np.random.choice(['Critical', 'High'], p=[0.4, 0.6])
else:
    priority = np.random.choice(['Medium', 'Low'], p=[0.6, 0.4])

# 基於優先順序的解決
resolution_scale = {'Critical': 4, 'High': 12, 'Medium': 36, 'Low': 72}
resolution_hours = np.random.exponential(scale=resolution_scale[priority])
```

---

## 驗證步驟

產生後驗證資料：

```python
# 1. 檢查列計數
print(f"顧客：{customers_df.count():,}")
print(f"訂單：{orders_df.count():,}")

# 2. 驗證分佈
customers_df.groupBy("tier").count().show()
orders_df.describe("amount").show()

# 3. 檢查參照完整性
orphans = orders_df.join(
    customers_df,
    orders_df.customer_id == customers_df.customer_id,
    "left_anti"
)
print(f"孤立訂單：{orphans.count()}")

# 4. 驗證日期範圍
orders_df.select(F.min("order_date"), F.max("order_date")).show()
```
