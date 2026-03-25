# Genie 對話

使用 Genie Conversation API，向已整理設定好的 Genie Space 提出自然語言問題。

## 概觀

`ask_genie` 工具可讓你以程式方式把問題送到 Genie Space，並接收由 SQL 產生的答案。你不必直接撰寫 SQL，而是把查詢生成工作交給 Genie；該 Space 已透過商業邏輯、`instructions` 與認證查詢完成整理。

## 何時使用 `ask_genie`

### 在下列情況使用 `ask_genie`

| 情境 | 原因 |
|------|------|
| Genie Space 已整理好商業邏輯 | Genie 知道像是「活躍客戶 = 90 天內有下單」這類規則 |
| 使用者明確表示「問 Genie」或「使用我的 Genie Space」 | 使用者明確想使用已整理好的 Space |
| 複雜的商業指標且定義明確 | Genie 具備官方指標的認證查詢 |
| 建立完 Genie Space 後要進行測試 | 驗證 Space 是否正常運作 |
| 使用者想以對話方式探索資料 | Genie 會為追問保留上下文 |

### 在下列情況改用直接 SQL（`execute_sql`）

| 情境 | 原因 |
|------|------|
| 簡單的臨時查詢 | 直接 SQL 更快，不需要額外整理設定 |
| 你已經有完全正確的 SQL | 不需要讓 Genie 重新產生 |
| 這份資料尚未建立 Genie Space | 沒有 Space 就無法使用 Genie |
| 需要精準控制查詢內容 | 直接 SQL 可提供完整控制 |

## MCP 工具

| 工具 | 用途 |
|------|------|
| `ask_genie` | 提出問題或追問（`conversation_id` 為選填） |

## 基本用法

### 提出問題

```python
ask_genie(
    space_id="01abc123...",
    question="上個月的總銷售額是多少？"
)
```

**回應：**
```python
{
    "question": "上個月的總銷售額是多少？",
    "conversation_id": "conv_xyz789",
    "message_id": "msg_123",
    "status": "COMPLETED",
    "sql": "SELECT SUM(total_amount) AS total_sales FROM orders WHERE order_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL 1 MONTH) AND order_date < DATE_TRUNC('month', CURRENT_DATE)",
    "columns": ["total_sales"],
    "data": [[125430.50]],
    "row_count": 1
}
```

### 提出追問

使用第一個回應中的 `conversation_id`，即可在保留上下文的情況下提出追問：

```python
# 第一個問題
result = ask_genie(
    space_id="01abc123...",
    question="上個月的總銷售額是多少？"
)

# 追問（沿用第一個問題的上下文）
ask_genie(
    space_id="01abc123...",
    question="請依區域拆分",
    conversation_id=result["conversation_id"]
)
```

Genie 會記住上下文，因此這裡的「那個」指的就是「上個月的總銷售額」。

## 回應欄位

| 欄位 | 說明 |
|------|------|
| `question` | 原始提問內容 |
| `conversation_id` | 追問時使用的 ID |
| `message_id` | 唯一的訊息識別碼 |
| `status` | `COMPLETED`、`FAILED`、`CANCELLED`、`TIMEOUT` |
| `sql` | Genie 產生的 SQL 查詢 |
| `columns` | 結果中的欄位名稱清單 |
| `data` | 以資料列清單表示的查詢結果 |
| `row_count` | 回傳的資料列數 |
| `text_response` | 文字說明（若 Genie 要求進一步釐清） |
| `error` | 錯誤訊息（當狀態不是 `COMPLETED` 時） |

## 處理回應

### 成功回應

```python
result = ask_genie(space_id, "我們的前 10 大客戶是誰？")

if result["status"] == "COMPLETED":
    print(f"SQL: {result['sql']}")
    print(f"資料列數: {result['row_count']}")
    for row in result["data"]:
        print(row)
```

### 失敗回應

