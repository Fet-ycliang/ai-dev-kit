# AI Functions、http_request、remote_query 與 read_files 參考

Databricks SQL 進階函式的完整參考：內建 AI functions、HTTP requests、Lakehouse Federation 遠端查詢，以及檔案讀取。

---

## 目錄

- [AI Functions 概覽](#ai-functions-overview)
- [ai_query -- 通用 AI 函式](#ai_query----general-purpose-ai-function)
- [任務專用 AI 函式](#task-specific-ai-functions)
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
- [Vector Search 函式](#vector-search-function)
  - [vector_search](#vector_search)
- [http_request 函式](#http_request-function)
- [remote_query 函式（Lakehouse Federation）](#remote_query-function-lakehouse-federation)
- [read_files 資料表值函式](#read_files-table-valued-function)

---

## AI Functions 概覽

Databricks AI Functions 是內建 SQL 函式，可直接從 SQL 呼叫最先進的生成式 AI 模型。它們執行於 Databricks Foundation Model APIs 之上，並可從 Databricks SQL、notebooks、Lakeflow Spark Declarative Pipelines 與 Workflows 使用。

**所有 AI Functions 的共同需求：**
- Workspace 必須位於支援針對批次推論最佳化之 AI Functions 的區域
- Databricks SQL Classic 不提供（需要 Serverless SQL Warehouse）
- notebooks 需要 Databricks Runtime 15.1+；批次工作負載建議使用 15.4 ML LTS
- 模型採用 Apache 2.0 或 LLAMA 3.3 Community License 授權
- 目前針對英文最佳化（底層模型支援多種語言）
- Public Preview，且符合 HIPAA

**速率限制與計費：**
- AI Functions 受 Foundation Model API 速率限制約束
- 計費方式為 Databricks SQL 運算費用加上 Foundation Model APIs 的 Token 用量
- 開發期間請在查詢中使用 `LIMIT` 以控制成本

---

## ai_query -- 通用 AI 函式

功能最強大且最具彈性的 AI 函式。可查詢任何 serving endpoint（Foundation Models、外部模型或自訂 ML 模型），進行即時或批次推論。

### 語法

```sql
-- 基本呼叫方式
ai_query(endpoint, request)

-- 含所有選用參數的完整呼叫方式
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

| 參數 | 類型 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `endpoint` | STRING | 是 | 同一個 workspace 中的 Foundation Model、外部模型或自訂模型 serving endpoint 名稱 |
| `request` | STRING 或 STRUCT | 是 | 對 LLM endpoint 而言為 STRING prompt；對自訂 ML endpoint 而言為單一欄位或符合預期輸入特徵的 STRUCT |
| `returnType` | Expression | 否 | 預期的回傳型別（DDL 樣式）。在 Runtime 15.2+ 為選用；15.1 與更早版本為必填 |
| `failOnError` | BOOLEAN | 否 | 預設為 `true`。若設為 `false`，會回傳含有 `response` 與 `errorStatus` 欄位的 STRUCT，而不是直接失敗 |
| `modelParameters` | STRUCT | 否 | 透過 `named_struct()` 傳入的模型參數（Runtime 15.3+） |
| `responseFormat` | STRING | 否 | 控制輸出格式：`'text'`、`'json_object'`，或 DDL/JSON schema 字串（Runtime 15.4 LTS+，僅限 chat models） |
| `files` | Expression | 否 | 用於影像處理的多模態檔案輸入（支援 JPEG、PNG） |

### 回傳型別

| 情境 | 回傳型別 |
|----------|-------------|
| `failOnError => true`（預設） | 符合 endpoint 類型或 `returnType` 的已解析回應 |
| `failOnError => false` | `STRUCT<result: T, errorMessage: STRING>`，其中 T 為已解析型別 |
| 使用 `responseFormat` | 符合指定 schema 的結構化輸出 |

### 模型參數

```sql
-- 使用 modelParameters 控制生成結果
SELECT ai_query(
  'databricks-meta-llama-3-3-70b-instruct',
  '請用 3 句話解釋量子運算。',
  modelParameters => named_struct(
    'max_tokens', 256,
    'temperature', 0.1,
    'top_p', 0.9
  )
) AS response;
```

常見模型參數：
- `max_tokens` (INT) -- 要生成的最大 Token 數
- `temperature` (DOUBLE) -- 隨機性（0.0 = 決定性，2.0 = 最大隨機）
- `top_p` (DOUBLE) -- nucleus sampling 門檻值
- `stop` (ARRAY<STRING>) -- 停止序列

### 使用 responseFormat 產生結構化輸出

> **注意：** 最上層 `responseFormat` STRUCT 必須只包含一個欄位。若要回傳多個欄位，請包在單一外層欄位中。

```sql
-- 強制輸出符合 schema 的 JSON（最上層 STRUCT 必須只有一個欄位）
SELECT ai_query(
  'databricks-meta-llama-3-3-70b-instruct',
  '請從以下內容擷取產品名稱、價格與類別：「Sony WH-1000XM5 headphones, $348, Electronics」',
  responseFormat => 'STRUCT<result: STRUCT<product_name: STRING, price: DOUBLE, category: STRING>>'
) AS extracted;
```

### 對資料表執行批次推論

```sql
-- 對資料表中的所有資料列進行分類
SELECT
  review_id,
  review_text,
  ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    CONCAT('請將以下評論分類為正面、負面或中性：', review_text),
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
  '請描述這張圖片的內容。',
  files => READ_FILES('/Volumes/catalog/schema/images/photo.jpg', format => 'binaryFile')
) AS description;
```

### 使用 failOnError 進行錯誤處理

```sql
-- 為批次處理提供平順的錯誤處理
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

### 產生 Embedding

```sql
-- 使用 ai_query 產生 Embedding
SELECT
  text,
  ai_query('databricks-gte-large-en', text) AS embedding
FROM catalog.schema.documents;
```

---

## 任務專用 AI 函式

這些函式提供簡化且單一用途的介面，不需要指定 endpoint 或 model。

### ai_gen

根據 prompt 產生文字。

```sql
ai_gen(prompt)
```

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `prompt` | STRING | 使用者的請求／prompt |

**回傳：** STRING

```sql
-- 簡單生成
SELECT ai_gen('請為夏季腳踏車特賣活動產生一個精簡、愉快的電子郵件標題，內容包含 20% 折扣');
-- 回傳：「夏季腳踏車特賣：以 8 折入手你的夢幻單車！」

-- 使用資料表資料生成
SELECT
  question,
  ai_gen('你是一位老師。請用 50 個字回答學生的問題：' || question) AS answer
FROM catalog.schema.questions
LIMIT 10;
```

---

### ai_classify

將文字分類為提供標籤中的其中一項。

```sql
ai_classify(content, labels)
```

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 要分類的文字 |
| `labels` | ARRAY<STRING> | 分類選項（最少 2 個、最多 20 個元素） |

**回傳：** STRING matching one of the labels, or NULL if classification fails.

```sql
-- 簡單分類
SELECT ai_classify('我的密碼外洩了。', ARRAY('緊急', '不緊急'));
-- 回傳：「緊急」

-- 批次產品分類
SELECT
  product_name,
  description,
  ai_classify(description, ARRAY('服飾', '鞋類', '配件', '家具')) AS category
FROM catalog.schema.products
LIMIT 100;

-- 支援工單路由
SELECT
  ticket_id,
  ai_classify(
    description,
    ARRAY('帳務', '技術', '帳號', '功能需求', '其他')
  ) AS department
FROM catalog.schema.support_tickets;
```

---

### ai_extract

從文字中擷取命名實體。

```sql
ai_extract(content, labels)
```

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 要從中擷取實體的文字 |
| `labels` | ARRAY<STRING> | 要擷取的實體類型 |

**回傳：** STRUCT，其中每個欄位對應一個標籤，並以 STRING 儲存擷取出的實體。若 content 為 NULL，則回傳 NULL。

```sql
-- 擷取人名、地點與組織
SELECT ai_extract(
  'John Doe 住在 New York，並在 Acme Corp. 工作。',
  ARRAY('person', 'location', 'organization')
);
-- 回傳：{"person": "John Doe", "location": "New York", "organization": "Acme Corp."}

-- 擷取聯絡資訊
SELECT ai_extract(
  '請寄送電子郵件到 jane.doe@example.com，說明上午 10 點的會議。',
  ARRAY('email', 'time')
);
-- 回傳：{"email": "jane.doe@example.com", "time": "上午 10 點"}

-- 從客戶回饋中批次擷取實體
SELECT
  feedback_id,
  ai_extract(feedback_text, ARRAY('product', 'issue', 'person')) AS entities
FROM catalog.schema.customer_feedback;
```

---

### ai_analyze_sentiment

對文字進行情緒分析。

```sql
ai_analyze_sentiment(content)
```

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 要分析的文字 |

**回傳：** STRING -- one of `'positive'`, `'negative'`, `'neutral'`, or `'mixed'`. Returns NULL if sentiment cannot be determined.

```sql
SELECT ai_analyze_sentiment('我很開心。');     -- 回傳："positive"
SELECT ai_analyze_sentiment('我很難過。');       -- 回傳："negative"
SELECT ai_analyze_sentiment('事情就是這樣。'); -- 回傳："neutral"

-- 依產品彙總情緒
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

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `expr1` | STRING | 第一段要比較的文字 |
| `expr2` | STRING | 第二段要比較的文字 |

**回傳：** FLOAT -- 語意相似度分數，其中 1.0 代表完全相同。此分數為相對值，僅適合用於排序。

```sql
-- 完全相符
SELECT ai_similarity('Apache Spark', 'Apache Spark');
-- 回傳：1.0

-- 尋找相似公司名稱（模糊比對）
SELECT company_name, ai_similarity(company_name, 'Databricks') AS score
FROM catalog.schema.customers
ORDER BY score DESC
LIMIT 10;

-- 重複資料偵測
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

產生文字摘要。

```sql
ai_summarize(content [, max_words])
```

| 參數 | 類型 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `content` | STRING | 是 | 要摘要的文字 |
| `max_words` | INTEGER | 否 | 摘要的目標字數。預設為 50；設為 0 則不限制 |

**回傳：** STRING. Returns NULL if content is NULL.

```sql
-- 以預設 50 字限制產生摘要
SELECT ai_summarize(
  'Apache Spark 是一個用於大規模資料處理的統一分析引擎。'
  || '它提供 Java、Scala、Python 與 R 的高階 API，並具備經過最佳化的'
  || '執行引擎，可支援一般化的執行圖。'
);

-- 以自訂字數限制產生摘要
SELECT ai_summarize(article_body, 100) AS summary
FROM catalog.schema.articles;

-- 為報告產生高階主管摘要
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

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 要翻譯的文字 |
| `to_lang` | STRING | 目標語言代碼 |

**支援語言：** English (`en`)、German (`de`)、French (`fr`)、Italian (`it`)、Portuguese (`pt`)、Hindi (`hi`)、Spanish (`es`)、Thai (`th`)。

**回傳：** STRING. Returns NULL if content is NULL.

```sql
-- 英文翻譯為西班牙文
SELECT ai_translate('你好，你最近好嗎？', 'es');
-- 回傳：「Hola, como estas?」

-- 西班牙文翻譯為英文
SELECT ai_translate('La vida es un hermoso viaje.', 'en');
-- 回傳：「Life is a beautiful journey.」

-- 為在地化翻譯產品描述
SELECT
  product_id,
  description AS original,
  ai_translate(description, 'fr') AS french,
  ai_translate(description, 'de') AS german
FROM catalog.schema.products;
```

---

### ai_fix_grammar

修正文法錯誤。

```sql
ai_fix_grammar(content)
```

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 要修正的文字 |

**回傳：** STRING with corrected grammar. Returns NULL if content is NULL.

```sql
SELECT ai_fix_grammar('This sentence have some mistake');
-- 回傳：「This sentence has some mistakes」

SELECT ai_fix_grammar('She dont know what to did.');
-- 回傳：「She doesn't know what to do.」

-- 清理使用者產生內容
SELECT
  comment_id,
  original_text,
  ai_fix_grammar(original_text) AS corrected_text
FROM catalog.schema.user_comments;
```

---

### ai_mask

遮罩文字中指定的實體類型（PII 去識別化）。

```sql
ai_mask(content, labels)
```

| 參數 | 類型 | 說明 |
|-----------|------|-------------|
| `content` | STRING | 含有待遮罩實體的文字 |
| `labels` | ARRAY<STRING> | 要遮罩的實體類型（例如 `'person'`、`'email'`、`'phone'`、`'address'`、`'location'`、`'ssn'`、`'credit_card'`） |

**回傳：** STRING with specified entities replaced by `[MASKED]`. Returns NULL if content is NULL.

```sql
-- 遮罩個人資訊
SELECT ai_mask(
  'John Doe 住在 New York。他的電子郵件是 john.doe@example.com。',
  ARRAY('person', 'email')
);
-- 回傳：「[MASKED] 住在 New York。他的電子郵件是 [MASKED]。」

-- 遮罩聯絡資訊
SELECT ai_mask(
  '請撥打 555-1234 聯絡我，或前往 123 Main St.。',
  ARRAY('phone', 'address')
);
-- 回傳：「請透過 [MASKED] 聯絡我，或前往 [MASKED]」

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

| 參數 | 類型 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `content` | BINARY | 是 | 以二進位 blob 資料表示的文件 |
| `options` | MAP<STRING, STRING> | 否 | 設定選項 |

**Options Map 鍵值：**

| 鍵值 | 值 | 說明 |
|-----|--------|-------------|
| `version` | `'2.0'` | 輸出 schema 版本 |
| `imageOutputPath` | Volume path | 儲存轉譯後頁面影像的 Unity Catalog volume 路徑 |
| `descriptionElementTypes` | `''`、`'figure'`、`'*'` | 控制 AI 產生描述的方式。預設為 `'*'`（所有元素） |

**回傳：** 具有以下結構的 VARIANT：
- `document.pages[]` -- 頁面中繼資料（id、image_uri）
- `document.elements[]` -- 擷取內容（type、content、bbox、description）
- `error_status[]` -- 每頁的錯誤詳細資料
- `metadata` -- 檔案與 schema 版本資訊

**支援格式：** PDF、JPG/JPEG、PNG、DOC/DOCX、PPT/PPTX

**需求：** Databricks Runtime 17.1+，且位於 US/EU 區域或已啟用跨地域路由。

```sql
-- 基本文件解析
SELECT ai_parse_document(content)
FROM READ_FILES('/Volumes/catalog/schema/volume/docs/', format => 'binaryFile');

-- 使用選項解析（儲存影像、版本 2.0）
SELECT ai_parse_document(
  content,
  map(
    'version', '2.0',
    'imageOutputPath', '/Volumes/catalog/schema/volume/images/',
    'descriptionElementTypes', '*'
  )
)
FROM READ_FILES('/Volumes/catalog/schema/volume/invoices/', format => 'binaryFile');

-- 先解析文件，再以 ai_query 擷取結構化資料
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
    CONCAT('請從以下內容擷取供應商名稱、發票號碼與總額：', doc:document:elements[0]:content::STRING),
    responseFormat => 'STRUCT<vendor: STRING, invoice_number: STRING, total: DOUBLE>'
  ) AS invoice_data
FROM parsed;
```

---

## 時間序列 AI 函式

### ai_forecast

使用內建、類似 prophet 的模型預測時間序列資料。這是一個資料表值函式（TVF）。

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

| 參數 | 類型 | 預設值 | 說明 |
|-----------|------|---------|-------------|
| `observed` | TABLE | 必填 | 以 `TABLE(subquery)` 或 `TABLE(table_name)` 傳入的訓練資料 |
| `horizon` | DATE/TIMESTAMP/STRING | 必填 | 不包含在內的預測結束時間 |
| `time_col` | STRING | 必填 | observed 資料中 DATE 或 TIMESTAMP 欄位的名稱 |
| `value_col` | STRING 或 ARRAY<STRING> | 必填 | 要預測的一個或多個數值欄位 |
| `group_col` | STRING、ARRAY<STRING> 或 NULL | NULL | 用於各群組獨立預測的分割欄位 |
| `prediction_interval_width` | DOUBLE | 0.95 | 預測區間界限的信賴水準（0 到 1） |
| `frequency` | STRING | `'auto'` | 時間粒度。會根據近期資料自動推斷。DATE 欄位可使用 `'day'`、`'week'`、`'month'`；TIMESTAMP 欄位可使用 `'D'`、`'W'`、`'M'`、`'H'` 等。 |
| `seed` | INTEGER 或 NULL | NULL | 供重現結果使用的隨機種子 |
| `parameters` | STRING | `'{}'` | JSON 編碼的進階設定 |

**進階參數（JSON）：**
- `global_cap` -- logistic growth 的上界
- `global_floor` -- logistic growth 的下界
- `daily_order` -- 每日季節性的 Fourier 階數
- `weekly_order` -- 每週季節性的 Fourier 階數

### 回傳欄位

對於每個名為 `v` 的 `value_col`，輸出內容包含：
- `{v}_forecast` (DOUBLE) -- 點預測值
- `{v}_upper` (DOUBLE) -- 預測上界
- `{v}_lower` (DOUBLE) -- 預測下界
- 以及原始時間欄位與群組欄位

**需求：** Serverless SQL Warehouse。

```sql
-- 基本營收預測
SELECT * FROM ai_forecast(
  TABLE(SELECT ds, revenue FROM catalog.schema.daily_sales),
  horizon    => '2025-12-31',
  time_col   => 'ds',
  value_col  => 'revenue'
);

-- 依群組進行多指標預測
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

-- 具成長限制的每月預測（DATE 欄位請使用 'month'，不要用 'M'）
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

## Vector Search 函式

### vector_search

使用 SQL 查詢 Mosaic AI Vector Search 索引。這是一個資料表值函式。

```sql
-- Databricks Runtime 15.3+
SELECT * FROM vector_search(
  index       => index_name,
  query_text  => search_text,         -- OR query_vector => embedding_array
  num_results => max_results,
  query_type  => 'ANN' | 'HYBRID'
)
```

### 參數 (Named Arguments Required)

| 參數 | 類型 | 預設值 | 說明 |
|-----------|------|---------|-------------|
| `index` | STRING 常值 | 必填 | vector search 索引的完整名稱 |
| `query_text` | STRING | -- | 搜尋字串（適用於具有 embedding 來源的 Delta Sync 索引） |
| `query_vector` | ARRAY<FLOAT\|DOUBLE\|DECIMAL> | -- | 用於搜尋的預先計算 embedding 向量 |
| `num_results` | INTEGER | 10 | 最多回傳的筆數（上限 100） |
| `query_type` | STRING | `'ANN'` | `'ANN'` 代表 approximate nearest neighbor，`'HYBRID'` 代表混合搜尋 |

**回傳：** 包含索引所有欄位與最佳匹配紀錄的資料表。

**需求：** Serverless SQL Warehouse，且需具有索引的 Select 權限。

```sql
-- 以文字為基礎的相似度搜尋
SELECT * FROM vector_search(
  index      => 'catalog.schema.product_index',
  query_text => '無線降噪耳機',
  num_results => 5
);

-- 混合搜尋（結合關鍵字與語意）
SELECT * FROM vector_search(
  index       => 'catalog.schema.support_docs_index',
  query_text  => '路由器型號 LMP-9R2 的 Wi‑Fi 連線問題',
  query_type  => 'HYBRID',
  num_results => 3
);

-- 使用預先計算 embedding 的向量搜尋
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

透過 Unity Catalog HTTP connections，從 SQL 對外部服務發送 HTTP requests。

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

| 參數 | 類型 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `CONN` | STRING 常值 | 是 | 既有 HTTP connection 的名稱 |
| `METHOD` | STRING 常值 | 是 | HTTP 方法：`'GET'`、`'POST'`、`'PUT'`、`'DELETE'`、`'PATCH'` |
| `PATH` | STRING 常值 | 是 | 會附加到 connection `base_path` 的路徑。不得包含目錄跳脫（`../`） |
| `HEADERS` | MAP<STRING, STRING> | 否 | Request headers。預設為 NULL |
| `PARAMS` | MAP<STRING, STRING> | 否 | Query 參數。預設為 NULL |
| `JSON` | STRING expression | 否 | 以 JSON 字串表示的 request body |

### 回傳型別

`STRUCT<status_code: INT, text: STRING>`
- `status_code` -- HTTP 回應狀態（例如 200、403、404）
- `text` -- 回應本文（通常為 JSON）

**需求：** Databricks Runtime 16.2+、已啟用 Unity Catalog 的 workspace，以及 USE CONNECTION 權限。

### 建立 HTTP Connections

```sql
-- Bearer Token 驗證
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

**Connection 選項：**

| 選項 | 類型 | 說明 |
|--------|------|-------------|
| `host` | STRING | 外部服務的基礎 URL |
| `port` | STRING | 網路連接埠（HTTPS 通常為 `'443'`） |
| `base_path` | STRING | API endpoints 的根路徑 |
| `bearer_token` | STRING | Auth Token（為了安全請使用 `secret()`） |
| `client_id` | STRING | OAuth 應用程式識別碼 |
| `client_secret` | STRING | OAuth 應用程式密鑰 |
| `oauth_scope` | STRING | 以空格分隔的 OAuth scopes |
| `token_endpoint` | STRING | OAuth Token endpoint URL |
| `authorization_endpoint` | STRING | OAuth 授權重新導向 URL |
| `oauth_credential_exchange_method` | STRING | `'header_and_body'`、`'body_only'` 或 `'header_only'` |

### 範例

```sql
-- POST 一則 Slack 訊息
SELECT http_request(
  CONN   => 'slack_conn',
  METHOD => 'POST',
  PATH   => '/chat.postMessage',
  JSON   => to_json(named_struct('channel', '#alerts', 'text', '管線已成功完成'))
);

-- 含 headers 與 params 的 GET request
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
    'message', CONCAT('空值比率超過門檻：', CAST(null_pct AS STRING))
  ))
)
FROM catalog.schema.data_quality_metrics
WHERE null_pct > 0.05;
```

---

## remote_query 函式（Lakehouse Federation）

使用外部資料庫原生 SQL 語法執行查詢，並將結果以 Databricks SQL 中的資料表形式回傳。這是一個資料表值函式。

### 概覽

Lakehouse Federation 可讓你在不遷移資料的情況下查詢外部資料庫。支援兩種模式：
- **Query Federation** -- 查詢會透過 JDBC 下推到外部資料庫
- **Catalog Federation** -- 查詢可直接存取 object storage 中的 foreign tables

### 語法

```sql
SELECT * FROM remote_query(
  '<connection-name>',
  <option-key> => '<option-value>'
  [, ...]
)
```

### 支援的資料庫

| 資料庫 | Connection 類型 |
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

### 參數 by Database Type

**PostgreSQL / MySQL / SQL Server / Redshift / Teradata：**

| 參數 | 類型 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `database` | STRING | 是 | 遠端資料庫名稱 |
| `query` | STRING | query/dbtable 擇一 | 使用遠端資料庫原生語法撰寫的 SQL 查詢 |
| `dbtable` | STRING | query/dbtable 擇一 | 完整限定資料表名稱 |
| `fetchsize` | STRING | 否 | 每次往返抓取的資料列數量 |
| `partitionColumn` | STRING | 否 | 用於平行讀取分割的欄位 |
| `lowerBound` | STRING | 否 | 分割欄位的下界 |
| `upperBound` | STRING | 否 | 分割欄位的上界 |
| `numPartitions` | STRING | 否 | 平行分割數量 |

**Oracle（以 `service_name` 取代 `database`）：**

| 參數 | 類型 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `service_name` | STRING | 是 | Oracle service 名稱 |
| `query` 或 `dbtable` | STRING | 是（擇一必填） | 查詢或資料表參照 |

**Snowflake：**

| 參數 | 類型 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `database` | STRING | 是 | Snowflake 資料庫 |
| `schema` | STRING | 否 | Schema 名稱（預設為 `public`） |
| `query` 或 `dbtable` | STRING | 是（擇一必填） | 查詢或資料表參照 |
| `query_timeout` | STRING | 否 | 查詢逾時秒數 |
| `partition_size_in_mb` | STRING | 否 | 讀取時的分割大小 |

**BigQuery：**

| 參數 | 類型 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `query` 或 `dbtable` | STRING | 是（擇一必填） | 查詢或資料表參照 |
| `materializationDataset` | STRING | 適用於 views／複雜查詢 | 用於 materialization 的 dataset |
| `materializationProject` | STRING | 否 | 用於 materialization 的 GCP project |
| `parentProject` | STRING | 否 | 上層 GCP project |

### Pushdown 控制

| 選項 | 預設值 | 說明 |
|--------|---------|-------------|
| `pushdown.limit.enabled` | `true` | 將 LIMIT 下推到遠端 |
| `pushdown.offset.enabled` | `true` | 將 OFFSET 下推到遠端 |
| `pushdown.filters.enabled` | `true` | 將 WHERE 篩選條件下推到遠端 |
| `pushdown.aggregates.enabled` | `true` | 將彙總計算下推到遠端 |
| `pushdown.sortLimit.enabled` | `true` | 將 ORDER BY + LIMIT 下推到遠端 |

### 需求

- 已啟用 Unity Catalog 的 workspace
- Databricks Runtime 17.3+（clusters）或 SQL Warehouse 2025.35+（Pro/Serverless）
- 與目標資料庫的網路連通性
- 需具備 `USE CONNECTION` 權限，或包裝 view 上的 `SELECT` 權限

### 限制

- **唯讀**：僅支援 SELECT 查詢（不支援 INSERT、UPDATE、DELETE、MERGE、DDL 或 stored procedures）

### 建立 Connections

```sql
-- PostgreSQL connection
CREATE CONNECTION my_postgres TYPE POSTGRESQL
OPTIONS (
  host     'pg-server.example.com',
  port     '5432',
  user     secret('my-scope', 'pg-user'),
  password secret('my-scope', 'pg-password')
);

-- SQL Server connection
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

-- 將 federated 資料與本機 Delta tables 進行 join
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

-- 透過 view 進行存取委派
CREATE VIEW catalog.schema.federated_customers AS
SELECT * FROM remote_query(
  'my_postgres',
  database => 'crm_db',
  query    => 'SELECT customer_id, name, region FROM customers'
);

-- 使用者只需要 view 的 SELECT 權限，不需要 USE CONNECTION
GRANT SELECT ON VIEW catalog.schema.federated_customers TO `analysts`;
```

---

## read_files 資料表值函式

直接在 SQL 中從 cloud storage 或 Unity Catalog volumes 讀取檔案，並自動偵測格式與推斷 schema。

### 語法

```sql
SELECT * FROM read_files(
  path
  [, option_key => option_value ] [...]
)
```

### 核心參數

| 參數 | 類型 | 必填 | 說明 |
|-----------|------|----------|-------------|
| `path` | STRING | 是 | 資料位置的 URI。支援 `s3://`、`abfss://`、`gs://`、`/Volumes/...` 路徑，也接受 glob pattern |

### 常用選項

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `format` | STRING | 自動偵測 | 檔案格式：`'csv'`、`'json'`、`'parquet'`、`'avro'`、`'orc'`、`'text'`、`'binaryFile'`、`'xml'` |
| `schema` | STRING | 推斷 | 以 DDL 格式明確定義的 schema |
| `schemaHints` | STRING | 無 | 覆寫部分推斷出的 schema 欄位 |
| `rescuedDataColumn` | STRING | `'_rescued_data'` | 無法解析資料的欄位名稱。設為空字串即可停用 |
| `pathGlobFilter` / `fileNamePattern` | STRING | 無 | 用於篩選檔案的 glob pattern（例如 `'*.csv'`） |
| `recursiveFileLookup` | BOOLEAN | `false` | 搜尋巢狀目錄 |
| `modifiedAfter` | TIMESTAMP STRING | 無 | 僅讀取在此時間戳記之後修改的檔案 |
| `modifiedBefore` | TIMESTAMP STRING | 無 | 僅讀取在此時間戳記之前修改的檔案 |
| `partitionColumns` | STRING | 自動偵測 | 以逗號分隔的 Hive 風格分割欄位。空字串代表忽略所有分割 |
| `useStrictGlobber` | BOOLEAN | `true` | 嚴格的 glob pattern 比對 |
| `inferColumnTypes` | BOOLEAN | `true` | 推斷精確欄位型別（而非全部視為 STRING） |
| `schemaEvolutionMode` | STRING | -- | Schema 演進行為：`'none'` 代表移除 rescued data 欄位 |

### CSV 專用選項

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `sep` / `delimiter` | STRING | `','` | 欄位分隔符號 |
| `header` | BOOLEAN | `false` | 第一列包含欄位名稱 |
| `encoding` | STRING | `'UTF-8'` | 字元編碼 |
| `quote` | STRING | `'"'` | 引號字元 |
| `escape` | STRING | `'\'` | 跳脫字元 |
| `nullValue` | STRING | `''` | null 的字串表示法 |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | 日期解析格式 |
| `timestampFormat` | STRING | `'yyyy-MM-dd\'T\'HH:mm:ss...'` | Timestamp 解析格式 |
| `mode` | STRING | `'PERMISSIVE'` | 解析模式：`'PERMISSIVE'`、`'DROPMALFORMED'`、`'FAILFAST'` |
| `multiLine` | BOOLEAN | `false` | 允許紀錄跨越多行 |
| `ignoreLeadingWhiteSpace` | BOOLEAN | `false` | 去除前導空白 |
| `ignoreTrailingWhiteSpace` | BOOLEAN | `false` | 去除尾端空白 |
| `comment` | STRING | 無 | 行註解字元 |
| `maxCharsPerColumn` | INTEGER | 無 | 每欄最大字元數 |
| `maxColumns` | INTEGER | 無 | 最大欄位數 |
| `mergeSchema` | BOOLEAN | `false` | 合併多個檔案的 schema |
| `enforceSchema` | BOOLEAN | `true` | 強制套用指定 schema |
| `locale` | STRING | `'US'` | 用於數字／日期解析的 locale |
| `charToEscapeQuoteEscaping` | STRING | 無 | 用於跳脫引號跳脫字元的字元 |
| `readerCaseSensitive` | BOOLEAN | `true` | 區分大小寫的欄位名稱比對 |

### JSON 專用選項

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `multiLine` | BOOLEAN | `false` | 解析多行 JSON 紀錄 |
| `allowComments` | BOOLEAN | `false` | 允許 Java/C++ 風格註解 |
| `allowSingleQuotes` | BOOLEAN | `true` | 允許字串使用單引號 |
| `allowUnquotedFieldNames` | BOOLEAN | `false` | 允許不加引號的欄位名稱 |
| `allowBackslashEscapingAnyCharacter` | BOOLEAN | `false` | 允許使用反斜線跳脫任意字元 |
| `allowNonNumericNumbers` | BOOLEAN | `true` | 允許 NaN、Infinity、-Infinity |
| `encoding` | STRING | `'UTF-8'` | 字元編碼 |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | 日期解析格式 |
| `timestampFormat` | STRING | -- | Timestamp parsing format |
| `inferTimestamp` | BOOLEAN | `false` | 推斷 timestamp 型別 |
| `prefersDecimal` | BOOLEAN | `false` | 優先使用 DECIMAL 而非 DOUBLE |
| `primitivesAsString` | BOOLEAN | `false` | 將所有 primitive 值推斷為 STRING |
| `singleVariantColumn` | STRING | 無 | 將整份 JSON 讀成單一 VARIANT 欄位 |
| `locale` | STRING | `'US'` | 用於解析的 locale |
| `mode` | STRING | `'PERMISSIVE'` | 解析模式 |
| `readerCaseSensitive` | BOOLEAN | `true` | 區分大小寫的欄位比對 |
| `timeZone` | STRING | Session timezone | 用於 timestamp 解析的時區 |

### XML 專用選項

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `rowTag` | STRING | **必填** | 用來界定資料列的 XML tag |
| `attributePrefix` | STRING | `'_'` | XML 屬性的前綴 |
| `valueTag` | STRING | `'_VALUE'` | 元素文字內容的 tag |
| `encoding` | STRING | `'UTF-8'` | 字元編碼 |
| `ignoreSurroundingSpaces` | BOOLEAN | `true` | 忽略值周圍的空白 |
| `ignoreNamespace` | BOOLEAN | `false` | 忽略 XML namespaces |
| `mode` | STRING | `'PERMISSIVE'` | 解析模式 |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | 日期解析格式 |
| `timestampFormat` | STRING | -- | Timestamp parsing format |
| `locale` | STRING | `'US'` | 用於解析的 locale |
| `readerCaseSensitive` | BOOLEAN | `true` | Case-sensitive matching |
| `samplingRatio` | DOUBLE | `1.0` | 用於 schema 推斷的抽樣資料列比例 |

### Parquet / Avro / ORC 選項

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mergeSchema` | BOOLEAN | `false` | 合併多個檔案的 schema |
| `readerCaseSensitive` | BOOLEAN | `true` | 區分大小寫的欄位比對 |
| `rescuedDataColumn` | STRING | -- | rescued data 欄位 |
| `datetimeRebaseMode` | STRING | -- | datetime 值的 rebase 模式 |
| `int96RebaseMode` | STRING | -- | INT96 timestamps 的 rebase 模式（僅 Parquet） |

### Streaming 選項

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `includeExistingFiles` | BOOLEAN | `true` | 第一次執行時處理既有檔案 |
| `maxFilesPerTrigger` | INTEGER | 無 | 每個 micro-batch 的最大檔案數 |
| `maxBytesPerTrigger` | STRING | 無 | 每個 micro-batch 的最大位元組數 |
| `allowOverwrites` | BOOLEAN | `false` | 允許處理被覆寫的檔案 |
| `schemaEvolutionMode` | STRING | -- | Schema 演進行為 |
| `schemaLocation` | STRING | -- | 儲存推斷 schema 的位置 |

### 需求

- Databricks Runtime 13.3 LTS 以上版本
- Databricks SQL

### 範例

```sql
-- 從 cloud storage 自動偵測格式與 schema
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

-- 讀取支援多行的 JSON
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/api_responses/',
  format    => 'json',
  multiLine => true
);

-- 讀取跨檔案合併 schema 的 Parquet
SELECT * FROM read_files(
  's3://my-bucket/parquet-data/',
  format      => 'parquet',
  mergeSchema => true
);

-- 讀取含 row tag 的 XML
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/feed.xml',
  format => 'xml',
  rowTag => 'record'
);

-- 讀取供 ai_parse_document 使用的二進位檔案（影像、PDF）
SELECT path, content FROM read_files(
  '/Volumes/catalog/schema/volume/documents/',
  format => 'binaryFile'
);

-- 依 glob pattern 與修改日期篩選檔案
SELECT * FROM read_files(
  's3://my-bucket/logs/',
  format          => 'json',
  pathGlobFilter  => '*.json',
  modifiedAfter   => '2025-01-01T00:00:00Z',
  modifiedBefore  => '2025-02-01T00:00:00Z'
);

-- 進行遞迴目錄掃描並探索 partitions
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/partitioned_data/',
  recursiveFileLookup => true,
  partitionColumns    => 'year,month'
);

-- 包含檔案中繼資料
SELECT *, _metadata.file_path, _metadata.file_name, _metadata.file_size
FROM read_files('/Volumes/catalog/schema/volume/data/');

-- 從檔案建立資料表
CREATE TABLE catalog.schema.imported_data AS
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/export.csv',
  format => 'csv',
  header => true
);

