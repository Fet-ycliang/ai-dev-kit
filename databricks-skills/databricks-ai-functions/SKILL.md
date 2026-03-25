---
name: databricks-ai-functions
description: "使用 Databricks 內建 AI Functions（ai_classify, ai_extract, ai_summarize, ai_mask, ai_translate, ai_fix_grammar, ai_gen, ai_analyze_sentiment, ai_similarity, ai_parse_document, ai_query, ai_forecast）直接為 SQL 與 PySpark 管線加入 AI 功能，無需管理模型端點。也涵蓋文件解析與建立自訂 RAG 管線（parse → chunk → index → query）。"
---

# Databricks AI Functions

> **官方文件：** https://docs.databricks.com/aws/en/large-language-models/ai-functions
> 各函式參考：https://docs.databricks.com/aws/en/sql/language-manual/functions/

## 概覽

Databricks AI Functions 是內建的 SQL 與 PySpark 函式，可直接從資料管線呼叫基礎模型 API——無需設定模型端點、無需 API 金鑰，也無需樣板程式碼。它們能像 `UPPER()` 或 `LENGTH()` 一樣自然地作用於資料表欄位，並針對大規模批次推論進行最佳化。

分為三種類別：

| 類別 | Functions | 使用時機 |
|---|---|---|
| **任務專用** | `ai_analyze_sentiment`, `ai_classify`, `ai_extract`, `ai_fix_grammar`, `ai_gen`, `ai_mask`, `ai_similarity`, `ai_summarize`, `ai_translate`, `ai_parse_document` | 任務定義明確時——請一律優先使用 |
| **通用型** | `ai_query` | 複雜巢狀 JSON、自訂端點、多模態——僅作為最後手段 |
| **資料表值型** | `ai_forecast` | 時間序列預測 |

**函式選擇規則——永遠優先使用任務專用函式，而不是 `ai_query`：**

| 任務 | 使用此函式 | 在以下情況改用 `ai_query`... |
|---|---|---|
| 情緒評分 | `ai_analyze_sentiment` | 不需要 |
| 固定標籤路由 | `ai_classify` (2–20 個標籤) | 不需要 |
| 平面實體擷取 | `ai_extract` | 輸出結構描述含有巢狀陣列 |
| 摘要 | `ai_summarize` | 不需要——要無上限請用 `max_words=0` |
| 文法修正 | `ai_fix_grammar` | 不需要 |
| 翻譯 | `ai_translate` | 目標語言不在支援清單中 |
| PII 遮罩 | `ai_mask` | 不需要 |
| 自由格式生成 | `ai_gen` | 需要結構化 JSON 輸出 |
| 語意相似度 | `ai_similarity` | 不需要 |
| PDF／文件解析 | `ai_parse_document` | 需要影像層級推理 |
| 複雜 JSON／推理 | — | **這就是 `ai_query` 的預期使用情境** |

## 前置條件

- Databricks SQL warehouse（**非 Classic**）或 DBR **15.1+** 的叢集
- 批次工作負載建議使用 DBR **15.4 ML LTS**
- `ai_parse_document` 需要 DBR **17.1+**
- `ai_forecast` 需要 **Pro 或 Serverless** SQL warehouse
- 工作區必須位於支援批次 AI 推論的 AWS/Azure 區域
- 模型依 Apache 2.0 或 LLAMA 3.3 Community License 執行——客戶需自行負責合規性

## 快速入門

在單一查詢中，對文字欄位進行分類、擷取與情緒評分：

```sql
SELECT
    ticket_id,
    ticket_text,
    ai_classify(ticket_text, ARRAY('urgent', 'not urgent', 'spam')) AS priority,
    ai_extract(ticket_text, ARRAY('product', 'error_code', 'date'))  AS entities,
    ai_analyze_sentiment(ticket_text)                                 AS sentiment
FROM support_tickets;
```

```python
from pyspark.sql.functions import expr

df = spark.table("support_tickets")
df = (
    df.withColumn("priority",  expr("ai_classify(ticket_text, array('urgent', 'not urgent', 'spam'))"))
      .withColumn("entities",  expr("ai_extract(ticket_text, array('product', 'error_code', 'date'))"))
      .withColumn("sentiment", expr("ai_analyze_sentiment(ticket_text)"))
)
# 從 ai_extract 存取巢狀 STRUCT 欄位
df.select("ticket_id", "priority", "sentiment",
          "entities.product", "entities.error_code", "entities.date").display()
```

## 常見模式

### 模式 1：文字分析管線

將多個任務專用函式串接起來，一次豐富化文字欄位：

```sql
SELECT
    id,
    content,
    ai_analyze_sentiment(content)               AS sentiment,
    ai_summarize(content, 30)                   AS summary,
    ai_classify(content,
        ARRAY('technical', 'billing', 'other')) AS category,
    ai_fix_grammar(content)                     AS content_clean
FROM raw_feedback;
```

### 模式 2：儲存前先做 PII 遮罩

