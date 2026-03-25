# 操作與限制

ACK 處理、重試與重新連線模式、吞吐量限制、傳遞語義和 Zerobus 擷取的操作限制。

---

## 確認（ACK）處理

每個擷取的記錄都會傳回耐久性確認。ACK 表示**該偏移量之前的所有記錄**都已被持久寫入到目標 Delta table。

### 策略

| 策略 | 使用時機 | 權衡 |
|----------|-------------|-----------|
| **`ingest_record_offset` + `wait_for_offset`** | 低量、嚴格排序 | 最簡單；吞吐量較低 |
| **`ingest_record_nowait` + `AckCallback`** | 高量生產者 | 吞吐量更高；更複雜 |
| **`ingest_record_nowait` + 定期 `flush`** | 批次導向工作負載 | 最佳吞吐量；最終一致 |

### 同步區塊（Python）

```python
offset = stream.ingest_record_offset(record)
stream.wait_for_offset(offset)  # 阻塞直到耐久
```

### ACK 回呼（Python）

```python
from zerobus.sdk.shared import AckCallback

class MyAckHandler(AckCallback):
    def __init__(self):
        self.last_acked_offset = 0

    def on_ack(self, offset: int) -> None:
        self.last_acked_offset = offset

    def on_error(self, offset: int, message: str) -> None:
        print(f"偏移 {offset} 的錯誤：{message}")

options = StreamConfigurationOptions(
    record_type=RecordType.JSON,
    ack_callback=MyAckHandler(),
)
```

### 清空型

```python
# 傳送許多記錄而不阻塞（火力與遺忘）
for record in batch:
    stream.ingest_record_nowait(record)

# 清空確保所有緩衝記錄已傳送
stream.flush()
```

---

## 重試與重新連線

Zerobus 串流可能因伺服器維護、網路問題或區域故障而關閉。使用指數退避和串流重新初始化實施重試。

### 模式（任何語言）

```
1. 嘗試擷取
2. 在連線/關閉錯誤時：
   a. 關閉目前串流
   b. 以指數退避等待（1 秒、2 秒、4 秒、...）
   c. 重新初始化串流
   d. 重試記錄
3. 超過最大重試次數後，記錄失敗並上報
```

### Python 實作

```python
import time
import logging

logger = logging.getLogger(__name__)

def ingest_with_retry(stream_factory, record, max_retries=5):
    """使用重試和串流重新初始化擷取記錄。

    參數：
        stream_factory：傳回新串流的可呼叫對象。
        record：要擷取的記錄。
        max_retries：最大重試次數。
    """
    stream = stream_factory()

    for attempt in range(max_retries):
        try:
            offset = stream.ingest_record_offset(record)
            stream.wait_for_offset(offset)
            return stream  # 傳回（可能是新的）串流
        except Exception as e:
            err = str(e).lower()
            logger.warning("嘗試 %d/%d 失敗：%s", attempt + 1, max_retries, e)

            if "closed" in err or "connection" in err or "unavailable" in err:
                try:
                    stream.close()
                except Exception:
                    pass
                backoff = min(2 ** attempt, 30)  # 上限 30 秒
                time.sleep(backoff)
                stream = stream_factory()
            elif attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise

    return stream
```

### 重點

- **在連線錯誤時始終重新初始化串流**，而不是只重試相同串流
- **設定退避上限**為合理的最大值（例如 30 秒）
- **記錄失敗**具有足夠的內容以診斷（端點、table、錯誤訊息）
- **針對至少一次設計**：下游使用者應處理重複記錄

---

## 傳遞語義

Zerobus 提供**至少一次**傳遞保證：

- 記錄可能被傳遞多次（例如，重試後原始記錄實際上已持久化）
- **沒有恰好一次**語義
- 設計目標 table 和下游使用者以處理重複（例如透過 `MERGE` 或唯一限制的去重）

---

## 吞吐量限制

| 限制 | 值 | 備註 |
|-------|-------|-------|
| **每個串流吞吐量** | 100 MB/秒 | 基於 1 KB 訊息 |
| **每個串流的列** | 15,000 列/秒 | |
| **最大訊息大小** | 10 MB（10,485,760 位元組） | 每個記錄 |
| **最大欄數** | 2,000 | 每個 proto 架構 / table |