-- 從 cloud storage 建立 streaming table
CREATE STREAMING TABLE catalog.schema.streaming_events AS
SELECT * FROM STREAM read_files(
  's3://my-bucket/events/',
  format              => 'json',
  includeExistingFiles => false,
  maxFilesPerTrigger   => 100
);

-- 為半結構化 JSON 讀取單一 VARIANT 欄位
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/complex.json',
  format              => 'json',
  singleVariantColumn => 'raw_data'
);
```

---

## 組合函式 -- 生產環境模式

### AI 強化 ETL 管線

```sql
-- 使用多個 AI functions 處理客戶回饋
CREATE OR REPLACE TABLE catalog.schema.enriched_feedback AS
SELECT
  feedback_id,
  feedback_text,
  ai_analyze_sentiment(feedback_text) AS sentiment,
  ai_classify(feedback_text, ARRAY('產品', '服務', '帳務', '其他')) AS category,
  ai_extract(feedback_text, ARRAY('product', 'issue')) AS entities,
  ai_summarize(feedback_text, 20) AS summary,
  ai_mask(feedback_text, ARRAY('person', 'email', 'phone')) AS anonymized_text
FROM catalog.schema.raw_feedback;
```

### 文件處理管線

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
    CONCAT('請從以下內容擷取合約當事方、生效日期與終止條款：',
           doc:document:elements[0]:content::STRING),
    responseFormat => 'STRUCT<party_a: STRING, party_b: STRING, effective_date: STRING, termination_clause: STRING>'
  ) AS contract_info
FROM parsed;
```

### 透過 http_request 整合外部 API

```sql
-- 透過呼叫外部 API 並 join 結果來豐富資料
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

### Federated Analytics

```sql
-- 結合遠端資料庫資料、本機 lakehouse 資料與 AI
SELECT
  remote_orders.customer_id,
  remote_orders.total_spend,
  local_profiles.segment,
  ai_classify(
    CONCAT('客戶消費金額為 $', CAST(remote_orders.total_spend AS STRING),
           '，所在區隔為 ', local_profiles.segment),
    ARRAY('高價值', '中價值', '低價值', '有流失風險')
  ) AS value_tier
FROM remote_query(
  'my_postgres',
  database => 'sales_db',
  query    => 'SELECT customer_id, SUM(amount) as total_spend FROM orders GROUP BY customer_id'
) remote_orders
JOIN catalog.schema.customer_profiles local_profiles
  ON remote_orders.customer_id = local_profiles.customer_id;
```