```python
from pyspark.sql.functions import expr

df_clean = (
    spark.table("raw_messages")
    .withColumn(
        "message_safe",
        expr("ai_mask(message, array('person', 'email', 'phone', 'address'))")
    )
)
df_clean.write.format("delta").mode("append").saveAsTable("catalog.schema.messages_safe")
```

### 模式 3：從 Unity Catalog Volume 進行文件擷取

解析 PDF/Office 文件，再用任務專用函式進行豐富化：

```python
from pyspark.sql.functions import expr

df = (
    spark.read.format("binaryFile")
    .load("/Volumes/catalog/schema/landing/documents/")
    .withColumn("parsed", expr("ai_parse_document(content)"))
    .selectExpr("path",
                "parsed:pages[*].elements[*].content AS text_blocks",
                "parsed:error AS parse_error")
    .filter("parse_error IS NULL")
    .withColumn("summary",  expr("ai_summarize(text_blocks, 50)"))
    .withColumn("entities", expr("ai_extract(text_blocks, array('date', 'amount', 'vendor'))"))
)
```

### 模式 4：語意比對／去重

```sql
-- 找出近似重複的公司名稱
SELECT a.id, b.id, ai_similarity(a.name, b.name) AS score
FROM companies a
JOIN companies b ON a.id < b.id
WHERE ai_similarity(a.name, b.name) > 0.85;
```

### 模式 5：使用 `ai_query` 擷取複雜 JSON（最後手段）

只有在輸出結構描述包含巢狀陣列，或需要任務專用函式無法處理的多步驟推理時才使用：

```python
from pyspark.sql.functions import expr, from_json, col

df = (
    spark.table("parsed_documents")
    .withColumn("ai_response", expr("""
        ai_query(
            'databricks-claude-sonnet-4',
            concat('將發票擷取為包含巢狀 itens 陣列的 JSON： ', text_blocks),
            responseFormat => '{"type":"json_object"}',
            failOnError     => false
        )
    """))
    .withColumn("invoice", from_json(
        col("ai_response.response"),
        "STRUCT<numero:STRING, total:DOUBLE, "
        "itens:ARRAY<STRUCT<codigo:STRING, descricao:STRING, qtde:DOUBLE, vlrUnit:DOUBLE>>>"
    ))
)
```

### 模式 6：時間序列預測

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(SELECT date, sales FROM daily_sales),
    horizon   => '2026-12-31',
    time_col  => 'date',
    value_col => 'sales'
);
-- 回傳：date, sales_forecast, sales_upper, sales_lower
```

## 參考檔案

- [1-task-functions.md](1-task-functions.md) — 所有 9 個任務專用函式（`ai_analyze_sentiment`, `ai_classify`, `ai_extract`, `ai_fix_grammar`, `ai_gen`, `ai_mask`, `ai_similarity`, `ai_summarize`, `ai_translate`）與 `ai_parse_document` 的完整語法、參數、SQL + PySpark 範例
- [2-ai-query.md](2-ai-query.md) — `ai_query` 完整參考：所有參數、使用 `responseFormat` 的結構化輸出、多模態 `files =>`、UDF 模式與錯誤處理
- [3-ai-forecast.md](3-ai-forecast.md) — `ai_forecast` 的參數、單一指標、多群組、多指標與信賴區間模式
- [4-document-processing-pipeline.md](4-document-processing-pipeline.md) — 在 Lakeflow 宣告式管線中使用 AI Functions 的端到端批次文件處理管線；包含 `config.yml` 集中化、函式選擇邏輯、自訂 RAG 管線（parse → chunk → Vector Search），以及近即時變體的 DSPy/LangChain 指引

## 常見問題

| 問題 | 解決方案 |
|---|---|
| 找不到 `ai_parse_document` | 需要 DBR **17.1+**。請檢查叢集 runtime。 |
| `ai_forecast` 失敗 | 需要 **Pro 或 Serverless** SQL warehouse——Classic 或 Starter 不提供。 |
| 所有函式都回傳 NULL | 輸入欄位為 NULL。呼叫前先用 `WHERE col IS NOT NULL` 篩選。 |
| `ai_translate` 無法處理某語言 | 支援：英文、德文、法文、義大利文、葡萄牙文、印地文、西班牙文、泰文。其他語言請用搭配多語言模型的 `ai_query`。 |
| `ai_classify` 回傳非預期標籤 | 請使用清楚且互斥的標籤名稱。標籤越少（2–5 個），結果越可靠。 |
| `ai_query` 在批次工作某些資料列上拋錯 | 加上 `failOnError => false`——它會回傳帶有 `.response` 與 `.error` 的 STRUCT，而不是直接拋錯。 |
| 批次工作執行很慢 | 請使用 DBR **15.4 ML LTS** 叢集（非 serverless 或互動式），以取得最佳化的批次推論吞吐量。 |
| 想在不修改 pipeline 程式碼的情況下切換模型 | 將所有模型名稱與提示詞存放在 `config.yml`——模式請參閱 [4-document-processing-pipeline.md](4-document-processing-pipeline.md)。 |