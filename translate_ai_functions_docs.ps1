function Write-Utf8NoBom {
    param(
        [string]$Path,
        [string]$Content
    )

    $normalized = $Content -replace "`r?`n", "`r`n"
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($Path, $normalized, $utf8NoBom)
}

$base = 'D:\azure_code\ai-dev-kit\databricks-skills\databricks-ai-functions'

Write-Utf8NoBom (Join-Path $base 'SKILL.md') @'
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
'@

Write-Utf8NoBom (Join-Path $base '1-task-functions.md') @'
# 任務專用 AI Functions — 完整參考

這些函式不需要選擇模型端點。它們會呼叫針對各任務最佳化的預先設定基礎模型 API。全部都需要 DBR 15.1+（批次作業為 15.4 ML LTS）；`ai_parse_document` 需要 DBR 17.1+。

---

## `ai_analyze_sentiment`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_analyze_sentiment

回傳以下其中之一：`positive`、`negative`、`neutral`、`mixed` 或 `NULL`。

```sql
SELECT ai_analyze_sentiment(review_text) AS sentiment
FROM customer_reviews;
```

```python
from pyspark.sql.functions import expr
df = spark.table("customer_reviews")
df.withColumn("sentiment", expr("ai_analyze_sentiment(review_text)")).display()
```

---

## `ai_classify`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_classify

**語法：** `ai_classify(content, labels)`
- `content`: STRING — 要分類的文字
- `labels`: ARRAY\<STRING\> — 2 到 20 個互斥類別

回傳符合的標籤或 `NULL`。

```sql
SELECT ticket_text,
       ai_classify(ticket_text, ARRAY('urgent', 'not urgent', 'spam')) AS priority
FROM support_tickets;
```

```python
from pyspark.sql.functions import expr
df = spark.table("support_tickets")
df.withColumn(
    "priority",
    expr("ai_classify(ticket_text, array('urgent', 'not urgent', 'spam'))")
).display()
```

**提示：**
- 標籤越少，結果越一致（2–5 個最佳）
- 標籤應互斥且容易明確區分
- 不適合多標籤分類——若需要請執行多次呼叫

---

## `ai_extract`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_extract

**語法：** `ai_extract(content, labels)`
- `content`: STRING — 來源文字
- `labels`: ARRAY\<STRING\> — 要擷取的實體類型

回傳一個 STRUCT，其中每個欄位名稱都對應一個標籤；若找不到則欄位為 `NULL`。

```sql
-- 直接擷取並存取欄位
SELECT
    entities.person,
    entities.location,
    entities.date
FROM (
    SELECT ai_extract(
        'John Doe called from New York on 2024-01-15.',
        ARRAY('person', 'location', 'date')
    ) AS entities
    FROM messages
);
```

```python
from pyspark.sql.functions import expr
df = spark.table("messages")
df = df.withColumn(
    "entities",
    expr("ai_extract(message, array('person', 'location', 'date'))")
)
df.select("entities.person", "entities.location", "entities.date").display()
```

**在以下情況請改用 `ai_query`：** 輸出包含巢狀陣列，或層級超過約 5 層時。

---

## `ai_fix_grammar`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_fix_grammar

**語法：** `ai_fix_grammar(content)` — 回傳修正後的 STRING。

針對英文最佳化。適合在下游處理前清理使用者產生內容。

```sql
SELECT ai_fix_grammar(user_comment) AS corrected FROM user_feedback;
```

```python
from pyspark.sql.functions import expr
df = spark.table("user_feedback")
df.withColumn("corrected", expr("ai_fix_grammar(user_comment)")).display()
```

---

## `ai_gen`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_gen

**語法：** `ai_gen(prompt)` — 回傳產生的 STRING。

當輸出格式不需結構化時，可用於自由格式文字生成。若要結構化 JSON 輸出，請使用搭配 `responseFormat` 的 `ai_query`。

```sql
SELECT product_name,
       ai_gen(CONCAT('為以下產品撰寫一句行銷標語：', product_name)) AS tagline
FROM products;
```

```python
from pyspark.sql.functions import expr
df = spark.table("products")
df.withColumn(
    "tagline",
    expr("ai_gen(concat('為以下產品撰寫一句行銷標語：', product_name))")
).display()
```

---

## `ai_mask`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_mask

**語法：** `ai_mask(content, labels)`
- `content`: STRING — 含有敏感資料的文字
- `labels`: ARRAY\<STRING\> — 要遮罩的實體類型

回傳將已辨識實體替換為 `[MASKED]` 的文字。

常見標籤值：`'person'`、`'email'`、`'phone'`、`'address'`、`'ssn'`、`'credit_card'`

```sql
SELECT ai_mask(
    message_body,
    ARRAY('person', 'email', 'phone', 'address')
) AS message_safe
FROM customer_messages;
```

```python
from pyspark.sql.functions import expr
df = spark.table("customer_messages")
df.withColumn(
    "message_safe",
    expr("ai_mask(message_body, array('person', 'email', 'phone'))")
).write.format("delta").mode("append").saveAsTable("catalog.schema.messages_safe")
```

---

## `ai_similarity`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_similarity

