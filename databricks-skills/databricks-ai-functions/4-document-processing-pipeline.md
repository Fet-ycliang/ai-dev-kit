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