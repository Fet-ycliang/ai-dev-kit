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