---
name: merge-operations
description: Delta MERGE 操作在流媒體中的完整指南，包含效能最佳化、平行合併和液體叢集設定。適用於實作 upsert、最佳化合併效能、對多個表格執行平行合併，或消除最佳化暫停。
---

# 流媒體中的合併操作

Delta MERGE 操作的完整指南：效能最佳化、對多個表格的平行合併，以及現代 Delta 功能（液體叢集 + 刪除向量 + 列級並行）。

## 快速開始

### 帶最佳化的基本 MERGE

```python
from delta.tables import DeltaTable

# 啟用現代 Delta 功能
spark.sql("""
    ALTER TABLE target_table SET TBLPROPERTIES (
        'delta.enableDeletionVectors' = true,
        'delta.enableRowLevelConcurrency' = true,
        'delta.liquid.clustering' = true
    )
""")

# ForEachBatch 中的 MERGE
def upsert_batch(batch_df, batch_id):
    batch_df.createOrReplaceTempView("updates")
    spark.sql("""
        MERGE INTO target_table t
        USING updates s ON t.id = s.id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    # 不需要最佳化 - 液體叢集會自動處理

stream.writeStream \
    .foreachBatch(upsert_batch) \
    .option("checkpointLocation", "/checkpoints/merge") \
    .start()
```

### 對多個表格的平行 MERGE

```python
from delta.tables import DeltaTable
from concurrent.futures import ThreadPoolExecutor, as_completed

def parallel_merge_multiple_tables(batch_df, batch_id):
    """對多個表格進行平行合併"""

    batch_df.cache()

    def merge_table(table_name, merge_key):
        target = DeltaTable.forName(spark, table_name)
        source = batch_df.alias("source")

        (target.alias("target")
            .merge(source, f"target.{merge_key} = source.{merge_key}")
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
        return f"合併 {table_name}"

    tables = [
        ("silver.customers", "customer_id"),
        ("silver.orders", "order_id"),
        ("silver.products", "product_id")
    ]

    # 平行合併
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(merge_table, table_name, merge_key): table_name
            for table_name, merge_key in tables
        }

        for future in as_completed(futures):
            future.result()  # 出錯時引發

    batch_df.unpersist()

stream.writeStream \
    .foreachBatch(parallel_merge_multiple_tables) \
    .option("checkpointLocation", "/checkpoints/parallel_merge") \
    .start()
```

## 核心概念

### 液體叢集 + DV + RLC

為最佳合併效能啟用現代 Delta 功能：

```sql
-- 為目標表格啟用
ALTER TABLE target_table SET TBLPROPERTIES (
    'delta.enableDeletionVectors' = true,
    'delta.enableRowLevelConcurrency' = true,
    'delta.liquid.clustering' = true
);
```

**優勢：**
- **刪除向量**：軟刪除而不重寫檔案
- **列級並行**：並行更新不同列
- **液體叢集**：自動最佳化無暫停
- **結果**：消除最佳化暫停、更低的 P99 延遲、更簡單的程式碼

## 常見模式

### 模式 1：帶最佳化的基本 MERGE

```python
def optimized_merge(batch_df, batch_id):
    """MERGE 並最佳化表格"""
    batch_df.createOrReplaceTempView("updates")

    spark.sql("""
        MERGE INTO target_table t
        USING updates s ON t.id = s.id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    # 不需要最佳化 - 液體叢集會處理

stream.writeStream \
    .foreachBatch(optimized_merge) \
    .option("checkpointLocation", "/checkpoints/merge") \
    .start()
```

