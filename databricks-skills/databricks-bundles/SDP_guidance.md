# DABs 的 SDP 管線設定

## 關鍵決策（若不明確請詢問）
1. 偏向串流還是批次？
2. 連續執行還是觸發式執行？
3. Serverless（預設值）還是 classic compute？

## Pipeline 資源模式

```yaml
resources:
  pipelines:
    pipeline_name:
      name: "[${bundle.target}] Pipeline Name"

      # 目標 catalog 和 schema
      catalog: ${var.catalog}
      target: ${var.schema}

      # Pipeline 程式庫
      libraries:
        - glob:
            include: ../src/pipelines/<pipeline_folder>/transformations/**
      
      root_path: ../src/pipelines/<pipeline_folder>

      serverless: true

      # Pipeline 設定
      configuration:
        source_catalog: ${var.source_catalog}
        source_schema: ${var.source_schema}

      continuous: false
      development: true
      photon: true

      channel: current

      permissions:
        - level: CAN_VIEW
          group_name: "users"
```

**權限層級**：`CAN_VIEW`, `CAN_RUN`, `CAN_MANAGE`

## 最佳實務

1. **對較新的組織結構使用 `root_path` 和 `libraries.glob`**
2. **除非使用者另有指定，否則預設使用 serverless**
3. **使用變數** 為 catalog/schema 參數化
4. **在 dev/staging 目標環境中設定 `development: true`**
