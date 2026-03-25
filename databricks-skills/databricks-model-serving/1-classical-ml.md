# 傳統 ML 模型服務

使用 MLflow autolog 部署傳統 ML 模型（sklearn、xgboost、pytorch 等）。

## Autolog 模式（建議）

部署 ML 模型最簡便的方式——訓練後所有內容自動記錄。

```python
import mlflow
import mlflow.sklearn
from sklearn.linear_model import ElasticNet
from sklearn.model_selection import train_test_split

# 設定
catalog = "main"
schema = "models"
model_name = "diabetes_predictor"

# 啟用 autolog 並自動註冊至 Unity Catalog
mlflow.sklearn.autolog(
    log_input_examples=True,
    registered_model_name=f"{catalog}.{schema}.{model_name}"
)

# 載入並切分資料
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25)

# 訓練——模型自動記錄並註冊
model = ElasticNet(alpha=0.05, l1_ratio=0.05)
model.fit(X_train, y_train)

# 完成！模型已在 Unity Catalog 中，準備好供服務使用
```

## 支援的框架

| 框架 | Autolog 函式 | 備注 |
|------|-------------|------|
| sklearn | `mlflow.sklearn.autolog()` | 大多數 sklearn estimator |
| xgboost | `mlflow.xgboost.autolog()` | XGBClassifier、XGBRegressor |
| lightgbm | `mlflow.lightgbm.autolog()` | LGBMClassifier 等 |
| pytorch | `mlflow.pytorch.autolog()` | 支援 Lightning |
| tensorflow | `mlflow.tensorflow.autolog()` | Keras 模型 |
| spark | `mlflow.spark.autolog()` | Spark ML Pipeline |

## 手動記錄（當 Autolog 不足時）

```python
import mlflow
from sklearn.ensemble import RandomForestClassifier

mlflow.set_registry_uri("databricks-uc")

with mlflow.start_run():
    # 訓練模型
    model = RandomForestClassifier(n_estimators=100)
    model.fit(X_train, y_train)

    # 記錄指標
    accuracy = model.score(X_test, y_test)
    mlflow.log_metric("accuracy", accuracy)

    # 記錄模型並附上簽章
    from mlflow.models import infer_signature
    signature = infer_signature(X_train, model.predict(X_train))

    model_info = mlflow.sklearn.log_model(
        model,
        artifact_path="model",
        signature=signature,
        input_example=X_train[:5],
        registered_model_name="main.models.random_forest"
    )
```

## 部署至服務端點

### 選項一：Databricks UI

1. 前往工作區中的 **Serving**
2. 點擊 **Create serving endpoint**
3. 從 Unity Catalog 選取您的模型
4. 設定擴展參數（workload size、scale-to-zero）
5. 點擊 **Create**

### 選項二：MLflow Deployments SDK

```python
from mlflow.deployments import get_deploy_client

mlflow.set_registry_uri("databricks-uc")
client = get_deploy_client("databricks")

endpoint = client.create_endpoint(
    name="diabetes-predictor",
    config={
        "served_entities": [
            {
                "entity_name": "main.models.diabetes_predictor",
                "entity_version": "1",
                "workload_size": "Small",
                "scale_to_zero_enabled": True
            }
        ],
        "traffic_config": {
            "routes": [
                {
                    "served_model_name": "diabetes_predictor-1",
                    "traffic_percentage": 100
                }
            ]
        }
    }
)
```

### 選項三：Databricks SDK

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

endpoint = w.serving_endpoints.create_and_wait(
    name="diabetes-predictor",
    config={
        "served_entities": [
            {
                "entity_name": "main.models.diabetes_predictor",
                "entity_version": "1",
                "workload_size": "Small",
                "scale_to_zero_enabled": True
            }
        ]
    },
    timeout=timedelta(minutes=30)
)
```

## 查詢端點

### 透過 MCP 工具

```
query_serving_endpoint(
    name="diabetes-predictor",
    dataframe_records=[
        {"age": 45, "bmi": 25.3, "bp": 120, "s1": 200}
    ]
)
```

### 透過 Python SDK

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
response = w.serving_endpoints.query(
    name="diabetes-predictor",
    dataframe_records=[
        {"age": 45, "bmi": 25.3, "bp": 120, "s1": 200}
    ]
)
print(response.predictions)
```

## 最佳實踐

1. **務必使用 `log_input_examples=True`** — 有助於偵錯與 schema 推論
2. **使用 Unity Catalog** — `registered_model_name="catalog.schema.model"`
3. **啟用 scale-to-zero** — 端點閒置時節省費用
4. **先在本地測試** — 部署前使用 `mlflow.pyfunc.load_model()`
5. **版本管理** — UC 自動追蹤版本
