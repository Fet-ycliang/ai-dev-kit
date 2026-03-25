# Lakebase 自動擴展計算

## 概觀

計算是運行分支 Postgres 的虛擬化服務。每個分支有一個主要讀寫計算，可以有選用的讀取副本。計算支援自動擴展、縮放至零和從 0.5 到 112 CU 的細粒度調整。

## 計算大小調整

每個計算單位 (CU) 分配約 2 GB 的 RAM。

### 可用大小

| 類別 | 範圍 | 備註 |
|----------|-------|-------|
| **自動擴展計算** | 0.5-32 CU | 在範圍內動態擴展（最大-最小 <= 8 CU） |
| **大型固定大小** | 36-112 CU | 固定大小，無自動擴展 |

### 代表性大小

| 計算單位 | RAM | 最大連線數 |
|--------------|-----|-----------------|
| 0.5 CU | ~1 GB | 104 |
| 1 CU | ~2 GB | 209 |
| 4 CU | ~8 GB | 839 |
| 8 CU | ~16 GB | 1,678 |
| 16 CU | ~32 GB | 3,357 |
| 32 CU | ~64 GB | 4,000 |
| 64 CU | ~128 GB | 4,000 |
| 112 CU | ~224 GB | 4,000 |

**注意：** Lakebase Provisioned 使用每 CU 約 16 GB。自動擴展使用每 CU 約 2 GB 以提供更細粒度的擴展。

## 建立計算

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, EndpointType

w = WorkspaceClient()

# 建立讀寫計算端點
result = w.postgres.create_endpoint(
    parent="projects/my-app/branches/production",
    endpoint=Endpoint(
        spec=EndpointSpec(
            endpoint_type=EndpointType.ENDPOINT_TYPE_READ_WRITE,
            autoscaling_limit_min_cu=0.5,
            autoscaling_limit_max_cu=4.0
        )
    ),
    endpoint_id="my-compute"
).wait()

print(f"端點已建立：{result.name}")
print(f"主機：{result.status.hosts.host}")
```

### CLI

```bash
databricks postgres create-endpoint \
    projects/my-app/branches/production my-compute \
    --json '{
        "spec": {
            "endpoint_type": "ENDPOINT_TYPE_READ_WRITE",
            "autoscaling_limit_min_cu": 0.5,
            "autoscaling_limit_max_cu": 4.0
        }
    }'
```

**重要：** 每個分支只能有一個讀寫計算。

## 取得計算詳細資訊

```python
endpoint = w.postgres.get_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute"
)

print(f"端點：{endpoint.name}")
print(f"類型：{endpoint.status.endpoint_type}")
print(f"狀態：{endpoint.status.current_state}")
print(f"主機：{endpoint.status.hosts.host}")
print(f"最小 CU：{endpoint.status.autoscaling_limit_min_cu}")
print(f"最大 CU：{endpoint.status.autoscaling_limit_max_cu}")
```

## 列出計算

```python
endpoints = list(w.postgres.list_endpoints(
    parent="projects/my-app/branches/production"
))

for ep in endpoints:
    print(f"端點：{ep.name}")
    print(f"  類型：{ep.status.endpoint_type}")
    print(f"  CU 範圍：{ep.status.autoscaling_limit_min_cu}-{ep.status.autoscaling_limit_max_cu}")
```

## 調整計算大小

使用 `update_mask` 指定要更新的欄位：

```python
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, FieldMask

# 更新最小和最大 CU
w.postgres.update_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute",
    endpoint=Endpoint(
        name="projects/my-app/branches/production/endpoints/my-compute",
        spec=EndpointSpec(
            autoscaling_limit_min_cu=2.0,
            autoscaling_limit_max_cu=8.0
        )
    ),
    update_mask=FieldMask(field_mask=[
        "spec.autoscaling_limit_min_cu",
        "spec.autoscaling_limit_max_cu"
    ])
).wait()
```

### CLI

```bash
# 更新單一欄位
databricks postgres update-endpoint \
    projects/my-app/branches/production/endpoints/my-compute \
    spec.autoscaling_limit_max_cu \
    --json '{"spec": {"autoscaling_limit_max_cu": 8.0}}'

# 更新多個欄位
databricks postgres update-endpoint \
    projects/my-app/branches/production/endpoints/my-compute \
    "spec.autoscaling_limit_min_cu,spec.autoscaling_limit_max_cu" \
    --json '{"spec": {"autoscaling_limit_min_cu": 2.0, "autoscaling_limit_max_cu": 8.0}}'
```

## 刪除計算

```python
w.postgres.delete_endpoint(
    name="projects/my-app/branches/production/endpoints/my-compute"
).wait()
```

## 自動擴展

自動擴展根據工作負載需求動態調整計算資源。

### 設定

- **範圍：** 0.5-32 CU
- **限制：** 最大值 - 最小值不能超過 8 CU
- **有效範例：** 4-8 CU、8-16 CU、16-24 CU
- **無效範例：** 0.5-32 CU（範圍為 31.5 CU）

### 最佳實務

- 設定最小 CU 足夠大以在記憶體中快取工作集
- 在計算擴展並快取資料之前，效能可能會降低
- 連線限制基於範圍中的最大 CU

## 縮放至零

在閒置一段時間後自動暫停計算。

| 設定 | 說明 |
|---------|-------------|
| **啟用** | 計算在閒置逾時後暫停（節省成本） |
| **停用** | 始終活躍的計算（消除喚醒延遲） |

**預設行為：**
- `production` 分支：縮放至零**停用**（始終活躍）
- 其他分支：縮放至零可配置

**預設閒置逾時：** 5 分鐘
**最小閒置逾時：** 60 秒

### 喚醒行為

當連線到達暫停計算時：
1. 計算自動啟動（重新啟動需要幾百毫秒）
2. 連線請求在活躍後被透明地處理
3. 計算以最小自動擴展大小重新啟動（如果啟用自動擴展）
4. 應用程式應在簡短重新啟動期間實現連線重試邏輯

### 重新啟動後的工作階段內容

當計算暫停並重新啟動時，工作階段內容**重設**：
- 記憶體中的統計資訊和快取內容被清除
- 臨時資料表和準備的陳述式遺失
- 工作階段特定設定重設
- 連線池和活躍事務被終止

如果應用程式需要持久工作階段資料，考慮停用縮放至零。

## 大小調整指南

| 因素 | 建議 |
|--------|---------------|
| 查詢複雜性 | 複雜分析查詢受益於更大的計算 |
| 並行連線 | 更多連線需要更多 CPU 和記憶體 |
| 資料量 | 更大資料集可能需要更多記憶體以提高效能 |
| 響應時間 | 關鍵應用可能需要更大計算 |