```python
result = ask_genie(space_id, "生命的意義是什麼？")

if result["status"] == "FAILED":
    print(f"錯誤: {result['error']}")
    # Genie 無法回答，可能需要重新措辭或改用直接 SQL
```

### 逾時

```python
result = ask_genie(space_id, question, timeout_seconds=60)

if result["status"] == "TIMEOUT":
    print("查詢花費太久，請改問較簡單的問題，或提高 timeout")
```

## 範例工作流程

### 工作流程 1：使用者要求使用 Genie

```
使用者：「幫我問問我的銷售 Genie，流失率是多少？」

Claude：
1. 辨識出使用者想使用 Genie（明確要求）
2. 呼叫 ask_genie(space_id="sales_genie_id", question="流失率是多少？")
3. 回傳：「根據你的銷售 Genie，流失率是 4.2%。
   Genie 使用了這段 SQL：SELECT ...」
```

### 工作流程 2：測試新的 Genie Space

```
使用者：「我剛為 HR 資料建立了一個 Genie Space。可以幫我測試嗎？」

Claude：
1. 從使用者或最近一次 create_or_update_genie 的結果取得 space_id
2. 使用測試問題呼叫 ask_genie：
   - 「我們目前有多少員工？」
   - 「各部門的平均薪資是多少？」
3. 回報結果：「你的 HR Genie 運作正常，已正確回答……」
```

### 工作流程 3：搭配追問的資料探索

```
使用者：「用我的分析 Genie 幫我探索銷售趨勢。」

Claude：
1. ask_genie(space_id, "今年每月的總銷售額是多少？")
2. 使用者：「哪一個月份成長最多？」
3. ask_genie(space_id, "哪一個月份成長最多？", conversation_id=conv_id)
4. 使用者：「是哪些產品帶動那個成長？」
5. ask_genie(space_id, "是哪些產品帶動那個成長？", conversation_id=conv_id)
```

## 最佳實務

### 新主題請開始新的對話

不要在互不相關的問題之間重複使用同一個對話：

```python
# 良好：新主題使用新的對話
result1 = ask_genie(space_id, "上個月的銷售額是多少？")  # 新對話
result2 = ask_genie(space_id, "我們目前有多少員工？")  # 新對話

# 良好：相關問題使用追問
result1 = ask_genie(space_id, "上個月的銷售額是多少？")
result2 = ask_genie(space_id, "請依產品拆分",
                    conversation_id=result1["conversation_id"])  # 相關追問
```

### 處理釐清請求

Genie 有時不會直接回傳結果，而是要求進一步釐清：

```python
result = ask_genie(space_id, "把資料顯示給我")

if result.get("text_response"):
    # Genie 正在要求釐清
    print(f"Genie 提問：{result['text_response']}")
    # 以更明確的方式重新措辭
```

### 設定合適的 timeout

- 簡單彙總：30-60 秒
- 複雜 join：60-120 秒
- 大量資料掃描：120 秒以上

```python
# 快速問題
ask_genie(space_id, "今天有多少筆訂單？", timeout_seconds=30)

# 複雜分析
ask_genie(space_id, "計算所有客戶的 customer lifetime value",
          timeout_seconds=180)
```

## 疑難排解

### 「找不到 Genie Space」

- 確認 `space_id` 是否正確
- 檢查你是否擁有該 Space 的存取權限
- 使用 `get_genie(space_id)` 確認它確實存在

### 「查詢逾時」

- 增加 `timeout_seconds`
- 簡化問題
- 檢查 SQL warehouse 是否正在執行

### 「產生 SQL 失敗」

- 以更清楚的方式重新措辭
- 確認問題是否能由目前可用的資料表回答
- 為 Genie Space 新增更多 `instructions` 或整理設定

### 結果不如預期

- 檢查回應中的 SQL
- 透過 Databricks UI 為 Genie Space 新增 SQL `instructions`
- 新增可示範正確模式的範例問題