**語法：** `ai_similarity(expr1, expr2)` — 回傳 0.0 到 1.0 之間的 FLOAT。

可用於模糊去重、搜尋結果排序，或跨資料集的項目比對。

```sql
-- 去重公司名稱（similarity > 0.85 = 很可能重複）
SELECT a.id, b.id, a.name, b.name,
       ai_similarity(a.name, b.name) AS score
FROM companies a
JOIN companies b ON a.id < b.id
WHERE ai_similarity(a.name, b.name) > 0.85
ORDER BY score DESC;
```

```python
from pyspark.sql.functions import expr
df = spark.table("product_search")
df.withColumn(
    "match_score",
    expr("ai_similarity(search_query, product_title)")
).orderBy("match_score", ascending=False).display()
```

---

## `ai_summarize`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_summarize

**語法：** `ai_summarize(content [, max_words])`
- `content`: STRING — 要摘要的文字
- `max_words`: INTEGER（選填）— 字數上限；預設 50；使用 `0` 表示不設上限

```sql
-- 預設（50 個字）
SELECT ai_summarize(article_body) AS summary FROM news_articles;

-- 自訂字數上限
SELECT ai_summarize(article_body, 20)  AS brief   FROM news_articles;
SELECT ai_summarize(article_body, 0)   AS full    FROM news_articles;
```

```python
from pyspark.sql.functions import expr
df = spark.table("news_articles")
df.withColumn("summary", expr("ai_summarize(article_body, 30)")).display()
```

---

## `ai_translate`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_translate

**語法：** `ai_translate(content, to_lang)`
- `content`: STRING — 來源文字
- `to_lang`: STRING — 目標語言代碼

**支援的語言：** `en`、`de`、`fr`、`it`、`pt`、`hi`、`es`、`th`

若語言不在支援範圍內，請使用搭配多語言模型端點的 `ai_query`。

```sql
-- 單一語言
SELECT ai_translate(product_description, 'es') AS description_es FROM products;

-- 多語言展開
SELECT
    description,
    ai_translate(description, 'fr') AS description_fr,
    ai_translate(description, 'de') AS description_de
FROM products;
```

```python
from pyspark.sql.functions import expr
df = spark.table("products")
df.withColumn(
    "description_es",
    expr("ai_translate(product_description, 'es')")
).display()
```

---

## `ai_parse_document`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_parse_document

**需求：** DBR 17.1+

**語法：** `ai_parse_document(content [, options])`
- `content`: BINARY — 從 `read_files()` 或 `spark.read.format("binaryFile")` 載入的文件內容
- `options`: MAP\<STRING, STRING\>（選填）— 解析設定

**支援的格式：** PDF、JPG/JPEG、PNG、DOCX、PPTX

回傳一個 VARIANT，其中包含頁面、elements（文字段落、表格、圖像、頁首、頁尾）、邊界框，以及錯誤中繼資料。

**選項：**

| 鍵 | 值 | 說明 |
|-----|--------|-------------|
| `version` | `'2.0'` | 輸出結構描述版本 |
| `imageOutputPath` | Volume 路徑 | 儲存轉譯後的頁面影像 |
| `descriptionElementTypes` | `''`, `'figure'`, `'*'` | AI 產生的描述（預設：所有類型皆為 `'*'`） |

**輸出結構描述：**

```
document
├── pages[]          -- 頁面 id、image_uri
└── elements[]       -- 擷取內容
    ├── type         -- "text"、"table"、"figure" 等
    ├── content      -- 擷取文字
    ├── bbox         -- 邊界框座標
    └── description  -- AI 產生的描述
metadata             -- 檔案資訊、結構描述版本
error_status[]       -- 每頁的錯誤（若有）
```

```sql
-- 解析並擷取文字區塊
SELECT
    path,
    parsed:pages[*].elements[*].content AS text_blocks,
    parsed:error AS parse_error
FROM (
    SELECT path, ai_parse_document(content) AS parsed
    FROM read_files('/Volumes/catalog/schema/landing/docs/', format => 'binaryFile')
);

-- 使用選項解析（影像輸出 + 描述）
SELECT ai_parse_document(
    content,
    map(
        'version', '2.0',
        'imageOutputPath', '/Volumes/catalog/schema/volume/images/',
        'descriptionElementTypes', '*'
    )
) AS parsed
FROM read_files('/Volumes/catalog/schema/volume/invoices/', format => 'binaryFile');
```

```python
from pyspark.sql.functions import expr

df = (
    spark.read.format("binaryFile")
    .load("/Volumes/catalog/schema/landing/docs/")
    .withColumn("parsed", expr("ai_parse_document(content)"))
    .selectExpr(
        "path",
        "parsed:pages[*].elements[*].content AS text_blocks",
        "parsed:error AS parse_error",
    )
    .filter("parse_error IS NULL")
)

# 將擷取出的文字串接任務專用函式
df = (
    df.withColumn("summary",  expr("ai_summarize(text_blocks, 50)"))
      .withColumn("entities", expr("ai_extract(text_blocks, array('date', 'amount', 'vendor'))"))
      .withColumn("category", expr("ai_classify(text_blocks, array('invoice', 'contract', 'report'))"))
)
df.display()
```

