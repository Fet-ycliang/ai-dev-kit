# 任務專用 AI Functions — 完整參考

這些函式不需要選擇 model endpoint。它們會呼叫針對各任務最佳化的預先設定 Foundation Model API。全部都需要 DBR 15.1+（批次處理建議 15.4 ML LTS）；`ai_parse_document` 需要 DBR 17.1+。

---

## `ai_analyze_sentiment`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_analyze_sentiment

會回傳以下其中之一：`positive`、`negative`、`neutral`、`mixed` 或 `NULL`。

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

回傳符合的標籤，或 `NULL`。

```sql
SELECT ticket_text,
       ai_classify(ticket_text, ARRAY('緊急', '不緊急', '垃圾訊息')) AS priority
FROM support_tickets;
```

```python
from pyspark.sql.functions import expr
df = spark.table("support_tickets")
df.withColumn(
    "priority",
    expr("ai_classify(ticket_text, array('緊急', '不緊急', '垃圾訊息'))")
).display()
```

**提示：**
- 標籤越少，結果通常越一致（2–5 個最佳）
- 標籤應互斥且容易清楚區分
- 不適合多標籤分類；如有需要請分次呼叫

---

## `ai_extract`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_extract

**語法：** `ai_extract(content, labels)`
- `content`: STRING — 來源文字
- `labels`: ARRAY\<STRING\> — 要擷取的實體類型

回傳一個 STRUCT，其中每個欄位名稱都對應到標籤。若找不到，欄位值會是 `NULL`。

```sql
-- 擷取後直接存取欄位
SELECT
    entities.person,
    entities.location,
    entities.date
FROM (
    SELECT ai_extract(
        'John Doe 於 2024-01-15 從 New York 來電。',
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

**改用 `ai_query` 的情況：** 輸出包含巢狀陣列，或階層深度超過約 5 層。

---

## `ai_fix_grammar`

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_fix_grammar

**語法：** `ai_fix_grammar(content)` — 回傳修正後的 STRING。

針對英文最佳化。適合在下游處理前，先清理使用者產生的內容。

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

適合用於自由格式文字生成，不需要結構化輸出格式時使用。若要產生結構化 JSON，請改用搭配 `responseFormat` 的 `ai_query`。

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

回傳把已識別實體替換成 `[MASKED]` 的文字。

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

**語法：** `ai_similarity(expr1, expr2)` — 回傳介於 0.0 到 1.0 的 FLOAT。

可用於模糊去重、搜尋結果排序，或跨資料集項目比對。

```sql
-- 公司名稱去重（相似度 > 0.85 = 很可能是重複）
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
- `max_words`: INTEGER（選用）— 字數上限；預設 50；使用 `0` 代表不設上限

```sql
-- 預設（50 字）
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

**支援語言：** `en`、`de`、`fr`、`it`、`pt`、`hi`、`es`、`th`

若是不支援的語言，請改用搭配多語模型 endpoint 的 `ai_query`。

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
- `content`: BINARY — 由 `read_files()` 或 `spark.read.format("binaryFile")` 載入的文件內容
- `options`: MAP\<STRING, STRING\>（選用）— 解析設定

**支援格式：** PDF、JPG/JPEG、PNG、DOCX、PPTX

回傳包含頁面、元素（文字段落、表格、圖形、頁首、頁尾）、邊界框與錯誤中繼資料的 VARIANT。

**選項：**

| 鍵 | 值 | 說明 |
|-----|--------|-------------|
| `version` | `'2.0'` | 輸出結構描述版本 |
| `imageOutputPath` | Volume path | 儲存轉譯後的頁面影像 |
| `descriptionElementTypes` | `''`, `'figure'`, `'*'` | AI 產生的描述（預設：`'*'` 表示全部） |

**輸出結構描述：**

```
document
├── pages[]          -- 頁面 id、image_uri
└── elements[]       -- 擷取出的內容
    ├── type         -- "text"、"table"、"figure" 等
    ├── content      -- 擷取出的文字
    ├── bbox         -- 邊界框座標
    └── description  -- AI 產生的描述
metadata             -- 檔案資訊、結構描述版本
error_status[]       -- 各頁錯誤（若有）
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

-- 使用 options 解析（輸出影像 + 描述）
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

# 將任務專用函式串接到擷取出的文字上
df = (
    df.withColumn("summary",  expr("ai_summarize(text_blocks, 50)"))
      .withColumn("entities", expr("ai_extract(text_blocks, array('date', 'amount', 'vendor'))"))
      .withColumn("category", expr("ai_classify(text_blocks, array('invoice', 'contract', 'report'))"))
)
df.display()
```

**限制：**
- 對內容密集或低解析度文件而言，處理速度較慢
- 對非拉丁字母與數位簽章 PDF 的效果較不理想
- 不支援自訂模型；一律使用內建解析模型
