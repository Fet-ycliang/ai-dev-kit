# 領域特定指導

常見資料領域的逼真模式。所有範例均使用 Spark + Faker + Pandas UDF。

---

## 零售/電子商務

### 表格
```
customers → orders → order_items → products
```

### 關鍵模式

| 模式 | 實現 |
|------|------|
| 季節尖峰 | Q4 假日購物（11 月至 12 月時 1.5-2 倍的音量） |
| 購物車放棄 | ~70% 的購物車永遠不會完成 |
| 忠誠度層級進展 | Free → Pro → Enterprise 隨著時間 |
| 地區定價 | 按地區 5-15% 的價格變化 |

### 逼真分佈

```python
@F.pandas_udf(DoubleType())
def generate_order_amount(tiers: pd.Series) -> pd.Series:
    """按層級的電子商務訂單金額。"""
    amounts = []
    for tier in tiers:
        if tier == "Premium":
            amounts.append(float(np.random.lognormal(mean=5.5, sigma=0.9)))  # ~$245 平均
        elif tier == "Standard":
            amounts.append(float(np.random.lognormal(mean=4.2, sigma=0.7)))  # ~$67 平均
        else:  # Basic
            amounts.append(float(np.random.lognormal(mean=3.5, sigma=0.6)))  # ~$33 平均
    return pd.Series(amounts)

# 含購物車放棄的訂單狀態
status_weights = [0.70, 0.08, 0.07, 0.10, 0.05]  # 放棄、待命、處理中、已出貨、已交付
```

### 綱要範例

```python
# 產品
products_df = spark.range(0, N_PRODUCTS).select(
    F.concat(F.lit("PROD-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("product_id"),
    fake_product_name(F.col("id")).alias("name"),
    F.array(F.lit("Electronics"), F.lit("Clothing"), F.lit("Home"), F.lit("Sports"))[
        (F.rand() * 4).cast("int")
    ].alias("category"),
    generate_price(F.col("id")).alias("base_price"),
)
```

---

## 支援/CRM

### 表格
```
accounts → contacts → tickets → interactions
```

### 關鍵模式

| 模式 | 實現 |
|------|------|
| 事件尖峰 | 停機期間 3-5 倍的音量 |
| 按優先順序解決 | Critical：4 小時平均，Low：72 小時平均 |
| Enterprise 聯絡人 | 5-10 個聯絡人/帳戶，與 SMB 的 1-2 個相比 |
| 顧客滿意度相關性 | 更快解決 = 更高滿意度 |

### 逼真分佈

```python
@F.pandas_udf("struct<priority:string,resolution_hours:double,csat:int>")
def generate_ticket_metrics(tiers: pd.Series) -> pd.DataFrame:
    """支援票務指標，具有相關聯的屬性。"""
    results = []
    for tier in tiers:
        # 優先順序與層級相關
        if tier == 'Enterprise':
            priority = np.random.choice(['Critical', 'High', 'Medium'], p=[0.3, 0.5, 0.2])
        else:
            priority = np.random.choice(['Critical', 'High', 'Medium', 'Low'], p=[0.05, 0.2, 0.45, 0.3])

        # 按優先順序的解決時間（指數分佈）
        resolution_scale = {'Critical': 4, 'High': 12, 'Medium': 36, 'Low': 72}
        resolution_hours = np.random.exponential(scale=resolution_scale[priority])

        # 顧客滿意度與解決時間相關
        if resolution_hours < 4:
            csat = np.random.choice([4, 5], p=[0.3, 0.7])
        elif resolution_hours < 24:
            csat = np.random.choice([3, 4, 5], p=[0.2, 0.5, 0.3])
        else:
            csat = np.random.choice([1, 2, 3, 4], p=[0.1, 0.3, 0.4, 0.2])

        results.append({"priority": priority, "resolution_hours": round(resolution_hours, 1), "csat": int(csat)})
    return pd.DataFrame(results)
```

### 綱要範例

```python
# 具有一致屬性的票務
tickets_df = (
    spark.range(0, N_TICKETS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("TKT-"), F.lpad(F.col("id").cast("string"), 6, "0")).alias("ticket_id"),
        # 到顧客的外鍵（按層級加權）
        ...
    )
    .withColumn("metrics", generate_ticket_metrics(F.col("tier")))
    .select("*", "metrics.*")
    .drop("metrics")
)
```

---

## 製造業/IoT

