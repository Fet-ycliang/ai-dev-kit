# Databricks Asset Bundles 的 SQL Alert 資源

## 重要：先進行 Schema 驗證

**務必先從檢查 schema 開始：**
```bash
databricks bundle schema | grep -A 100 'sql.AlertV2'
```

Alert v2 API 的 schema 與其他資源有顯著差異。不要自行假設欄位名稱。

## 應避免的常見 Schema 錯誤

### ❌ 錯誤 - 這些欄位不存在：
```yaml
condition:                    # 應為 "evaluation"
  op: LESS_THAN
  operand:
    column:                   # 巢狀層級錯誤
      name: "r"

schedule:
  cron_schedule:              # 應直接放在 schedule 底下
    quartz_cron_expression: "..."

subscriptions:                # 應放在 evaluation.notification 底下
  - destination_type: "EMAIL"
```

### ✅ 正確 - Alerts v2 API 結構：
```yaml
evaluation:                   # 不是 "condition"
  comparison_operator: 'LESS_THAN_OR_EQUAL'
  source:                     # 不要巢狀放在 "operand.column" 底下
    name: 'column_name'
    display: 'column_name'
  threshold:
    value:
      double_value: 100
  notification:               # Subscriptions 需巢狀放在這裡
    notify_on_ok: false
    subscriptions:
      - user_email: "${workspace.current_user.userName}"

schedule:                     # 欄位直接位於 schedule 底下
  pause_status: 'UNPAUSED'    # 必填
  quartz_cron_schedule: '0 38 16 * * ?'  # 必填
  timezone_id: 'America/Los_Angeles'     # 必填
```

## Alert 觸發邏輯

**重要：** Alert 會在條件評估結果為 **TRUE** 時觸發，而不是 FALSE。

**錯誤做法：** 使用 `GREATER_THAN` 並期待在條件為 false 時觸發 Alert
**正確做法：** 使用能直接表達你意圖的 operator

### 範例：當 count 不是 > 100（也就是 ≤ 100）時觸發 Alert
```yaml
# ❌ 錯誤 - 這會在 count 確實 > 100 時觸發
comparison_operator: 'GREATER_THAN'

# ✅ 正確 - 這會在 count 確實 <= 100 時觸發
comparison_operator: 'LESS_THAN_OR_EQUAL'
```

## Email 通知

```yaml
evaluation:
  notification:
    subscriptions:
      - user_email: "${workspace.current_user.userName}"
```

## Quartz Cron

格式：`second minute hour day-of-month month day-of-week`（當 day-of-month 使用 `*` 時，day-of-week 請使用 `?`）

範例：`'0 0 9 * * ?'`（每天上午 9 點）、`'0 */30 * * * ?'`（每 30 分鐘）

## 必填欄位

```yaml
resources:
  alerts:
    alert_name:
      display_name: "[${bundle.target}] Alert Name"     # 必填
      query_text: "SELECT count(*) c FROM table"        # 必填
      warehouse_id: ${var.warehouse_id}                 # 必填

      evaluation:                                        # 必填
        comparison_operator: 'LESS_THAN'                # 必填
        source:                                          # 必填
          name: 'c'
          display: 'c'
        threshold:
          value:
            double_value: 100
        notification:
          notify_on_ok: false
          subscriptions:
            - user_email: "${workspace.current_user.userName}"

      schedule:                                          # 必填
        pause_status: 'UNPAUSED'                        # 必填
        quartz_cron_schedule: '0 0 9 * * ?'            # 必填
        timezone_id: 'America/Los_Angeles'             # 必填

      permissions:
        - level: CAN_RUN
          group_name: "users"
```

## 比較運算子

`EQUAL`, `NOT_EQUAL`, `GREATER_THAN`, `GREATER_THAN_OR_EQUAL`, `LESS_THAN`, `LESS_THAN_OR_EQUAL`

## 權限層級

`CAN_READ`, `CAN_RUN`（建議）, `CAN_EDIT`, `CAN_MANAGE`
