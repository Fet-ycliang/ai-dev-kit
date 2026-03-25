# Unity Catalog Volumes

Unity Catalog Volumes 完整參考：檔案操作、權限管理與最佳實踐。

## 概覽

Volumes 是 Unity Catalog 用於存取、儲存和管理檔案的功能。與資料表（結構化資料）不同，Volumes 儲存非結構化或半結構化的檔案。

| Volume 類型 | 說明 | 儲存位置 |
|------------|------|---------|
| **Managed（受管）** | Databricks 管理儲存位置 | 預設 Metastore 位置 |
| **External（外部）** | 使用者自行管理儲存位置 | 您的雲端儲存（S3、ADLS、GCS） |

**常見使用情境：**
- ML 訓練資料（影像、音訊、影片、PDF）
- 資料探索與暫存
- 函式庫檔案（.whl、.jar）
- 設定檔與腳本
- ETL 落地區（Landing Zone）

---

## Volume 路徑格式

所有 Volume 操作使用以下路徑格式：

```
/Volumes/<catalog>/<schema>/<volume>/<path_to_file>
```

**範例：**
```
/Volumes/main/default/my_volume/data.csv
/Volumes/analytics/raw/landing_zone/2024/01/orders.parquet
/Volumes/ml/training/images/cats/cat_001.jpg
```

---

## MCP 工具

### 列出 Volume 中的檔案

```python
# 列出檔案與目錄
list_volume_files(
    volume_path="/Volumes/main/default/my_volume/data/"
)
# 回傳：[{"name": "file.csv", "path": "...", "is_directory": false, "file_size": 1024, "last_modified": "..."}]
```

### 上傳檔案至 Volume

```python
# 上傳本地檔案
upload_to_volume(
    local_path="/tmp/data.csv",
    volume_path="/Volumes/main/default/my_volume/data.csv",
    overwrite=True
)
# 回傳：{"local_path": "...", "volume_path": "...", "success": true}
```

### 從 Volume 下載檔案

```python
# 下載至本地路徑
download_from_volume(
    volume_path="/Volumes/main/default/my_volume/data.csv",
    local_path="/tmp/downloaded.csv",
    overwrite=True
)
# 回傳：{"volume_path": "...", "local_path": "...", "success": true}
```

### 建立目錄

```python
# 建立目錄（類似 mkdir -p，自動建立父目錄）
create_volume_directory(
    volume_path="/Volumes/main/default/my_volume/data/2024/01"
)
# 回傳：{"volume_path": "...", "success": true}
```

### 刪除檔案

```python
# 刪除檔案
delete_volume_file(
    volume_path="/Volumes/main/default/my_volume/old_data.csv"
)
# 回傳：{"volume_path": "...", "success": true}
```

### 取得檔案資訊

```python
# 取得檔案中繼資料
get_volume_file_info(
    volume_path="/Volumes/main/default/my_volume/data.csv"
)
# 回傳：{"name": "data.csv", "file_size": 1024, "last_modified": "...", "success": true}
```

---

## Python SDK 範例

### Volume CRUD 操作

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import VolumeType

w = WorkspaceClient()

# 列出 Schema 中的 Volumes
for volume in w.volumes.list(catalog_name="main", schema_name="default"):
    print(f"{volume.full_name}: {volume.volume_type}")

# 取得 Volume 詳情
volume = w.volumes.read(name="main.default.my_volume")
print(f"Storage: {volume.storage_location}")

# 建立受管 Volume
managed = w.volumes.create(
    catalog_name="main",
    schema_name="default",
    name="my_managed_volume",
    volume_type=VolumeType.MANAGED,
    comment="ML 資料用受管 Volume"
)

# 建立外部 Volume
external = w.volumes.create(
    catalog_name="main",
    schema_name="default",
    name="my_external_volume",
    volume_type=VolumeType.EXTERNAL,
    storage_location="s3://my-bucket/volumes/data",
    comment="S3 上的外部 Volume"
)

# 更新 Volume
w.volumes.update(
    name="main.default.my_volume",
    comment="已更新的說明"
)

# 刪除 Volume
w.volumes.delete(name="main.default.my_volume")
```

### 檔案操作

```python
from databricks.sdk import WorkspaceClient
import io

w = WorkspaceClient()

# 從記憶體上傳檔案
data = b"col1,col2\n1,2\n3,4"
w.files.upload(
    file_path="/Volumes/main/default/my_volume/data.csv",
    contents=io.BytesIO(data),
    overwrite=True
)

