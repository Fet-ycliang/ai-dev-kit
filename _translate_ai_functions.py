import pathlib, textwrap

content = """\
# AI Functions、http_request、remote_query 與 read_files 參考

Databricks SQL 進階函式完整參考：內建 AI 函式、HTTP 請求、Lakehouse Federation 遠端查詢與檔案讀取。

---

## 內容

- [AI Functions 概覽](#ai-functions-overview)
- [ai_query -- 通用 AI 函式](#ai_query----general-purpose-ai-function)
- [特定任務 AI 函式](#task-specific-ai-functions)
  - [ai_gen](#ai_gen)
  - [ai_classify](#ai_classify)
  - [ai_extract](#ai_extract)
  - [ai_analyze_sentiment](#ai_analyze_sentiment)
  - [ai_similarity](#ai_similarity)
  - [ai_summarize](#ai_summarize)
  - [ai_translate](#ai_translate)
  - [ai_fix_grammar](#ai_fix_grammar)
  - [ai_mask](#ai_mask)
- [文件與多模態 AI 函式](#document-and-multimodal-ai-functions)
  - [ai_parse_document](#ai_parse_document)
- [時間序列 AI 函式](#time-series-ai-functions)
  - [ai_forecast](#ai_forecast)
- [向量搜尋函式](#vector-search-function)
  - [vector_search](#vector_search)
- [http_request 函式](#http_request-function)
- [remote_query 函式（Lakehouse Federation）](#remote_query-function-lakehouse-federation)
- [read_files 資料表值函式](#read_files-table-valued-function)

---

## AI Functions 概覽

Databricks AI Functions 是內建的 SQL 函式，可直接從 SQL 呼叫最先進的生成式 AI 模型。它們運行於 Databricks Foundation Model API 之上，可在 Databricks SQL、筆記本、Lakeflow Spark Declarative Pipelines 及 Workflows 中使用。

**所有 AI 函式的共同需求：**
- 工作區必須位於支援 AI Functions 批次推論最佳化的區域
- 不支援 Databricks SQL Classic（需要 Serverless SQL Warehouse）
- 筆記本需要 Databricks Runtime 15.1+；批次工作負載建議使用 15.4 ML LTS
- 模型授權於 Apache 2.0 或 LLAMA 3.3 Community License
- 目前針對英文進行調整（底層模型支援多種語言）
- 公開預覽版，符合 HIPAA 規範

**速率限制與計費：**
- AI Functions 受 Foundation Model API 速率限制約束
- 以 Databricks SQL 運算加上 Foundation Model API 的 token 用量計費
- 開發期間請在查詢中使用 `LIMIT` 以控制成本

---

## ai_query -- 通用 AI 函式

最強大且最靈活的 AI 函式。查詢任何 serving endpoint（Foundation Models、外部模型或自訂 ML 模型），用於即時或批次推論。

### 語法

```sql
-- 基本呼叫
ai_query(endpoint, request)

-- 包含所有選用參數的完整呼叫
ai_query(
  endpoint,
  request,
  returnType          => type_expression,
  failOnError         => boolean,
  modelParameters     => named_struct(...),
  responseFormat      => format_string,
  files               => content_expression
)
```

### 參數

| 參數 | 型別 | 必要 | 說明 |
|-----------|------|----------|-------------|
| `endpoint` | STRING | 是 | 同一工作區中 Foundation Model、外部模型或自訂模型 serving endpoint 的名稱 |
| `request` | STRING or STRUCT | 是 | 對於 LLM endpoint：STRING 提示詞。對於自訂 ML endpoint：單一欄位或符合預期輸入特徵的 STRUCT |
| `returnType` | Expression | 否 | 預期的回傳型別（DDL 格式）。Runtime 15.2+ 為選用；15.1 及以下版本為必填 |
| `failOnError` | BOOLEAN | 否 | 預設 `true`。設為 `false` 時，改回傳包含 `response` 與 `errorStatus` 欄位的 STRUCT，而非直接失敗 |
| `modelParameters` | STRUCT | 否 | 透過 `named_struct()` 傳入模型參數（Runtime 15.3+） |
| `responseFormat` | STRING | 否 | 控制輸出格式：`'text'`、`'json_object'` 或 DDL/JSON schema 字串（Runtime 15.4 LTS+，僅限 chat 模型） |
| `files` | Expression | 否 | 影像處理的多模態檔案輸入（支援 JPEG、PNG） |

### 回傳型別

| 情境 | 回傳型別 |
|----------|-------------|
| `failOnError => true`（預設） | 符合 endpoint 型別或 `returnType` 的解析回應 |
| `failOnError => false` | `STRUCT<result: T, errorMessage: STRING>`，其中 T 為解析後的型別 |
| 使用 `responseFormat` | 符合指定 schema 的結構化輸出 |

### 模型參數

```sql
-- 使用 modelParameters 控制生成
SELECT ai_query(
  'databricks-meta-llama-3-3-70b-instruct',
  'Explain quantum computing in 3 sentences.',
  modelParameters => named_struct(
    'max_tokens', 256,
    'temperature', 0.1,
    'top_p', 0.9
  )
) AS response;
```

常用模型參數：
- `max_tokens`（INT）-- 最大生成 token 數
- `temperature`（DOUBLE）-- 隨機性（0.0 = 確定性，2.0 = 最大隨機）
- `top_p`（DOUBLE）-- Nucleus sampling 閾值
- `stop`（ARRAY<STRING>）-- 停止序列

### 使用 responseFormat 的結構化輸出

> **注意：** 頂層 `responseFormat` STRUCT 必須恰好包含一個欄位。若要回傳多個欄位，請將它們包裝在單一外層欄位中。

```sql
-- 強制輸出符合 schema 的 JSON（頂層 STRUCT 必須恰好包含一個欄位）
SELECT ai_query(
  'databricks-meta-llama-3-3-70b-instruct',
  'Extract the product name, price, and category from: "Sony WH-1000XM5 headphones, $348, Electronics"',
  responseFormat => 'STRUCT<result: STRUCT<product_name: STRING, price: DOUBLE, category: STRING>>'
) AS extracted;
```

### 資料表批次推論

```sql
-- 對資料表中所有列進行分類
SELECT
  review_id,
  review_text,
  ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    CONCAT('Classify the following review as positive, negative, or neutral: ', review_text),
    responseFormat => 'STRUCT<result: STRUCT<sentiment: STRING, confidence: STRING>>'
  ) AS classification
FROM catalog.schema.product_reviews;
```

### 自訂 ML 模型推論

```sql
-- 查詢自訂 sklearn/MLflow 模型
SELECT ai_query(
  endpoint  => 'spam-classification-endpoint',
  request   => named_struct(
    'text', email_body,
    'subject', email_subject
  ),
  returnType => 'BOOLEAN'
) AS is_spam
FROM catalog.schema.inbox_messages;
```

### 多模態（影像）輸入

```sql
-- 使用視覺模型分析影像
SELECT ai_query(
  'databricks-meta-llama-3-2-90b-instruct',
  'Describe the contents of this image.',
  files => READ_FILES('/Volumes/catalog/schema/images/photo.jpg', format => 'binaryFile')
) AS description;
```

### 使用 failOnError 處理錯誤

```sql
-- 批次處理的優雅錯誤處理
SELECT
  id,
  result.result AS answer,
  result.errorMessage AS error
FROM (
  SELECT
    id,
    ai_query(
      'databricks-meta-llama-3-3-70b-instruct',
      question,
      failOnError => false
    ) AS result
  FROM catalog.schema.questions
);
```

### 生成 Embedding

```sql
-- 使用 ai_query 生成 embedding
SELECT
  text,
  ai_query('databricks-gte-large-en', text) AS embedding
FROM catalog.schema.documents;
```

---

## 特定任務 AI 函式

這些函式提供簡化的單一用途介面，無需指定 endpoint 或模型。

### ai_gen

從提示詞生成文字。

```sql
ai_gen(prompt)
```

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `prompt` | STRING | 使用者的請求/提示詞 |

**回傳：** STRING

```sql
-- 簡單生成
SELECT ai_gen('Generate a concise, cheerful email title for a summer bike sale with 20% discount');
-- 回傳："Summer Bike Sale: Grab Your Dream Bike at 20% Off!"

-- 使用資料表資料生成
SELECT
  question,
  ai_gen('You are a teacher. Answer the students question in 50 words: ' || question) AS answer
FROM catalog.schema.questions
LIMIT 10;
```

---

### ai_classify

將文字分類至提供的標籤之一。

```sql
ai_classify(content, labels)
```

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 要分類的文字 |
| `labels` | ARRAY<STRING> | 分類選項（最少 2 個，最多 20 個元素） |

**回傳：** STRING，符合其中一個標籤；分類失敗時回傳 NULL。

```sql
-- 簡單分類
SELECT ai_classify('My password is leaked.', ARRAY('urgent', 'not urgent'));
-- 回傳："urgent"

-- 批次產品分類
SELECT
  product_name,
  description,
  ai_classify(description, ARRAY('clothing', 'shoes', 'accessories', 'furniture')) AS category
FROM catalog.schema.products
LIMIT 100;

-- 客服票單路由
SELECT
  ticket_id,
  ai_classify(
    description,
    ARRAY('billing', 'technical', 'account', 'feature_request', 'other')
  ) AS department
FROM catalog.schema.support_tickets;
```

---

### ai_extract

從文字中擷取命名實體。

```sql
ai_extract(content, labels)
```

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 要擷取實體的文字 |
| `labels` | ARRAY<STRING> | 要擷取的實體型別 |

**回傳：** STRUCT，其中每個欄位對應一個標籤，包含擷取的實體（STRING）。內容為 NULL 時回傳 NULL。

```sql
-- 擷取人物、地點、組織
SELECT ai_extract(
  'John Doe lives in New York and works for Acme Corp.',
  ARRAY('person', 'location', 'organization')
);
-- 回傳：{"person": "John Doe", "location": "New York", "organization": "Acme Corp."}

-- 擷取聯絡資訊
SELECT ai_extract(
  'Send an email to jane.doe@example.com about the meeting at 10am.',
  ARRAY('email', 'time')
);
-- 回傳：{"email": "jane.doe@example.com", "time": "10am"}

-- 從客戶回饋批次擷取實體
SELECT
  feedback_id,
  ai_extract(feedback_text, ARRAY('product', 'issue', 'person')) AS entities
FROM catalog.schema.customer_feedback;
```

---

### ai_analyze_sentiment

對文字進行情感分析。

```sql
ai_analyze_sentiment(content)
```

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 要分析的文字 |

**回傳：** STRING -- `'positive'`、`'negative'`、`'neutral'` 或 `'mixed'` 其中之一。若無法判斷情感則回傳 NULL。

```sql
SELECT ai_analyze_sentiment('I am happy');     -- 回傳："positive"
SELECT ai_analyze_sentiment('I am sad');       -- 回傳："negative"
SELECT ai_analyze_sentiment('It is what it is'); -- 回傳："neutral"

-- 依產品彙總情感
SELECT
  product_id,
  ai_analyze_sentiment(review_text) AS sentiment,
  COUNT(*) AS review_count
FROM catalog.schema.reviews
GROUP BY product_id, ai_analyze_sentiment(review_text);
```

---

### ai_similarity

計算兩段文字之間的語意相似度。

```sql
ai_similarity(expr1, expr2)
```

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `expr1` | STRING | 要比較的第一段文字 |
| `expr2` | STRING | 要比較的第二段文字 |

**回傳：** FLOAT -- 語意相似度分數，1.0 表示完全相同。此分數為相對值，僅供排名使用。

```sql
-- 完全相符
SELECT ai_similarity('Apache Spark', 'Apache Spark');
-- 回傳：1.0

-- 尋找相似公司名稱（模糊比對）
SELECT company_name, ai_similarity(company_name, 'Databricks') AS score
FROM catalog.schema.customers
ORDER BY score DESC
LIMIT 10;

-- 重複偵測
SELECT
  a.id AS id_a,
  b.id AS id_b,
  ai_similarity(a.description, b.description) AS similarity
FROM catalog.schema.products a
JOIN catalog.schema.products b ON a.id < b.id
WHERE ai_similarity(a.description, b.description) > 0.85;
```

---

### ai_summarize

生成文字摘要。

```sql
ai_summarize(content [, max_words])
```

| 參數 | 型別 | 必要 | 說明 |
|-----------|------|----------|-------------|
| `content` | STRING | 是 | 要摘要的文字 |
| `max_words` | INTEGER | 否 | 摘要的目標字數。預設：50。設為 0 則不限制 |

**回傳：** STRING。內容為 NULL 時回傳 NULL。

```sql
-- 以預設 50 字限制進行摘要
SELECT ai_summarize(
  'Apache Spark is a unified analytics engine for large-scale data processing. '
  || 'It provides high-level APIs in Java, Scala, Python and R, and an optimized '
  || 'engine that supports general execution graphs.'
);

-- 以自訂字數限制進行摘要
SELECT ai_summarize(article_body, 100) AS summary
FROM catalog.schema.articles;

-- 為報告生成高階摘要
SELECT
  report_id,
  report_title,
  ai_summarize(report_body, 30) AS executive_summary
FROM catalog.schema.quarterly_reports;
```

---

### ai_translate

將文字翻譯成目標語言。

```sql
ai_translate(content, to_lang)
```

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 要翻譯的文字 |
| `to_lang` | STRING | 目標語言代碼 |

**支援語言：** 英文（`en`）、德文（`de`）、法文（`fr`）、義大利文（`it`）、葡萄牙文（`pt`）、北印度文（`hi`）、西班牙文（`es`）、泰文（`th`）。

**回傳：** STRING。內容為 NULL 時回傳 NULL。

```sql
-- 英文轉西班牙文
SELECT ai_translate('Hello, how are you?', 'es');
-- 回傳："Hola, como estas?"

-- 西班牙文轉英文
SELECT ai_translate('La vida es un hermoso viaje.', 'en');
-- 回傳："Life is a beautiful journey."

-- 翻譯產品描述以進行在地化
SELECT
  product_id,
  description AS original,
  ai_translate(description, 'fr') AS french,
  ai_translate(description, 'de') AS german
FROM catalog.schema.products;
```

---

### ai_fix_grammar

修正文字中的文法錯誤。

```sql
ai_fix_grammar(content)
```

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 要修正的文字 |

**回傳：** 文法已修正的 STRING。內容為 NULL 時回傳 NULL。

```sql
SELECT ai_fix_grammar('This sentence have some mistake');
-- 回傳："This sentence has some mistakes"

SELECT ai_fix_grammar('She dont know what to did.');
-- 回傳："She doesn't know what to do."

-- 清理使用者生成的內容
SELECT
  comment_id,
  original_text,
  ai_fix_grammar(original_text) AS corrected_text
FROM catalog.schema.user_comments;
```

---

### ai_mask

遮罩文字中指定的實體型別（PII 去識別化）。

```sql
ai_mask(content, labels)
```

| 參數 | 型別 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 包含要遮罩實體的文字 |
| `labels` | ARRAY<STRING> | 要遮罩的實體型別（例如 `'person'`、`'email'`、`'phone'`、`'address'`、`'location'`、`'ssn'`、`'credit_card'`） |

**回傳：** 指定實體被替換為 `[MASKED]` 的 STRING。內容為 NULL 時回傳 NULL。

```sql
-- 遮罩個人資訊
SELECT ai_mask(
  'John Doe lives in New York. His email is john.doe@example.com.',
  ARRAY('person', 'email')
);
-- 回傳："[MASKED] lives in New York. His email is [MASKED]."

-- 遮罩聯絡資訊
SELECT ai_mask(
  'Contact me at 555-1234 or visit us at 123 Main St.',
  ARRAY('phone', 'address')
);
-- 回傳："Contact me at [MASKED] or visit us at [MASKED]"

-- 建立匿名化資料集
CREATE TABLE catalog.schema.anonymized_feedback AS
SELECT
  feedback_id,
  ai_mask(feedback_text, ARRAY('person', 'email', 'phone', 'address')) AS masked_text,
  category
FROM catalog.schema.customer_feedback;
```

---

## 文件與多模態 AI 函式

### ai_parse_document

從非結構化文件（PDF、DOCX、PPTX、影像）中擷取結構化內容。

```sql
ai_parse_document(content)
ai_parse_document(content, options_map)
```

| 參數 | 型別 | 必要 | 說明 |
|-----------|------|----------|-------------|
| `content` | BINARY | 是 | 以 binary blob 形式表示的文件資料 |
| `options` | MAP<STRING, STRING> | 否 | 設定選項 |

**Options Map 鍵值：**

| 鍵 | 值 | 說明 |
|-----|--------|-------------|
| `version` | `'2.0'` | 輸出 schema 版本 |
| `imageOutputPath` | Volume 路徑 | 儲存渲染頁面影像至 Unity Catalog volume 的路徑 |
| `descriptionElementTypes` | `''`、`'figure'`、`'*'` | 控制 AI 生成描述。預設：`'*'`（所有元素） |

**回傳：** VARIANT，結構如下：
- `document.pages[]` -- 頁面詮釋資料（id、image_uri）
- `document.elements[]` -- 擷取的內容（type、content、bbox、description）
- `error_status[]` -- 每頁的錯誤詳情
- `metadata` -- 檔案與 schema 版本資訊

**支援格式：** PDF、JPG/JPEG、PNG、DOC/DOCX、PPT/PPTX

**需求：** Databricks Runtime 17.1+，US/EU 區域或已啟用跨地理路由。

```sql
-- 基本文件解析
SELECT ai_parse_document(content)
FROM READ_FILES('/Volumes/catalog/schema/volume/docs/', format => 'binaryFile');

-- 使用選項解析（儲存影像，2.0 版本）
SELECT ai_parse_document(
  content,
  map(
    'version', '2.0',
    'imageOutputPath', '/Volumes/catalog/schema/volume/images/',
    'descriptionElementTypes', '*'
  )
)
FROM READ_FILES('/Volumes/catalog/schema/volume/invoices/', format => 'binaryFile');

-- 解析文件後使用 ai_query 擷取結構化資料
WITH parsed AS (
  SELECT
    path,
    ai_parse_document(content) AS doc
  FROM READ_FILES('/Volumes/catalog/schema/volume/invoices/', format => 'binaryFile')
)
SELECT
  path,
  ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    CONCAT('Extract vendor name, invoice number, and total from: ', doc:document:elements[0]:content::STRING),
    responseFormat => 'STRUCT<vendor: STRING, invoice_number: STRING, total: DOUBLE>'
  ) AS invoice_data
FROM parsed;
```

---

## 時間序列 AI 函式

### ai_forecast

使用內建的類 prophet 模型預測時間序列資料。這是一個資料表值函式（TVF）。

```sql
ai_forecast(
  observed                  TABLE,
  horizon                   DATE | TIMESTAMP | STRING,
  time_col                  STRING,
  value_col                 STRING | ARRAY<STRING>,
  group_col                 STRING | ARRAY<STRING> | NULL  DEFAULT NULL,
  prediction_interval_width DOUBLE                         DEFAULT 0.95,
  frequency                 STRING                         DEFAULT 'auto',
  seed                      INTEGER | NULL                 DEFAULT NULL,
  parameters                STRING                         DEFAULT '{}'
)
```

### 參數

| 參數 | 型別 | 預設 | 說明 |
|-----------|------|---------|-------------|
| `observed` | TABLE | 必要 | 以 `TABLE(subquery)` 或 `TABLE(table_name)` 傳入的訓練資料 |
| `horizon` | DATE/TIMESTAMP/STRING | 必要 | 右開區間的預測結束時間 |
| `time_col` | STRING | 必要 | 觀測資料中 DATE 或 TIMESTAMP 欄位的名稱 |
| `value_col` | STRING or ARRAY<STRING> | 必要 | 要預測的一或多個數值欄位 |
| `group_col` | STRING、ARRAY<STRING> 或 NULL | NULL | 用於各群組獨立預測的分割欄位 |
| `prediction_interval_width` | DOUBLE | 0.95 | 預測區間的信賴水準（0 到 1） |
| `frequency` | STRING | `'auto'` | 時間粒度。自動從最近資料推論。DATE 欄位使用：`'day'`、`'week'`、`'month'`。TIMESTAMP 欄位使用：`'D'`、`'W'`、`'M'`、`'H'` 等 |
| `seed` | INTEGER or NULL | NULL | 可重現性的隨機種子 |
| `parameters` | STRING | `'{}'` | JSON 編碼的進階設定 |

**進階參數（JSON）：**
- `global_cap` -- 邏輯成長的上限
- `global_floor` -- 邏輯成長的下限
- `daily_order` -- 每日季節性的 Fourier 階數
- `weekly_order` -- 每週季節性的 Fourier 階數

### 回傳欄位

對於每個名為 `v` 的 `value_col`，輸出包含：
- `{v}_forecast`（DOUBLE）-- 點預測值
- `{v}_upper`（DOUBLE）-- 預測上界
- `{v}_lower`（DOUBLE）-- 預測下界
- 加上原始時間欄位與群組欄位

**需求：** Serverless SQL Warehouse。

```sql
-- 基本營收預測
SELECT * FROM ai_forecast(
  TABLE(SELECT ds, revenue FROM catalog.schema.daily_sales),
  horizon    => '2025-12-31',
  time_col   => 'ds',
  value_col  => 'revenue'
);

-- 依群組多指標預測
SELECT * FROM ai_forecast(
  TABLE(
    SELECT date, zipcode, revenue, trip_count
    FROM catalog.schema.regional_metrics
  ),
  horizon                   => '2025-06-30',
  time_col                  => 'date',
  value_col                 => ARRAY('revenue', 'trip_count'),
  group_col                 => 'zipcode',
  prediction_interval_width => 0.90,
  frequency                 => 'D'
);

-- 帶成長限制的月度預測（DATE 欄位使用 'month' 而非 'M'）
SELECT * FROM ai_forecast(
  TABLE(catalog.schema.monthly_kpis),
  horizon    => '2026-01-01',
  time_col   => 'month',
  value_col  => 'active_users',
  frequency  => 'month',
  parameters => '{"global_floor": 0}'
);
```

---

## 向量搜尋函式

### vector_search

使用 SQL 查詢 Mosaic AI Vector Search 索引。這是一個資料表值函式。

```sql
-- Databricks Runtime 15.3+
SELECT * FROM vector_search(
  index       => index_name,
  query_text  => search_text,         -- 或 query_vector => embedding_array
  num_results => max_results,
  query_type  => 'ANN' | 'HYBRID'
)
```

### 參數（需使用具名引數）

| 參數 | 型別 | 預設 | 說明 |
|-----------|------|---------|-------------|
| `index` | STRING 常數 | 必要 | 向量搜尋索引的完整限定名稱 |
| `query_text` | STRING | -- | 搜尋字串（用於具有 embedding 來源的 Delta Sync 索引） |
| `query_vector` | ARRAY<FLOAT\\|DOUBLE\\|DECIMAL> | -- | 預先計算的 embedding 向量以供搜尋 |
| `num_results` | INTEGER | 10 | 最大回傳筆數（最多 100） |
| `query_type` | STRING | `'ANN'` | `'ANN'` 為近似最近鄰，`'HYBRID'` 為混合搜尋 |

**回傳：** 包含所有索引欄位及最符合記錄的資料表。

**需求：** Serverless SQL Warehouse，索引的 Select 權限。

```sql
-- 以文字為基礎的相似度搜尋
SELECT * FROM vector_search(
  index      => 'catalog.schema.product_index',
  query_text => 'wireless noise canceling headphones',
  num_results => 5
);

-- 混合搜尋（結合關鍵字 + 語意）
SELECT * FROM vector_search(
  index       => 'catalog.schema.support_docs_index',
  query_text  => 'Wi-Fi connection issues with router model LMP-9R2',
  query_type  => 'HYBRID',
  num_results => 3
);

-- 以預先計算 embedding 進行向量搜尋
SELECT * FROM vector_search(
  index        => 'catalog.schema.embeddings_index',
  query_vector => ARRAY(0.45, -0.35, 0.78, 0.22),
  num_results  => 10
);

-- 使用 LATERAL join 進行批次搜尋
SELECT
  q.query_text,
  q.query_id,
  results.*
FROM catalog.schema.search_queries q,
LATERAL (
  SELECT * FROM vector_search(
    index       => 'catalog.schema.knowledge_base_index',
    query_text  => q.query_text,
    num_results => 3
  )
) AS results;
```

---

## http_request 函式

使用 Unity Catalog HTTP 連線，從 SQL 對外部服務發出 HTTP 請求。

### 語法

```sql
http_request(
  CONN    => connection_name,
  METHOD  => http_method,
  PATH    => path,
  HEADERS => header_map,
  PARAMS  => param_map,
  JSON    => json_body
)
```

### 參數

| 參數 | 型別 | 必要 | 說明 |
|-----------|------|----------|-------------|
| `CONN` | STRING 常數 | 是 | 現有 HTTP 連線的名稱 |
| `METHOD` | STRING 常數 | 是 | HTTP 方法：`'GET'`、`'POST'`、`'PUT'`、`'DELETE'`、`'PATCH'` |
| `PATH` | STRING 常數 | 是 | 附加至連線 base_path 的路徑。不得包含目錄遍歷（`../`） |
| `HEADERS` | MAP<STRING, STRING> | 否 | 請求標頭。預設：NULL |
| `PARAMS` | MAP<STRING, STRING> | 否 | 查詢參數。預設：NULL |
| `JSON` | STRING expression | 否 | JSON 字串格式的請求本體 |

### 回傳型別

`STRUCT<status_code: INT, text: STRING>`
- `status_code` -- HTTP 回應狀態碼（例如 200、403、404）
- `text` -- 回應本體（通常為 JSON）

**需求：** Databricks Runtime 16.2+，已啟用 Unity Catalog 的工作區，USE CONNECTION 權限。

### 建立 HTTP 連線

```sql
-- Bearer token 驗證
CREATE CONNECTION slack_conn TYPE HTTP
OPTIONS (
  host         'https://slack.com',
  port         '443',
  base_path    '/api/',
  bearer_token secret('my-scope', 'slack-token')
);

-- OAuth Machine-to-Machine
CREATE CONNECTION github_conn TYPE HTTP
OPTIONS (
  host           'https://api.github.com',
  port           '443',
  base_path      '/',
  client_id      secret('my-scope', 'github-client-id'),
  client_secret  secret('my-scope', 'github-client-secret'),
  oauth_scope    'repo read:org',
  token_endpoint 'https://github.com/login/oauth/access_token'
);
```

**連線選項：**

| 選項 | 型別 | 說明 |
|--------|------|-------------|
| `host` | STRING | 外部服務的基礎 URL |
| `port` | STRING | 網路連接埠（HTTPS 通常為 `'443'`） |
| `base_path` | STRING | API endpoint 的根路徑 |
| `bearer_token` | STRING | 驗證 token（建議使用 `secret()` 確保安全） |
| `client_id` | STRING | OAuth 應用程式識別碼 |
| `client_secret` | STRING | OAuth 應用程式密鑰 |
| `oauth_scope` | STRING | 以空格分隔的 OAuth scope |
| `token_endpoint` | STRING | OAuth token endpoint URL |
| `authorization_endpoint` | STRING | OAuth 授權重新導向 URL |
| `oauth_credential_exchange_method` | STRING | `'header_and_body'`、`'body_only'` 或 `'header_only'` |

### 範例

```sql
-- POST 一則 Slack 訊息
SELECT http_request(
  CONN   => 'slack_conn',
  METHOD => 'POST',
  PATH   => '/chat.postMessage',
  JSON   => to_json(named_struct('channel', '#alerts', 'text', 'Pipeline completed successfully'))
);

-- 帶標頭與參數的 GET 請求
SELECT http_request(
  CONN    => 'github_conn',
  METHOD  => 'GET',
  PATH    => '/repos/databricks/spark/issues',
  HEADERS => map('Accept', 'application/vnd.github+json'),
  PARAMS  => map('state', 'open', 'per_page', '5')
);

-- 解析 JSON 回應
SELECT
  response.status_code,
  from_json(response.text, 'STRUCT<id: INT, title: STRING, state: STRING>') AS issue
FROM (
  SELECT http_request(
    CONN   => 'github_conn',
    METHOD => 'GET',
    PATH   => '/repos/databricks/spark/issues/1'
  ) AS response
);

-- 由資料變更觸發的 Webhook 通知
SELECT http_request(
  CONN   => 'webhook_conn',
  METHOD => 'POST',
  PATH   => '/notify',
  JSON   => to_json(named_struct(
    'event', 'data_quality_alert',
    'table', 'catalog.schema.orders',
    'message', CONCAT('Null rate exceeded threshold: ', CAST(null_pct AS STRING))
  ))
)
FROM catalog.schema.data_quality_metrics
WHERE null_pct > 0.05;
```

---

## remote_query 函式（Lakehouse Federation）

使用外部資料庫的原生 SQL 語法對其執行查詢，並以 Databricks SQL 資料表的形式回傳結果。這是一個資料表值函式。

### 概覽

Lakehouse Federation 可在不移轉資料的情況下查詢外部資料庫。支援兩種模式：
- **查詢聯合（Query Federation）** -- 查詢透過 JDBC 下推至外部資料庫
- **目錄聯合（Catalog Federation）** -- 查詢直接存取物件儲存中的外部資料表

### 語法

```sql
SELECT * FROM remote_query(
  '<connection-name>',
  <option-key> => '<option-value>'
  [, ...]
)
```

### 支援的資料庫

| 資料庫 | 連線型別 |
|----------|----------------|
| PostgreSQL | `POSTGRESQL` |
| MySQL | `MYSQL` |
| Microsoft SQL Server | `SQLSERVER` |
| Oracle | `ORACLE` |
| Teradata | `TERADATA` |
| Amazon Redshift | `REDSHIFT` |
| Snowflake | `SNOWFLAKE` |
| Google BigQuery | `BIGQUERY` |
| Databricks | `DATABRICKS` |

### 依資料庫型別的參數

**PostgreSQL / MySQL / SQL Server / Redshift / Teradata：**

| 參數 | 型別 | 必要 | 說明 |
|-----------|------|----------|-------------|
| `database` | STRING | 是 | 遠端資料庫名稱 |
| `query` | STRING | 二選一（query/dbtable） | 遠端資料庫原生語法的 SQL 查詢 |
| `dbtable` | STRING | 二選一（query/dbtable） | 完整限定資料表名稱 |
| `fetchsize` | STRING | 否 | 每次往返擷取的列數 |
| `partitionColumn` | STRING | 否 | 用於平行讀取分割的欄位 |
| `lowerBound` | STRING | 否 | 分割欄位的下限 |
| `upperBound` | STRING | 否 | 分割欄位的上限 |
| `numPartitions` | STRING | 否 | 平行分割數量 |

**Oracle（使用 `service_name` 而非 `database`）：**

| 參數 | 型別 | 必要 | 說明 |
|-----------|------|----------|-------------|
| `service_name` | STRING | 是 | Oracle 服務名稱 |
| `query` 或 `dbtable` | STRING | 是（擇一） | 查詢或資料表參考 |

**Snowflake：**

| 參數 | 型別 | 必要 | 說明 |
|-----------|------|----------|-------------|
| `database` | STRING | 是 | Snowflake 資料庫 |
| `schema` | STRING | 否 | Schema 名稱（預設為 `public`） |
| `query` 或 `dbtable` | STRING | 是（擇一） | 查詢或資料表參考 |
| `query_timeout` | STRING | 否 | 查詢逾時秒數 |
| `partition_size_in_mb` | STRING | 否 | 讀取的分割大小 |

**BigQuery：**

| 參數 | 型別 | 必要 | 說明 |
|-----------|------|----------|-------------|
| `query` 或 `dbtable` | STRING | 是（擇一） | 查詢或資料表參考 |
| `materializationDataset` | STRING | 用於視圖/複雜查詢 | 實體化的資料集 |
| `materializationProject` | STRING | 否 | 實體化的 GCP 專案 |
| `parentProject` | STRING | 否 | 父 GCP 專案 |

### 下推控制

| 選項 | 預設 | 說明 |
|--------|---------|-------------|
| `pushdown.limit.enabled` | `true` | 將 LIMIT 下推至遠端 |
| `pushdown.offset.enabled` | `true` | 將 OFFSET 下推至遠端 |
| `pushdown.filters.enabled` | `true` | 將 WHERE 篩選條件下推至遠端 |
| `pushdown.aggregates.enabled` | `true` | 將彙總下推至遠端 |
| `pushdown.sortLimit.enabled` | `true` | 將 ORDER BY + LIMIT 下推至遠端 |

### 需求

- 已啟用 Unity Catalog 的工作區
- Databricks Runtime 17.3+（叢集）或 SQL Warehouse 2025.35+（Pro/Serverless）
- 可連線至目標資料庫的網路
- `USE CONNECTION` 權限，或對包裝視圖的 `SELECT` 權限

### 限制

- **唯讀**：僅支援 SELECT 查詢（不支援 INSERT、UPDATE、DELETE、MERGE、DDL 或預存程序）

### 建立連線

```sql
-- PostgreSQL 連線
CREATE CONNECTION my_postgres TYPE POSTGRESQL
OPTIONS (
  host     'pg-server.example.com',
  port     '5432',
  user     secret('my-scope', 'pg-user'),
  password secret('my-scope', 'pg-password')
);

-- SQL Server 連線
CREATE CONNECTION my_sqlserver TYPE SQLSERVER
OPTIONS (
  host     'sql-server.example.com',
  port     '1433',
  user     secret('my-scope', 'sql-user'),
  password secret('my-scope', 'sql-password')
);
```

### 範例

```sql
-- 對 PostgreSQL 執行基本查詢
SELECT * FROM remote_query(
  'my_postgres',
  database => 'sales_db',
  query    => 'SELECT customer_id, name, email FROM customers WHERE active = true'
);

-- 從 SQL Server 平行讀取
SELECT * FROM remote_query(
  'my_sqlserver',
  database        => 'orders_db',
  dbtable         => 'dbo.transactions',
  partitionColumn => 'transaction_id',
  lowerBound      => '0',
  upperBound      => '1000000',
  numPartitions   => '10'
);

-- 聯合資料與本地 Delta 資料表進行 JOIN
SELECT
  o.order_id,
  o.amount,
  c.name,
  c.email
FROM catalog.schema.orders o
JOIN remote_query(
  'my_postgres',
  database => 'crm_db',
  query    => 'SELECT customer_id, name, email FROM customers'
) c ON o.customer_id = c.customer_id;

-- 透過視圖進行存取委派
CREATE VIEW catalog.schema.federated_customers AS
SELECT * FROM remote_query(
  'my_postgres',
  database => 'crm_db',
  query    => 'SELECT customer_id, name, region FROM customers'
);

-- 使用者只需要視圖的 SELECT 權限，無需 USE CONNECTION
GRANT SELECT ON VIEW catalog.schema.federated_customers TO `analysts`;
```

---

## read_files 資料表值函式

直接在 SQL 中讀取雲端儲存或 Unity Catalog volumes 中的檔案，支援自動格式偵測與 schema 推論。

### 語法

```sql
SELECT * FROM read_files(
  path
  [, option_key => option_value ] [...]
)
```

### 核心參數

| 參數 | 型別 | 必要 | 說明 |
|-----------|------|----------|-------------|
| `path` | STRING | 是 | 資料位置的 URI。支援 `s3://`、`abfss://`、`gs://`、`/Volumes/...` 路徑。接受 glob 模式 |

### 常用選項

| 選項 | 型別 | 預設 | 說明 |
|--------|------|---------|-------------|
| `format` | STRING | 自動偵測 | 檔案格式：`'csv'`、`'json'`、`'parquet'`、`'avro'`、`'orc'`、`'text'`、`'binaryFile'`、`'xml'` |
| `schema` | STRING | 推論 | DDL 格式的明確 schema 定義 |
| `schemaHints` | STRING | 無 | 覆寫推論 schema 的部分欄位 |
| `rescuedDataColumn` | STRING | `'_rescued_data'` | 無法解析的資料欄位名稱。設為空字串可停用 |
| `pathGlobFilter` / `fileNamePattern` | STRING | 無 | 篩選檔案的 glob 模式（例如 `'*.csv'`） |
| `recursiveFileLookup` | BOOLEAN | `false` | 搜尋巢狀目錄 |
| `modifiedAfter` | TIMESTAMP STRING | 無 | 僅讀取此時間戳記之後修改的檔案 |
| `modifiedBefore` | TIMESTAMP STRING | 無 | 僅讀取此時間戳記之前修改的檔案 |
| `partitionColumns` | STRING | 自動偵測 | 以逗號分隔的 Hive 式分割欄位。空字串忽略所有分割 |
| `useStrictGlobber` | BOOLEAN | `true` | 嚴格 glob 模式比對 |
| `inferColumnTypes` | BOOLEAN | `true` | 推論精確欄位型別（而非全部視為 STRING） |
| `schemaEvolutionMode` | STRING | -- | Schema 演進行為：`'none'` 可移除救援資料欄位 |

### CSV 特定選項

| 選項 | 型別 | 預設 | 說明 |
|--------|------|---------|-------------|
| `sep` / `delimiter` | STRING | `','` | 欄位分隔符號 |
| `header` | BOOLEAN | `false` | 第一列包含欄位名稱 |
| `encoding` | STRING | `'UTF-8'` | 字元編碼 |
| `quote` | STRING | `'"'` | 引號字元 |
| `escape` | STRING | `'\\'` | 跳脫字元 |
| `nullValue` | STRING | `''` | null 的字串表示 |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | 日期解析格式 |
| `timestampFormat` | STRING | `'yyyy-MM-dd\\'T\\'HH:mm:ss...'` | 時間戳記解析格式 |
| `mode` | STRING | `'PERMISSIVE'` | 解析模式：`'PERMISSIVE'`、`'DROPMALFORMED'`、`'FAILFAST'` |
| `multiLine` | BOOLEAN | `false` | 允許記錄跨越多列 |
| `ignoreLeadingWhiteSpace` | BOOLEAN | `false` | 修剪前置空白 |
| `ignoreTrailingWhiteSpace` | BOOLEAN | `false` | 修剪尾端空白 |
| `comment` | STRING | 無 | 列注釋字元 |
| `maxCharsPerColumn` | INTEGER | 無 | 每欄最大字元數 |
| `maxColumns` | INTEGER | 無 | 最大欄位數 |
| `mergeSchema` | BOOLEAN | `false` | 合併跨檔案的 schema |
| `enforceSchema` | BOOLEAN | `true` | 強制套用指定的 schema |
| `locale` | STRING | `'US'` | 數字/日期解析的語系 |
| `charToEscapeQuoteEscaping` | STRING | 無 | 用於跳脫引號跳脫字元的字元 |
| `readerCaseSensitive` | BOOLEAN | `true` | 欄位名稱區分大小寫的比對 |

### JSON 特定選項

| 選項 | 型別 | 預設 | 說明 |
|--------|------|---------|-------------|
| `multiLine` | BOOLEAN | `false` | 解析多列 JSON 記錄 |
| `allowComments` | BOOLEAN | `false` | 允許 Java/C++ 風格的注釋 |
| `allowSingleQuotes` | BOOLEAN | `true` | 允許字串使用單引號 |
| `allowUnquotedFieldNames` | BOOLEAN | `false` | 允許未加引號的欄位名稱 |
| `allowBackslashEscapingAnyCharacter` | BOOLEAN | `false` | 允許反斜線跳脫任意字元 |
| `allowNonNumericNumbers` | BOOLEAN | `true` | 允許 NaN、Infinity、-Infinity |
| `encoding` | STRING | `'UTF-8'` | 字元編碼 |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | 日期解析格式 |
| `timestampFormat` | STRING | -- | 時間戳記解析格式 |
| `inferTimestamp` | BOOLEAN | `false` | 推論時間戳記型別 |
| `prefersDecimal` | BOOLEAN | `false` | 偏好 DECIMAL 而非 DOUBLE |
| `primitivesAsString` | BOOLEAN | `false` | 將所有基本型別推論為 STRING |
| `singleVariantColumn` | STRING | 無 | 將整個 JSON 讀入單一 VARIANT 欄位 |
| `locale` | STRING | `'US'` | 解析語系 |
| `mode` | STRING | `'PERMISSIVE'` | 解析模式 |
| `readerCaseSensitive` | BOOLEAN | `true` | 欄位比對區分大小寫 |
| `timeZone` | STRING | 工作階段時區 | 時間戳記解析的時區 |

### XML 特定選項

| 選項 | 型別 | 預設 | 說明 |
|--------|------|---------|-------------|
| `rowTag` | STRING | **必要** | 分隔列的 XML 標籤 |
| `attributePrefix` | STRING | `'_'` | XML 屬性的前綴 |
| `valueTag` | STRING | `'_VALUE'` | 元素文字內容的標籤 |
| `encoding` | STRING | `'UTF-8'` | 字元編碼 |
| `ignoreSurroundingSpaces` | BOOLEAN | `true` | 忽略值周圍的空白 |
| `ignoreNamespace` | BOOLEAN | `false` | 忽略 XML 命名空間 |
| `mode` | STRING | `'PERMISSIVE'` | 解析模式 |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | 日期解析格式 |
| `timestampFormat` | STRING | -- | 時間戳記解析格式 |
| `locale` | STRING | `'US'` | 解析語系 |
| `readerCaseSensitive` | BOOLEAN | `true` | 區分大小寫比對 |
| `samplingRatio` | DOUBLE | `1.0` | 用於 schema 推論的資料列取樣比例 |

### Parquet / Avro / ORC 選項

| 選項 | 型別 | 預設 | 說明 |
|--------|------|---------|-------------|
| `mergeSchema` | BOOLEAN | `false` | 合併跨檔案的 schema |
| `readerCaseSensitive` | BOOLEAN | `true` | 欄位比對區分大小寫 |
| `rescuedDataColumn` | STRING | -- | 救援資料的欄位 |
| `datetimeRebaseMode` | STRING | -- | 日期時間值的重新基準模式 |
| `int96RebaseMode` | STRING | -- | INT96 時間戳記的重新基準模式（僅 Parquet） |

### 串流選項

| 選項 | 型別 | 預設 | 說明 |
|--------|------|---------|-------------|
| `includeExistingFiles` | BOOLEAN | `true` | 第一次執行時處理現有檔案 |
| `maxFilesPerTrigger` | INTEGER | 無 | 每個微批次的最大檔案數 |
| `maxBytesPerTrigger` | STRING | 無 | 每個微批次的最大位元組數 |
| `allowOverwrites` | BOOLEAN | `false` | 允許處理已覆寫的檔案 |
| `schemaEvolutionMode` | STRING | -- | Schema 演進行為 |
| `schemaLocation` | STRING | -- | 儲存推論 schema 的位置 |

### 需求

- Databricks Runtime 13.3 LTS 及以上版本
- Databricks SQL

### 範例

```sql
-- 從雲端儲存自動偵測格式與 schema
SELECT * FROM read_files('s3://my-bucket/data/');

-- 以明確 schema 讀取 CSV
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/sales.csv',
  format => 'csv',
  header => true,
  schema => 'order_id INT, customer_id INT, amount DOUBLE, order_date DATE'
);

-- 以 schema hints 讀取 CSV（僅覆寫特定欄位）
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/events/',
  format      => 'csv',
  header      => true,
  schemaHints => 'event_timestamp TIMESTAMP, amount DECIMAL(10,2)'
);

-- 讀取支援多列的 JSON
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/api_responses/',
  format    => 'json',
  multiLine => true
);

-- 讀取合併跨檔案 schema 的 Parquet
SELECT * FROM read_files(
  's3://my-bucket/parquet-data/',
  format      => 'parquet',
  mergeSchema => true
);

-- 讀取帶 row tag 的 XML
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/feed.xml',
  format => 'xml',
  rowTag => 'record'
);

-- 讀取二進位檔案（影像、PDF）供 ai_parse_document 使用
SELECT path, content FROM read_files(
  '/Volumes/catalog/schema/volume/documents/',
  format => 'binaryFile'
);

-- 以 glob 模式與修改日期篩選檔案
SELECT * FROM read_files(
  's3://my-bucket/logs/',
  format          => 'json',
  pathGlobFilter  => '*.json',
  modifiedAfter   => '2025-01-01T00:00:00Z',
  modifiedBefore  => '2025-02-01T00:00:00Z'
);

-- 遞迴掃描目錄並自動發現分割
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/partitioned_data/',
  recursiveFileLookup => true,
  partitionColumns    => 'year,month'
);

-- 包含檔案詮釋資料
SELECT *, _metadata.file_path, _metadata.file_name, _metadata.file_size
FROM read_files('/Volumes/catalog/schema/volume/data/');

-- 從檔案建立資料表
CREATE TABLE catalog.schema.imported_data AS
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/export.csv',
  format => 'csv',
  header => true
);

-- 從雲端儲存建立串流資料表
CREATE STREAMING TABLE catalog.schema.streaming_events AS
SELECT * FROM STREAM read_files(
  's3://my-bucket/events/',
  format              => 'json',
  includeExistingFiles => false,
  maxFilesPerTrigger   => 100
);

-- 讀取半結構化 JSON 的單一 VARIANT 欄位
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/complex.json',
  format              => 'json',
  singleVariantColumn => 'raw_data'
);
```

---

## 組合函式 -- 生產環境模式

### AI 強化的 ETL Pipeline

```sql
-- 使用多個 AI 函式處理客戶回饋
CREATE OR REPLACE TABLE catalog.schema.enriched_feedback AS
SELECT
  feedback_id,
  feedback_text,
  ai_analyze_sentiment(feedback_text) AS sentiment,
  ai_classify(feedback_text, ARRAY('product', 'service', 'billing', 'other')) AS category,
  ai_extract(feedback_text, ARRAY('product', 'issue')) AS entities,
  ai_summarize(feedback_text, 20) AS summary,
  ai_mask(feedback_text, ARRAY('person', 'email', 'phone')) AS anonymized_text
FROM catalog.schema.raw_feedback;
```

### 文件處理 Pipeline

```sql
-- 擷取、解析並查詢文件
WITH raw_docs AS (
  SELECT path, content
  FROM read_files('/Volumes/catalog/schema/volume/contracts/', format => 'binaryFile')
),
parsed AS (
  SELECT path, ai_parse_document(content, map('version', '2.0')) AS doc
  FROM raw_docs
)
SELECT
  path,
  ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    CONCAT('Extract the contract parties, effective date, and termination clause from: ',
           doc:document:elements[0]:content::STRING),
    responseFormat => 'STRUCT<party_a: STRING, party_b: STRING, effective_date: STRING, termination_clause: STRING>'
  ) AS contract_info
FROM parsed;
```

### 使用 http_request 的外部 API 整合

```sql
-- 透過呼叫外部 API 豐富資料並 JOIN 結果
SELECT
  o.order_id,
  o.tracking_number,
  from_json(
    tracking.text,
    'STRUCT<status: STRING, location: STRING, estimated_delivery: STRING>'
  ) AS tracking_info
FROM catalog.schema.orders o
CROSS JOIN LATERAL (
  SELECT http_request(
    CONN   => 'shipping_api_conn',
    METHOD => 'GET',
    PATH   => CONCAT('/track/', o.tracking_number)
  ) AS response
) tracking
WHERE tracking.response.status_code = 200;
```

### 聯合分析

```sql
-- 結合遠端資料庫資料、本地 lakehouse 資料與 AI
SELECT
  remote_orders.customer_id,
  remote_orders.total_spend,
  local_profiles.segment,
  ai_classify(
    CONCAT('Customer spent $', CAST(remote_orders.total_spend AS STRING),
           ' in segment ', local_profiles.segment),
    ARRAY('high_value', 'medium_value', 'low_value', 'at_risk')
  ) AS value_tier
FROM remote_query(
  'my_postgres',
  database => 'sales_db',
  query    => 'SELECT customer_id, SUM(amount) as total_spend FROM orders GROUP BY customer_id'
) remote_orders
JOIN catalog.schema.customer_profiles local_profiles
  ON remote_orders.customer_id = local_profiles.customer_id;
```
"""

out = pathlib.Path(r'D:\azure_code\ai-dev-kit\databricks-skills\databricks-dbsql\ai-functions.md')
out.write_text(content, encoding='utf-8')
print(f"Written {len(content)} chars, no BOM")
# Verify no BOM
raw = out.read_bytes()
assert raw[:3] != b'\xef\xbb\xbf', "BOM detected!"
print("BOM check passed")