**限制：**
- 對內容密集或低解析度文件的處理速度較慢
- 對非拉丁字母與數位簽章 PDF 的效果較不理想
- 不支援自訂模型——一律使用內建解析模型
'@

Write-Utf8NoBom (Join-Path $base '2-ai-query.md') @'
# `ai_query` — 完整參考

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_query

> 只有在沒有任何任務專用函式適用時才使用 `ai_query`。請參閱 [SKILL.md](SKILL.md) 中的函式選擇表。

## 何時使用 `ai_query`

- 輸出結構描述包含**巢狀陣列或深層巢狀 STRUCT**（例如 `itens: [{codigo, descricao, qtde}]`）
- 呼叫**自訂 Model Serving 端點**（你自行微調的模型）
- **多模態輸入**——透過 `files =>` 傳遞二進位影像檔案
- **跨文件推理**——prompt 包含多個來源的內容
- 需要控制**取樣參數**（`temperature`、`max_tokens`）

## 語法

```sql
ai_query(
    endpoint,
    request
    [, returnType      => ddl_schema]
    [, failOnError     => boolean]
    [, modelParameters => named_struct(...)]
    [, responseFormat  => json_string]
    [, files           => binary_column]
)
```

## 參數

| 參數 | 型別 | Runtime | 說明 |
|---|---|---|---|
| `endpoint` | STRING literal | — | 基礎模型名稱或自訂 endpoint 名稱。請勿猜測——請使用 [model serving docs](https://docs.databricks.com/aws/en/machine-learning/foundation-models/supported-models.html) 中的精確名稱。 |
| `request` | STRING or STRUCT | — | chat models 的 prompt 字串；自訂 ML 端點則為 STRUCT |
| `returnType` | DDL schema（選填） | 15.2+ | 像 `from_json` 一樣將回應結構化解析 |
| `failOnError` | BOOLEAN（選填，預設 `true`） | 15.3+ | 若為 `false`，失敗時回傳 STRUCT `{response, error}`，而不是直接拋出錯誤 |
| `modelParameters` | STRUCT（選填） | 15.3+ | 取樣參數：`temperature`、`max_tokens`、`top_p` 等 |
| `responseFormat` | JSON string（選填） | 15.4+ | 強制輸出結構化 JSON：`'{"type":"json_object"}'` |
| `files` | binary column（選填） | — | 直接傳遞二進位影像（JPEG/PNG）——不需要上傳步驟 |

## 基礎模型名稱（請勿猜測）

| 使用情境 | Endpoint 名稱 |
|---|---|
| 一般推理／擷取 | `databricks-claude-sonnet-4` |
| 快速／低成本任務 | `databricks-meta-llama-3-1-8b-instruct` |
| 大 context／高複雜度 | `databricks-meta-llama-3-3-70b-instruct` |
| 多模態（vision + text） | `databricks-llama-4-maverick` |
| 向量嵌入 | `databricks-gte-large-en` |

## 模式

### 基本用法 — 單一 prompt

```sql
SELECT ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    '請用 30 個字描述 Databricks SQL。'
) AS response;
```

### 套用至資料表欄位

```sql
SELECT ticket_id,
       ai_query(
           'databricks-meta-llama-3-3-70b-instruct',
           CONCAT('請用一句話摘要：', ticket_body)
       ) AS summary
FROM support_tickets;
```

### 結構化 JSON 輸出（`responseFormat`）

對於 chat models，優先使用此方式而非 `returnType`（需要 Runtime 15.4+）：

```sql
SELECT ai_query(
    'databricks-claude-sonnet-4',
    CONCAT('將發票欄位擷取為 JSON。欄位：numero, fornecedor, total, '
           'itens:[{codigo, descricao, qtde, vlrUnit}]。輸入：', text_blocks),
    responseFormat => '{"type":"json_object"}',
    failOnError     => false
) AS ai_response
FROM parsed_documents;
```

接著使用 `from_json` 解析：

```python
from pyspark.sql.functions import from_json, col

df = df.withColumn(
    "invoice",
    from_json(
        col("ai_response.response"),
        "STRUCT<numero:STRING, fornecedor:STRING, total:DOUBLE, "
        "itens:ARRAY<STRUCT<codigo:STRING, descricao:STRING, qtde:DOUBLE, vlrUnit:DOUBLE>>>"
    )
)
# 存取欄位
df.select("invoice.numero", "invoice.total", "invoice.itens").display()
```

### 搭配 `failOnError`（批次管線務必使用）

```sql
SELECT
    id,
    ai_response.response,
    ai_response.error
FROM (
    SELECT id,
           ai_query(
               'databricks-claude-sonnet-4',
               CONCAT('分類：', text),
               failOnError => false
           ) AS ai_response
    FROM documents
)
-- 在下游將錯誤導向至獨立資料表
```

### 搭配 `modelParameters`（控制取樣）

```sql
SELECT ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    CONCAT('從以下內容擷取實體：', text),
    failOnError     => false,
    modelParameters => named_struct('temperature', CAST(0.0 AS DOUBLE), 'max_tokens', 500)
) AS result
FROM documents;
```

### 多模態 — 影像檔案（`files =>`）

不需要額外的檔案上傳步驟。直接傳入二進位欄位即可：

```sql
SELECT
    path,
    ai_query(
        'databricks-llama-4-maverick',
        '詳細描述這張影像中的內容。',
        files => content
    ) AS description
FROM read_files('/Volumes/catalog/schema/images/', format => 'binaryFile');
```

```python
from pyspark.sql.functions import expr

df = (
    spark.read.format("binaryFile")
    .load("/Volumes/catalog/schema/images/")
    .withColumn("description", expr("""
        ai_query(
            'databricks-llama-4-maverick',
            '描述這張影像的內容。',
            files => content
        )
    """))
)
```

### 作為可重複使用的 SQL UDF

```sql
CREATE FUNCTION catalog.schema.extract_invoice(text STRING)
RETURNS STRING
RETURN ai_query(
    'databricks-claude-sonnet-4',
    CONCAT('從以下內容擷取發票 JSON：', text),
    responseFormat => '{"type":"json_object"}'
);

SELECT extract_invoice(document_text) FROM raw_documents;
```

### 搭配 `expr` 的 PySpark

```python
from pyspark.sql.functions import expr

df = spark.table("documents")
df = df.withColumn("result", expr("""
    ai_query(
        'databricks-claude-sonnet-4',
        concat('從以下內容擷取結構化資料：', content),
        responseFormat => '{"type":"json_object"}',
        failOnError     => false
    )
"""))
```

## 批次管線的錯誤處理模式

在批次工作中務必使用 `failOnError => false`。將錯誤寫入 sidecar 資料表：

```python
import dlt
from pyspark.sql.functions import expr, col

@dlt.table(comment="AI 擷取結果")
def extracted():
    return (
        dlt.read("raw")
        .withColumn("ai_response", expr("""
            ai_query('databricks-claude-sonnet-4', prompt,
                     responseFormat => '{"type":"json_object"}',
                     failOnError     => false)
        """))
    )

@dlt.table(comment="AI 擷取失敗的資料列")
def extraction_errors():
    return (
        dlt.read("extracted")
        .filter(col("ai_response.error").isNotNull())
        .select("id", "prompt", col("ai_response.error").alias("error"))
    )
```
'@

Write-Utf8NoBom (Join-Path $base '3-ai-forecast.md') @'
# `ai_forecast` — 完整參考

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_forecast

> `ai_forecast` 是**資料表值型函式**——它回傳的是資料列組成的資料表，而不是純量。請使用 `SELECT * FROM ai_forecast(...)` 呼叫。

## 需求條件

- **Pro 或 Serverless SQL warehouse**——Classic 或 Starter 不提供
- 輸入資料必須具有 DATE 或 TIMESTAMP 時間欄位，以及至少一個數值欄位

## 語法

```sql
SELECT *
FROM ai_forecast(
    observed                   => TABLE(...) or query,
    horizon                    => 'YYYY-MM-DD' or TIMESTAMP,
    time_col                   => 'column_name',
    value_col                  => 'column_name',
    [group_col                 => 'column_name'],
    [prediction_interval_width => 0.95]
)
```

## 參數

| 參數 | 型別 | 說明 |
|---|---|---|
| `observed` | TABLE 參照或子查詢 | 含時間 + 數值欄位的訓練資料 |
| `horizon` | DATE、TIMESTAMP 或 STRING | 預測期間的結束日期／時間 |
| `time_col` | STRING | `observed` 中 DATE 或 TIMESTAMP 欄位的名稱 |
| `value_col` | STRING | 要預測的一個或多個數值欄位（每個 group 最多 100 個） |
| `group_col` | STRING（選填） | 依欄位分組預測——每個 group 值各產生一條預測序列 |
| `prediction_interval_width` | DOUBLE（選填，預設 0.95） | 介於 0 到 1 之間的信賴區間寬度 |

## 輸出欄位

對於每個名為 `metric` 的 `value_col`，輸出包含：

| 欄位 | 型別 | 說明 |
|---|---|---|
| time_col | DATE 或 TIMESTAMP | 預測時間戳（與輸入型別相同） |
| `metric_forecast` | DOUBLE | 點預測值 |
| `metric_upper` | DOUBLE | 信賴區間上界 |
| `metric_lower` | DOUBLE | 信賴區間下界 |
| group_col | 原始型別 | 指定 `group_col` 時才會出現 |

## 模式

### 單一指標預測

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(SELECT order_date, revenue FROM daily_revenue),
    horizon   => '2026-12-31',
    time_col  => 'order_date',
    value_col => 'revenue'
);
-- 回傳：order_date, revenue_forecast, revenue_upper, revenue_lower
```

### 多群組預測

會為 `group_col` 的每個不同值產生一條預測序列：

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(SELECT date, region, sales FROM regional_sales),
    horizon   => '2026-12-31',
    time_col  => 'date',
    value_col => 'sales',
    group_col => 'region'
);
-- 回傳：date, region, sales_forecast, sales_upper, sales_lower
-- 每個 region 的每個日期各一列
```