### 超越單個串流的擴展

如果需要高於單個串流提供的吞吐量：

- 從不同用戶端開啟**多個串流**到相同 table
- Zerobus 支援**數千個並行用戶端**寫入相同 table
- 按鍵分割資料跨串流（例如裝置 ID、區域）
- 聯絡 Databricks 以了解自訂吞吐量需求

---

## 區域可用性

Workspace 和目標 tables 必須在雲端供應商支援的區域中。

### AWS 支援的區域

| 區域 | 代碼 |
|--------|------|
| 美國東部（維吉尼亞北部） | `us-east-1` |
| 美國東部（俄亥俄州） | `us-east-2` |
| 美國西部（俄勒岡州） | `us-west-2` |
| 歐洲（法蘭克福） | `eu-central-1` |
| 歐洲（愛爾蘭） | `eu-west-1` |
| 亞太（新加坡） | `ap-southeast-1` |
| 亞太（雪梨） | `ap-southeast-2` |
| 亞太（東京） | `ap-northeast-1` |
| 加拿大（中部） | `ca-central-1` |

### Azure 支援的區域

| 區域 | 代碼 |
|--------|------|
| 加拿大中部 | `canadacentral` |
| 美國西部 | `westus` |
| 美國東部 | `eastus` |
| 美國東部 2 | `eastus2` |
| 美國中部 | `centralus` |
| 美國中北部 | `northcentralus` |
| 瑞典中部 | `swedencentral` |
| 西歐 | `westeurope` |
| 北歐 | `northeurope` |
| 澳洲東部 | `australiaeast` |
| 東南亞 | `southeastasia` |

**效能注意：** 最佳吞吐量需要用戶端應用程式和 Zerobus 端點位於**相同區域**。

---

## 耐久性和可用性

- **單一 AZ 僅限**：Zerobus 在單一可用性區域中運行。如果該區域不可用，服務可能經歷停機時間。
- **無地理冗餘**：在生產者的重試邏輯中規劃區域停機。
- **維護時段**：伺服器可能在維護期間關閉串流。用戶端應優雅地處理重新連線。

---

## 目標 Table 限制

| 限制 | 詳細資訊 |
|------------|---------|
| **Table 型別** | 受管 Delta tables 僅限（無外部存儲） |
| **Table 名稱** | 僅 ASCII 字母、數字、底線 |
| **Schema 變更** | 無自動演進；重新產生 proto 並重新部署 |
| **Table 建立** | Zerobus 不建立 tables；透過 SQL DDL 預先建立 |
| **Table 重建** | 無法透過 Zerobus 重建現有目標 table |

---

## 支援的資料型別

| Delta 型別 | Protobuf 型別 | 轉換備註 |
|------------|---------------|------------------|
| STRING | string | 直接對應 |
| INT / INTEGER | int32 | 直接對應 |
| LONG / BIGINT | int64 | 直接對應 |
| FLOAT | float | 直接對應 |
| DOUBLE | double | 直接對應 |
| BOOLEAN | bool | 直接對應 |
| BINARY | bytes | 直接對應 |
| ARRAY\<T\> | repeated T | 遞迴對應 |
| MAP\<K,V\> | map\<K,V\> | 鍵必須是字串或整數 |
| STRUCT | nested message | 遞迴對應 |
| DATE | int32 | 1970-01-01 以來的時代日期 |
| TIMESTAMP | int64 | 時代微秒 |
| VARIANT | string | JSON 編碼的字串 |

---

## 監控和可觀測性

Zerobus 目前不公開內建計量儀表板。使用以下方式監控生產者：

- **應用程式層級日誌記錄**：記錄 ACK 偏移量、重試計數和錯誤率
- **ACK 回呼追蹤**：追蹤最後確認的偏移量以測量擷取延遲
- **Table 列計數**：定期查詢目標 table 以驗證資料正在到達
- **健康檢查**：嘗試輕量級擷取（或串流建立）以驗證連線

```python
# 簡單的健康檢查
def check_zerobus_health(sdk, client_id, client_secret, table_props, options):
    try:
        stream = sdk.create_stream(client_id, client_secret, table_props, options)
        stream.close()
        return True
    except Exception as e:
        logger.error("Zerobus 健康檢查失敗：%s", e)
        return False
```