### 表格
```
equipment → sensors → readings → maintenance_orders
```

### 關鍵模式

| 模式 | 實現 |
|------|------|
| 感測器生命週期 | Normal → degraded → failure 進展 |
| 異常前驅 | 異常在維護前 2-7 天發生 |
| 季節性生產 | 夏季/冬季生產變化 |
| 設備年齡 | 故障率隨著年齡增加 |

### 逼真分佈

```python
@F.pandas_udf(DoubleType())
def generate_sensor_reading(equipment_ages: pd.Series) -> pd.Series:
    """感測器讀數，具有基於年齡的衰減。"""
    readings = []
    for age_days in equipment_ages:
        # 帶有基於年齡漂移的基礎讀數
        base = 100.0
        drift = (age_days / 365) * 5  # 每年 5 個單位漂移
        noise = np.random.normal(0, 2)

        # 偶發異常（隨著年齡更可能）
        anomaly_prob = min(0.01 + (age_days / 365) * 0.02, 0.1)
        if np.random.random() < anomaly_prob:
            noise += np.random.choice([-1, 1]) * np.random.exponential(10)

        readings.append(base + drift + noise)
    return pd.Series(readings)
```

### 綱要範例

```python
# 感測器讀數時間序列
readings_df = (
    spark.range(0, N_READINGS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("READ-"), F.col("id").cast("string")).alias("reading_id"),
        # 到感測器的外鍵
        ((F.col("id") % N_SENSORS) + 1).alias("sensor_id"),
        F.date_add(F.lit(START_DATE.date()), (F.col("id") / READINGS_PER_DAY).cast("int")).alias("timestamp"),
        generate_sensor_reading(F.col("equipment_age")).alias("value"),
    )
)
```

---

## 金融服務

### 表格
```
accounts → transactions → payments → fraud_flags
```

### 關鍵模式

| 模式 | 實現 |
|------|------|
| 交易冪律 | 20% 帳戶產生 80% 的音量 |
| 詐欺模式 | 異常時間、金額、位置 |
| 餘額一致性 | 交易維持正餘額 |
| 監管合規 | 無負餘額、有效金額 |

### 逼真分佈

```python
@F.pandas_udf(DoubleType())
def generate_transaction_amount(account_types: pd.Series) -> pd.Series:
    """按帳戶類型遵循冪律的交易金額。"""
    amounts = []
    for acct_type in account_types:
        if acct_type == "Corporate":
            # 企業冪律（少數大額交易）
            amount = (np.random.pareto(a=1.5) + 1) * 1000
        elif acct_type == "Premium":
            amount = np.random.lognormal(mean=6, sigma=1.2)
        else:  # Standard
            amount = np.random.lognormal(mean=4, sigma=0.8)
        amounts.append(min(amount, 1_000_000))  # 上限 $1M
    return pd.Series(amounts)

@F.pandas_udf(BooleanType())
def generate_fraud_flag(amounts: pd.Series, hours: pd.Series) -> pd.Series:
    """根據金額和時間標記可疑交易。"""
    flags = []
    for amount, hour in zip(amounts, hours):
        # 更高詐欺概率：大金額 + 異常時間
        base_prob = 0.001
        if amount > 5000:
            base_prob *= 3
        if hour < 6 or hour > 22:
            base_prob *= 2
        flags.append(np.random.random() < base_prob)
    return pd.Series(flags)
```

### 綱要範例

```python
# 具有詐欺指標的交易
transactions_df = (
    spark.range(0, N_TRANSACTIONS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("TXN-"), F.lpad(F.col("id").cast("string"), 10, "0")).alias("transaction_id"),
        # 到帳戶的外鍵
        ...
        generate_transaction_amount(F.col("account_type")).alias("amount"),
        F.hour(F.col("timestamp")).alias("hour"),
    )
    .withColumn("is_suspicious", generate_fraud_flag(F.col("amount"), F.col("hour")))
)
```

---

## 一般最佳實踐

1. **從領域表格開始**：首先定義核心實體和關係
2. **新增領域特定分佈**：對領域使用逼真統計模式
3. **包含邊界案例**：每個領域都有邊界案例（退貨、取消、故障）
4. **基於時間的模式很重要**：大多數領域都有每日/每週/季節模式
5. **相關聯屬性**：列內的屬性應在業務上有意義

**注意：** 這些是指導模式，不是嚴格的綱要。根據使用者的特定要求進行調整。