### 多個數值欄位

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(SELECT date, units, revenue FROM daily_kpis),
    horizon   => '2026-06-30',
    time_col  => 'date',
    value_col => 'units,revenue'   -- 以逗號分隔
);
-- 回傳：date, units_forecast, units_upper, units_lower,
--                revenue_forecast, revenue_upper, revenue_lower
```

### 自訂信賴區間

```sql
SELECT *
FROM ai_forecast(
    observed                   => TABLE(SELECT ts, sensor_value FROM iot_readings),
    horizon                    => '2026-03-31',
    time_col                   => 'ts',
    value_col                  => 'sensor_value',
    prediction_interval_width  => 0.80   -- 較窄的區間 = 較不保守
);
```

### 篩選輸入資料（Subquery）

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(
        SELECT date, sales
        FROM daily_sales
        WHERE region = 'BR' AND date >= '2024-01-01'
    ),
    horizon   => '2026-12-31',
    time_col  => 'date',
    value_col => 'sales'
);
```

### PySpark — 使用 `spark.sql()`

`ai_forecast` 是資料表值型函式，因此必須透過 `spark.sql()` 呼叫：

```python
result = spark.sql("""
    SELECT *
    FROM ai_forecast(
        observed  => TABLE(SELECT date, sales FROM catalog.schema.daily_sales),
        horizon   => '2026-12-31',
        time_col  => 'date',
        value_col => 'sales'
    )
""")
result.display()
```