# 從磁碟上傳（大型檔案建議使用）
w.files.upload_from(
    file_path="/Volumes/main/default/my_volume/large_file.parquet",
    source_path="/local/path/large_file.parquet",
    overwrite=True,
    use_parallel=True  # 大型檔案使用平行上傳
)

# 列出目錄內容
for entry in w.files.list_directory_contents("/Volumes/main/default/my_volume/"):
    file_type = "目錄" if entry.is_directory else "檔案"
    print(f"{entry.name}: {file_type} ({entry.file_size} bytes)")

# 下載檔案至記憶體
response = w.files.download("/Volumes/main/default/my_volume/data.csv")
content = response.contents.read()

# 下載檔案至磁碟（大型檔案建議使用）
w.files.download_to(
    file_path="/Volumes/main/default/my_volume/large_file.parquet",
    destination="/local/path/downloaded.parquet",
    use_parallel=True  # 大型檔案使用平行下載
)

# 建立目錄
w.files.create_directory("/Volumes/main/default/my_volume/new_folder/")

# 刪除檔案
w.files.delete("/Volumes/main/default/my_volume/old_data.csv")

# 刪除空目錄
w.files.delete_directory("/Volumes/main/default/my_volume/empty_folder/")

# 取得檔案中繼資料
metadata = w.files.get_metadata("/Volumes/main/default/my_volume/data.csv")
print(f"Size: {metadata.content_length}, Modified: {metadata.last_modified}")
```

---

## SQL 操作

### 查詢 Volume 中繼資料

```sql
-- 列出某 Catalog 下的所有 Volumes
SELECT
    volume_catalog,
    volume_schema,
    volume_name,
    volume_type,
    storage_location,
    comment,
    created,
    created_by
FROM system.information_schema.volumes
WHERE volume_catalog = 'analytics'
ORDER BY volume_schema, volume_name;

-- 依類型篩選 Volumes
SELECT volume_name, storage_location
FROM system.information_schema.volumes
WHERE volume_type = 'EXTERNAL';
```

### 從 Volumes 讀取檔案

```sql
-- 讀取 CSV 檔案
SELECT * FROM read_files('/Volumes/main/default/my_volume/data.csv');

-- 讀取時指定選項
SELECT * FROM read_files(
    '/Volumes/main/default/my_volume/data/',
    format => 'csv',
    header => true,
    inferSchema => true
);

-- 讀取 Parquet 檔案
SELECT * FROM read_files(
    '/Volumes/main/default/my_volume/parquet_data/',
    format => 'parquet'
);

-- 讀取 JSON 檔案
SELECT * FROM read_files(
    '/Volumes/main/default/my_volume/events/*.json',
    format => 'json'
);

-- 從 Volume 檔案建立資料表
CREATE TABLE analytics.bronze.raw_orders AS
SELECT * FROM read_files('/Volumes/analytics/raw/landing/orders/');
```

### 寫入檔案至 Volumes

```sql
-- 匯出為 Parquet 至 Volume
COPY INTO '/Volumes/main/default/my_volume/export/'
FROM (SELECT * FROM analytics.gold.customers)
FILEFORMAT = PARQUET;

-- 匯出為 CSV
COPY INTO '/Volumes/main/default/my_volume/export/'
FROM (SELECT * FROM analytics.gold.report)
FILEFORMAT = CSV
HEADER = true;
```

---

## 權限管理

### 所需權限

| 操作 | 所需權限 |
|------|---------|
| 列出檔案 | `READ VOLUME` |
| 讀取檔案 | `READ VOLUME` |
| 寫入檔案 | `WRITE VOLUME` |
| 建立 Volume | Schema 上的 `CREATE VOLUME` |
| 刪除 Volume | 擁有者或 `MANAGE` |

> **注意：** 同時需要父 Catalog 的 `USE CATALOG` 與父 Schema 的 `USE SCHEMA` 權限。

### 授予權限（SQL）

```sql
-- 授予讀取權限
GRANT READ VOLUME ON VOLUME main.default.my_volume TO `data_readers`;

-- 授予寫入權限
GRANT WRITE VOLUME ON VOLUME main.default.my_volume TO `data_writers`;

-- 授予在 Schema 中建立 Volume 的權限
GRANT CREATE VOLUME ON SCHEMA main.default TO `data_engineers`;