### 模式 2：對多個表格的平行 MERGE

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def parallel_merge(batch_df, batch_id):
    """對多個表格進行平行合併"""

    batch_df.cache()

    def merge_one_table(table_name, merge_key):
        target = DeltaTable.forName(spark, table_name)
        source = batch_df.alias("source")

        (target.alias("target")
            .merge(source, f"target.{merge_key} = source.{merge_key}")
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
        return table_name

    tables = [
        ("silver.customers", "customer_id"),
        ("silver.orders", "order_id"),
        ("silver.products", "product_id")
    ]

    # 最佳執行緒計數：min(表格數，叢集核心數 / 2)
    max_workers = min(len(tables), max(2, total_cores // 2))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(merge_one_table, table_name, merge_key): table_name
            for table_name, merge_key in tables
        }

        errors = []
        for future in as_completed(futures):
            table_name = futures[future]
            try:
                future.result()
            except Exception as e:
                errors.append((table_name, str(e)))

    batch_df.unpersist()

    if errors:
        raise Exception(f"合併失敗：{errors}")
```

### 模式 3：帶分割區修剪的 MERGE

```python
def partition_pruned_merge(batch_df, batch_id):
    """MERGE 並在條件中包含分割區欄"""
    batch_df.createOrReplaceTempView("updates")

    # 在合併條件中包含分割區欄
    spark.sql("""
        MERGE INTO target_table t
        USING updates s
        ON t.id = s.id AND t.date = s.date  -- 分割區欄
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    # 跳過無關分割區以加快執行
```

### 模式 4：帶平行 MERGE 的 CDC 多目標

```python
def cdc_parallel_merge(batch_df, batch_id):
    """將 CDC 變更套用到多個表格（平行執行）"""

    batch_df.cache()

    # 按操作類型分割
    deletes = batch_df.filter(col("_op") == "DELETE")
    upserts = batch_df.filter(col("_op").isin(["INSERT", "UPDATE"]))

    def merge_cdc_table(table_name, merge_key):
        target = DeltaTable.forName(spark, table_name)

        # Upsert
        if upserts.count() > 0:
            (target.alias("target")
                .merge(upserts.alias("source"), f"target.{merge_key} = source.{merge_key}")
                .whenMatchedUpdateAll()
                .whenNotMatchedInsertAll()
                .execute()
            )

        # 刪除
        if deletes.count() > 0:
            (target.alias("target")
                .merge(deletes.alias("source"), f"target.{merge_key} = source.{merge_key}")
                .whenMatchedDelete()
                .execute()
            )

    tables = [
        ("silver.customers", "customer_id"),
        ("silver.orders", "order_id")
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(merge_cdc_table, table_name, merge_key): table_name
            for table_name, merge_key in tables
        }

        for future in as_completed(futures):
            future.result()

    batch_df.unpersist()
```

## 效能最佳化

### 啟用液體叢集 + DV + RLC

```sql
-- 使用液體叢集建立表格
CREATE TABLE target_table (
    id STRING,
    name STRING,
    updated_at TIMESTAMP
) USING DELTA
CLUSTER BY (id)
TBLPROPERTIES (
    'delta.enableDeletionVectors' = true,
    'delta.enableRowLevelConcurrency' = true
);

-- 或更改現有表格
ALTER TABLE target_table SET TBLPROPERTIES (
    'delta.enableDeletionVectors' = true,
    'delta.enableRowLevelConcurrency' = true,
    'delta.liquid.clustering' = true
);
ALTER TABLE target_table CLUSTER BY (id);
```

### 在合併鍵上進行 Z 排序

```sql
-- 在合併鍵上進行 Z 排序以加快查詢速度
OPTIMIZE target_table ZORDER BY (id);

-- 定期執行或透過預測最佳化
-- 針對目標查詢快 5-10 倍
```

### 檔案大小調整

```sql
-- 最佳合併的目標檔案大小
ALTER TABLE target_table SET TBLPROPERTIES (
    'delta.targetFileSize' = '128mb'
);
```

### 最佳執行緒計數

```python
# 公式：min(表格數，叢集核心數 / 2)
# 範例：4 個表格、8 個核心 → 4 個工作程式
# 範例：2 個表格、4 個核心 → 2 個工作程式

max_workers = min(len(tables), max(2, total_cores // 2))
```

## 監控

### 追蹤合併效能

```python
import time

def monitored_merge(batch_df, batch_id):
    start_time = time.time()

    batch_df.createOrReplaceTempView("updates")
    spark.sql("""
        MERGE INTO target_table t
        USING updates s ON t.id = s.id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)

    duration = time.time() - start_time
    print(f"合併持續時間：{duration:.2f} 秒")

    # 如果持續時間超過閾值，發出警報
    if duration > 30:
        print(f"警告：合併持續時間 {duration:.2f} 秒超過閾值")
```

## 常見問題

| 問題 | 原因 | 解決方案 |
|-------|-------|----------|
| **P99 延遲過高** | 最佳化暫停 | 啟用液體叢集（無暫停） |
| **合併衝突** | 對相同列的並行更新 | 啟用列級並行 |
| **合併速度慢** | 大型檔案，無最佳化 | 啟用液體叢集；在合併鍵上進行 Z 排序 |
| **執行緒過多** | 資源爭奪 | 減少 max_workers；符合叢集容量 |
| **部分失敗** | 一個合併失敗 | 收集所有錯誤；如有任何錯誤，則使批次失敗 |

## 生產檢查清單

- [ ] 在所有目標表格上啟用液體叢集 + DV + RLC
- [ ] 在合併鍵上設定 Z 排序
- [ ] 設定最佳執行緒計數（從 2 開始）
- [ ] 實作錯誤處理（收集所有錯誤）
- [ ] 每個表格的效能監控
- [ ] 使用快取以避免重新計算
- [ ] 在寫入後 unpersist
- [ ] 調整檔案大小（128MB 目標）

## 相關技能

- `multi-sink-writes` - 多接收器寫入模式
- `partitioning-strategy` - 合併分割區最佳化
- `checkpoint-best-practices` - 檢查點設定