### 將預測結果儲存至 Delta 資料表

```python
result = spark.sql("""
    SELECT *
    FROM ai_forecast(
        observed  => TABLE(SELECT date, region, revenue FROM catalog.schema.sales),
        horizon   => '2026-12-31',
        time_col  => 'date',
        value_col => 'revenue',
        group_col => 'region'
    )
""")
result.write.format("delta").mode("overwrite").saveAsTable("catalog.schema.revenue_forecast")
```

## 注意事項

- 底層模型是類似 prophet 的分段線性 + 季節性模型——適合具有趨勢與每週／每年季節性的商業時間序列
- 可處理「任意數量的群組」，但每個群組最多 **100 個指標**
- 輸出時間欄位會保留輸入型別（DATE 仍為 DATE，TIMESTAMP 仍為 TIMESTAMP）
- 無論輸入型別為何，數值欄位在輸出中一律轉型為 DOUBLE
'@

Write-Utf8NoBom (Join-Path $base '4-document-processing-pipeline.md') @'
# 使用 AI Functions 的文件處理管線

說明如何在 Lakeflow 宣告式管線 (DLT) 中，使用 AI Functions 建立端到端的批次文件處理管線模式。涵蓋函式選擇、`config.yml` 集中化、錯誤處理，以及使用 DSPy 或 LangChain 建立近即時變體的指引。

> 若需工作流程移轉脈絡（例如從 n8n、LangChain 或其他編排工具移轉），請參閱配套 skill `n8n-to-databricks`。

---

## 文件管線的函式選擇

使用 AI Functions 處理文件時，請在每個階段依照以下優先順序選擇：

| 階段 | 優先函式 | 在以下情況使用 `ai_query`... |
|---|---|---|
| 解析二進位文件（PDF、DOCX、影像） | `ai_parse_document` | 需要影像層級推理 |
| 從文字擷取平面欄位 | `ai_extract` | 結構描述含有巢狀陣列 |
| 分類文件類型或狀態 | `ai_classify` | 超過 20 個類別 |
| 項目相似度／比對評分 | `ai_similarity` | 需要跨文件推理 |
| 摘要長段落 | `ai_summarize` | — |
| 擷取巢狀 JSON（例如 line items） | 搭配 `responseFormat` 的 `ai_query` | （這就是預期使用情境） |

---

## 集中式配置（`config.yml`）

**務必將模型名稱、Volume 路徑與提示詞集中放在 `config.yml` 中。** 這樣切換模型時只需修改一行，也能讓 pipeline 程式碼避免硬編碼字串。

```yaml
# config.yml
models:
  default: "databricks-claude-sonnet-4"
  mini:    "databricks-meta-llama-3-1-8b-instruct"
  vision:  "databricks-llama-4-maverick"

catalog:
  name:   "my_catalog"
  schema: "document_processing"

volumes:
  input: "/Volumes/my_catalog/document_processing/landing/"
  tmp:   "/Volumes/my_catalog/document_processing/tmp/"

output_tables:
  results: "my_catalog.document_processing.processed_docs"
  errors:  "my_catalog.document_processing.processing_errors"

prompts:
  extract_invoice: |
    擷取發票欄位，且只回傳有效的 JSON。
    欄位：invoice_number, vendor_name, vendor_tax_id（僅數字），
    issue_date（dd/mm/yyyy）、total_amount（數值），
    line_items: [{item_code, description, quantity, unit_price, total}]。
    缺少欄位時請回傳 null。

  classify_doc: |
    請將這份文件精確分類為一個類別。
```

```python
# config_loader.py
import yaml

def load_config(path: str = "config.yml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

CFG           = load_config()
ENDPOINT      = CFG["models"]["default"]
ENDPOINT_MINI = CFG["models"]["mini"]
VOLUME_INPUT  = CFG["volumes"]["input"]
PROMPT_INV    = CFG["prompts"]["extract_invoice"]
```

---

## 批次管線 — Lakeflow 宣告式管線