-- 撤銷權限
REVOKE WRITE VOLUME ON VOLUME main.default.my_volume FROM `data_writers`;
```

### 授予權限（Python SDK）

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import SecurableType, PermissionsChange, Privilege

w = WorkspaceClient()

# 授予權限
w.grants.update(
    securable_type=SecurableType.VOLUME,
    full_name="main.default.my_volume",
    changes=[
        PermissionsChange(
            add=[Privilege.READ_VOLUME],
            principal="data_readers"
        )
    ]
)

# 查看目前權限
grants = w.grants.get(
    securable_type=SecurableType.VOLUME,
    full_name="main.default.my_volume"
)
for grant in grants.privilege_assignments:
    print(f"{grant.principal}: {grant.privileges}")
```

---

## 最佳實踐

### 目錄組織

1. **使用有意義的路徑** — 依日期、來源或類型組織
   ```
   /Volumes/catalog/schema/volume/year=2024/month=01/file.parquet
   /Volumes/catalog/schema/volume/source=salesforce/accounts.csv
   ```

2. **區分原始資料與處理後資料** — 使用不同 Volume 區分落地區與整理後資料
   ```
   /Volumes/analytics/raw/landing_zone/    # 原始上傳
   /Volumes/analytics/curated/processed/   # 清理後資料
   ```

3. **封存舊資料** — 將不常存取的檔案移至封存 Volume

### 效能

1. **大型檔案使用平行上傳**（SDK v0.72.0+）
   ```python
   w.files.upload_from(..., use_parallel=True)
   ```

2. **合併小檔案** — 將大量小檔案合併為較大的封存檔

3. **使用 Parquet 格式** — 欄位式格式更適合分析查詢

4. **依日期分區** — 讓查詢可有效剪枝

### 資安

1. 當 Databricks 應管理儲存時，**使用受管 Volume**

2. 在以下情況**使用外部 Volume**：
   - 現有雲端儲存中已有資料
   - 需要跨工作區存取
   - 需要自訂資料保留政策

3. **最小權限原則** — 僅授予必要的權限

4. **稽核存取記錄** — 在稽核日誌中監控 Volume 存取
   ```sql
   SELECT *
   FROM system.access.audit
   WHERE action_name LIKE '%Volume%'
     AND event_date >= current_date() - 7;
   ```

---

## 疑難排解

### 常見錯誤

| 錯誤 | 原因 | 解決方式 |
|------|------|---------|
| `PERMISSION_DENIED` | 缺少 Volume 權限 | 授予 `READ VOLUME` 或 `WRITE VOLUME` |
| `NOT_FOUND` | Volume 或路徑不存在 | 確認路徑拼寫，確保 Volume 已存在 |
| `ALREADY_EXISTS` | 檔案已存在且 overwrite=False | 設定 `overwrite=True` 或先刪除檔案 |
| `RESOURCE_DOES_NOT_EXIST` | 父目錄不存在 | 先建立父目錄 |
| `INVALID_PARAMETER_VALUE` | 路徑格式不正確 | 使用 `/Volumes/catalog/schema/volume/path` 格式 |

### 除錯清單

1. **確認 Volume 存在：**
   ```sql
   SELECT * FROM system.information_schema.volumes
   WHERE volume_name = 'my_volume';
   ```

2. **確認權限：**
   ```python
   grants = w.grants.get(
       securable_type=SecurableType.VOLUME,
       full_name="catalog.schema.volume"
   )
   ```

3. **確認路徑格式：**
   - 必須以 `/Volumes/` 開頭
   - 三層命名空間：`catalog/schema/volume`
   - 不可有連續斜線（`//`）

4. **確認檔案存在：**
   ```python
   try:
       w.files.get_metadata("/Volumes/catalog/schema/volume/file.csv")
   except Exception as e:
       print(f"找不到檔案：{e}")
   ```

### 外部 Volume 問題

1. **需要 Storage Credential** — 外部 Volume 須有對應的 Storage Credential
   ```python
   # 先建立 Storage Credential
   w.storage_credentials.create(
       name="my_s3_cred",
       aws_iam_role={"role_arn": "arn:aws:iam::..."}
   )

   # 建立 External Location
   w.external_locations.create(
       name="my_s3_location",
       url="s3://my-bucket/path",
       credential_name="my_s3_cred"
   )

   # 再建立外部 Volume
   w.volumes.create(
       ...
       volume_type=VolumeType.EXTERNAL,
       storage_location="s3://my-bucket/path/volume"
   )
   ```

2. **網路存取** — 確認工作區可連接雲端儲存

3. **IAM 權限** — 確認 IAM Role 具有 Bucket 存取權限