你的文件工作流程中，每個邏輯步驟都對應到一個 `@dlt.table` 階段。資料會透過各階段之間的 Delta 資料表流動。

```
[Landing Volume]  →  階段 1：ai_parse_document
                  →  階段 2：ai_classify（文件類型）
                  →  階段 3：ai_extract（平面欄位）+ ai_query（巢狀 JSON）
                  →  階段 4：ai_similarity（項目比對）
                  →  階段 5：最終 Delta 輸出資料表
```

### `pipeline.py`

```python
import dlt
import yaml
from pyspark.sql.functions import expr, col, from_json

CFG      = yaml.safe_load(open("/Workspace/path/to/config.yml"))
ENDPOINT = CFG["models"]["default"]
VOL_IN   = CFG["volumes"]["input"]
PROMPT   = CFG["prompts"]["extract_invoice"]


# ── 階段 1：解析二進位文件 ───────────────────────────────────────────────
# 優先選擇：ai_parse_document——不需要選模型，也不需要 ai_query

@dlt.table(comment="來自 landing volume 中所有檔案類型的解析文件文字")
def raw_parsed():
    return (
        spark.read.format("binaryFile").load(VOL_IN)
        .withColumn("parsed", expr("ai_parse_document(content)"))
        .selectExpr(
            "path",
            "parsed:pages[*].elements[*].content AS text_blocks",
            "parsed:error AS parse_error",
        )
        .filter("parse_error IS NULL")
    )


# ── 階段 2：分類文件類型 ─────────────────────────────────────────────────
# 優先選擇：ai_classify——成本低，無需選端點

@dlt.table(comment="文件類型分類")
def classified_docs():
    return (
        dlt.read("raw_parsed")
        .withColumn(
            "doc_type",
            expr("ai_classify(text_blocks, array('invoice', 'purchase_order', 'receipt', 'contract', 'other'))")
        )
    )


# ── 階段 3a：平面欄位擷取 ────────────────────────────────────────────────
# 平面欄位（vendor、date、total）優先選擇 ai_extract

@dlt.table(comment="從文件擷取的平面標頭欄位")
def extracted_flat():
    return (
        dlt.read("classified_docs")
        .filter("doc_type = 'invoice'")
        .withColumn(
            "header",
            expr("ai_extract(text_blocks, array('invoice_number', 'vendor_name', 'issue_date', 'total_amount', 'tax_id'))")
        )
        .select("path", "doc_type", "text_blocks", col("header"))
    )


# ── 階段 3b：巢狀 JSON 擷取（最後手段：ai_query）────────────────────────
# 只因為 line_items 是巢狀陣列才使用 ai_query——ai_extract 無法處理

@dlt.table(comment="已擷取的巢狀明細項目——僅因陣列結構描述而使用 ai_query")
def extracted_line_items():
    return (
        dlt.read("extracted_flat")
        .withColumn(
            "ai_response",
            expr(f"""
                ai_query(
                    '{ENDPOINT}',
                    concat('{PROMPT.strip()}', '\\n\\n文件文字：\\n', LEFT(text_blocks, 6000)),
                    responseFormat => '{{"type":"json_object"}}',
                    failOnError     => false
                )
            """)
        )
        .withColumn(
            "line_items",
            from_json(
                col("ai_response.response"),
                "STRUCT<line_items:ARRAY<STRUCT<item_code:STRING, description:STRING, "
                "quantity:DOUBLE, unit_price:DOUBLE, total:DOUBLE>>>"
            )
        )
        .select("path", "doc_type", "header", "line_items", col("ai_response.error").alias("extraction_error"))
    )


# ── 階段 4：相似度比對 ───────────────────────────────────────────────────
# 模糊比對擷取欄位時，優先選擇 ai_similarity

@dlt.table(comment="供應商名稱與參考主檔資料的相似度")
def vendor_matched():
    extracted = dlt.read("extracted_line_items")
    # 與參考 vendor 資料表做 join，以進行模糊比對
    vendors = spark.table("my_catalog.document_processing.vendor_master").select("vendor_id", "vendor_name")

    return (
        extracted.crossJoin(vendors)
        .withColumn(
            "name_similarity",
            expr("ai_similarity(header.vendor_name, vendor_name)")
        )
        .filter("name_similarity > 0.80")
        .orderBy("name_similarity", ascending=False)
    )


# ── 階段 5：最終輸出 + 錯誤 sidecar ─────────────────────────────────────

@dlt.table(
    comment="供下游使用的最終處理後文件",
    table_properties={"delta.enableChangeDataFeed": "true"},
)
def processed_docs():
    return (
        dlt.read("extracted_line_items")
        .filter("extraction_error IS NULL")
        .selectExpr(
            "path",
            "doc_type",
            "header.invoice_number",
            "header.vendor_name",
            "header.issue_date",
            "header.total_amount",
            "line_items.line_items AS items",
        )
    )


@dlt.table(comment="在任一擷取階段失敗的資料列——供檢查與重新處理")
def processing_errors():
    return (
        dlt.read("extracted_line_items")
        .filter("extraction_error IS NOT NULL")
        .select("path", "doc_type", col("extraction_error").alias("error"))
    )
```

---

## 自訂 RAG 管線 — Parse → Chunk → Index → Query

如果目標是 retrieval-augmented generation，而不是欄位擷取，請使用此管線來解析文件、將其切成 chunks 存入 Delta 資料表，並用 Vector Search 建立索引。

### 步驟 1 — 解析並切 chunk 到 Delta 資料表

`ai_parse_document` 會回傳 VARIANT。呼叫 `explode` 前，請先使用 `variant_get` 並明確轉型成 `ARRAY<VARIANT>`，因為 `explode()` 無法直接接受原始 VARIANT 值。

```sql
CREATE OR REPLACE TABLE catalog.schema.parsed_chunks AS
WITH parsed AS (
  SELECT
    path,
    ai_parse_document(content) AS doc
  FROM read_files('/Volumes/catalog/schema/volume/docs/', format => 'binaryFile')
),
elements AS (
  SELECT
    path,
    explode(variant_get(doc, '$.document.elements', 'ARRAY<VARIANT>')) AS element
  FROM parsed
)
SELECT
  md5(concat(path, variant_get(element, '$.content', 'STRING'))) AS chunk_id,
  path AS source_path,
  variant_get(element, '$.content', 'STRING') AS content,
  variant_get(element, '$.type', 'STRING') AS element_type,
  current_timestamp() AS parsed_at
FROM elements
WHERE variant_get(element, '$.content', 'STRING') IS NOT NULL
  AND length(trim(variant_get(element, '$.content', 'STRING'))) > 10;
```

### 步驟 1a（正式環境）— 使用 Structured Streaming 進行增量解析

對於新文件會持續進入的正式環境管線，請使用搭配 checkpoints 的 Structured Streaming 來達成 exactly-once 處理。每次執行只會處理新檔案，然後以 `trigger(availableNow=True)` 結束。

請參閱官方 bundle 範例：
[databricks/bundle-examples/contrib/job_with_ai_parse_document](https://github.com/databricks/bundle-examples/tree/main/contrib/job_with_ai_parse_document)

**階段 1 — 解析原始文件（streaming）：**

```python
from pyspark.sql.functions import col, current_timestamp, expr

files_df = (
    spark.readStream.format("binaryFile")
    .option("pathGlobFilter", "*.{pdf,jpg,jpeg,png}")
    .option("recursiveFileLookup", "true")
    .load("/Volumes/catalog/schema/volume/docs/")
)

parsed_df = (
    files_df
    .repartition(8, expr("crc32(path) % 8"))
    .withColumn("parsed", expr("""
        ai_parse_document(content, map(
            'version', '2.0',
            'descriptionElementTypes', '*'
        ))
    """))
    .withColumn("parsed_at", current_timestamp())
    .select("path", "parsed", "parsed_at")
)

(
    parsed_df.writeStream.format("delta")
    .outputMode("append")
    .option("checkpointLocation", "/Volumes/catalog/schema/checkpoints/01_parse")
    .option("mergeSchema", "true")
    .trigger(availableNow=True)
    .toTable("catalog.schema.parsed_documents_raw")
)
```

**階段 2 — 從已解析的 VARIANT 擷取文字（streaming）：**

使用 `transform()` 從 VARIANT 陣列中擷取 element content，並以 `try_cast` 安全存取。錯誤資料列會保留，但會被標記。

```python
from pyspark.sql.functions import col, concat_ws, expr, lit, when

parsed_stream = spark.readStream.format("delta").table("catalog.schema.parsed_documents_raw")

text_df = (
    parsed_stream
    .withColumn("text",
        when(
            expr("try_cast(parsed:error_status AS STRING)").isNotNull(), lit(None)
        ).otherwise(
            concat_ws("\n\n", expr("""
                transform(
                    try_cast(parsed:document:elements AS ARRAY),
                    element -> try_cast(element:content AS STRING)
                )
            """))
        )
    )
    .withColumn("error_status", expr("try_cast(parsed:error_status AS STRING)"))
    .select("path", "text", "error_status", "parsed_at")
)

(
    text_df.writeStream.format("delta")
    .outputMode("append")
    .option("checkpointLocation", "/Volumes/catalog/schema/checkpoints/02_text")
    .option("mergeSchema", "true")
    .trigger(availableNow=True)
    .toTable("catalog.schema.parsed_documents_text")
)
```

關鍵技巧：
- **依檔案 hash 進行 `repartition`** —— 將 `ai_parse_document` 平行分散到各 worker 節點
- **`trigger(availableNow=True)`** —— 處理所有待處理檔案後停止（類似批次）
- **Checkpoints** —— exactly-once 保證；重新執行時不會重複解析
- **`transform()` + `try_cast`** —— 對文字擷取而言，比 `explode` + `variant_get` 更安全
- **具獨立 checkpoints 的分離階段** —— 解析與文字擷取可各自失敗／重試

### 步驟 1b — 啟用 Change Data Feed

這是 Vector Search Delta Sync 的必要條件：

```sql
ALTER TABLE catalog.schema.parsed_chunks
SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
```

### 步驟 2 — 建立 Vector Search Index 並查詢

請使用 **[databricks-vector-search](../databricks-vector-search/SKILL.md)** skill 在已切 chunk 的資料表上建立 Delta Sync index，並進行查詢。請先確認已啟用 CDF（上述步驟 1b）。

### RAG 專屬問題

| 問題 | 解決方案 |
|-------|----------|
| `explode()` 對 VARIANT 失敗 | `explode()` 需要 ARRAY，而不是 VARIANT。請在 explode 前使用 `variant_get(doc, '$.document.elements', 'ARRAY<VARIANT>')` 先轉型 |
| 過短／雜訊多的 chunks | 以 `length(trim(...)) > 10` 進行篩選——解析會產生微小片段（頁碼、頁首），進而汙染索引 |
| 重複解析未變更的文件 | 使用搭配 checkpoints 的 Structured Streaming——請參閱上方步驟 1a |
| 不支援的區域 | 僅支援 US/EU 區域，或啟用 cross-geography routing |

---

## 近即時變體 — DSPy + MLflow Agent

當管線必須在幾秒內回應（由使用者動作、API 呼叫或表單提交觸發）時，請改用搭配 MLflow ChatAgent 的 DSPy，而非 DLT 管線。

**何時使用 DSPy 或 LangChain：**

| 情境 | 技術棧 |
|---|---|
| 固定 pipeline 步驟、I/O 明確、希望進行 prompt 最佳化 | **DSPy** |
| 需要 tool-calling、memory 或多 agent 協作 | **LangChain LCEL** + MLflow ChatAgent |
| 單一 LLM 呼叫、簡單任務 | 直接在 notebook 中使用 AI Function 或 `ai_query` |

### DSPy Signatures（取代 LangChain agent system prompts）

```python
# pip install dspy-ai mlflow databricks-sdk
import dspy, yaml

CFG = yaml.safe_load(open("config.yml"))
lm = dspy.LM(
    model=f"databricks/{CFG['models']['default']}",
    api_base="https://<workspace-host>/serving-endpoints",
    api_key=dbutils.secrets.get("scope", "databricks-token"),
)
dspy.configure(lm=lm)


class ExtractInvoiceHeader(dspy.Signature):
    """從文件文字擷取發票標頭欄位。"""
    document_text:  str = dspy.InputField(desc="文件的原始文字")
    invoice_number: str = dspy.OutputField(desc="發票號碼，或 null")
    vendor_name:    str = dspy.OutputField(desc="供應商名稱，或 null")
    issue_date:     str = dspy.OutputField(desc="日期，格式為 dd/mm/yyyy，或 null")
    total_amount:  float = dspy.OutputField(desc="總金額（float），或 null")


class ClassifyDocument(dspy.Signature):
    """將文件分類為提供的其中一個類別。"""
    document_text: str = dspy.InputField()
    category:      str = dspy.OutputField(
        desc="以下其中之一：invoice, purchase_order, receipt, contract, other"
    )


class DocumentPipeline(dspy.Module):
    def __init__(self):
        self.classify = dspy.Predict(ClassifyDocument)
        self.extract  = dspy.Predict(ExtractInvoiceHeader)

    def forward(self, document_text: str):
        doc_type = self.classify(document_text=document_text).category
        if doc_type == "invoice":
            header = self.extract(document_text=document_text)
            return {"doc_type": doc_type, "header": header.__dict__}
        return {"doc_type": doc_type, "header": None}


pipeline = DocumentPipeline()
```

### 使用 MLflow 包裝並註冊

```python
import mlflow, json

class DSPyDocumentAgent(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        import dspy, yaml
        cfg = yaml.safe_load(open(context.artifacts["config"]))
        lm = dspy.LM(model=f"databricks/{cfg['models']['default']}")
        dspy.configure(lm=lm)
        self.pipeline = DocumentPipeline()

    def predict(self, context, model_input):
        text = model_input.iloc[0]["document_text"]
        return json.dumps(self.pipeline(document_text=text), ensure_ascii=False)

mlflow.set_registry_uri("databricks-uc")
with mlflow.start_run():
    mlflow.pyfunc.log_model(
        artifact_path="document_agent",
        python_model=DSPyDocumentAgent(),
        artifacts={"config": "config.yml"},
        registered_model_name="my_catalog.document_processing.document_agent",
    )
```

---

## 提示

1. **先解析、再豐富化** —— 務必將 `ai_parse_document` 作為第一階段。將其文字輸出提供給任務專用函式；切勿把原始二進位直接傳給 `ai_query`。
2. **平面欄位 → `ai_extract`；巢狀陣列 → `ai_query`** —— 這是最清楚的決策邊界。
3. **在批次中 `failOnError => false` 是必要條件** —— 將錯誤寫入 sidecar `_errors` 資料表，而不是讓 pipeline 當掉。
4. **送進 `ai_query` 前先截斷** —— 使用 `LEFT(text, 6000)`，或對長文件切 chunk，以避免超出 context window 限制。
5. **提示詞應放在 `config.yml` 中** —— 絕不要在 pipeline 程式碼中硬編碼 prompt 字串。修改 prompt 應是 config 變更，而不是程式碼變更。
6. **DSPy 適合 agents** —— 當從 LangChain agent 類工具移轉時，DSPy 的型別化 `Signature` 類別可提供結構化 I/O 契約、可測試性，以及可選的 prompt 編譯／最佳化。
'@
