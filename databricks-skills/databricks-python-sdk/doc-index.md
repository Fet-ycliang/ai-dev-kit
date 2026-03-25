# Databricks Python SDK - 文件索引

API 作業與文件 URL 的完整對照。

**基底 URL：** `https://databricks-sdk-py.readthedocs.io/en/latest`

> **重要：** 此 SDK 為同步式。在 async 應用程式（FastAPI）中，請以 `asyncio.to_thread()` 包裝所有 SDK 呼叫，避免阻塞事件迴圈。範例請參閱 `SKILL.md`。

---

## 叢集 API
**文件：** /workspace/compute/clusters.html

| 方法 | 簽章 |
|--------|-----------|
| `w.clusters.list()` | `([filter_by, page_size, page_token, sort_by]) → Iterator[ClusterDetails]` |
| `w.clusters.get()` | `(cluster_id: str) → ClusterDetails` |
| `w.clusters.create()` | `(spark_version, [cluster_name, num_workers, ...]) → Wait[ClusterDetails]` |
| `w.clusters.create_and_wait()` | `(..., timeout) → ClusterDetails` |
| `w.clusters.edit()` | `(cluster_id, spark_version, [...]) → Wait[ClusterDetails]` |
| `w.clusters.delete()` | `(cluster_id) → Wait[ClusterDetails]` |
| `w.clusters.permanent_delete()` | `(cluster_id) → None` |
| `w.clusters.start()` | `(cluster_id) → Wait[ClusterDetails]` |
| `w.clusters.start_and_wait()` | `(cluster_id, timeout) → ClusterDetails` |
| `w.clusters.restart()` | `(cluster_id, [restart_user]) → Wait[ClusterDetails]` |
| `w.clusters.resize()` | `(cluster_id, [autoscale, num_workers]) → Wait[ClusterDetails]` |
| `w.clusters.events()` | `(cluster_id, [...]) → Iterator[ClusterEvent]` |
| `w.clusters.pin()` | `(cluster_id) → None` |
| `w.clusters.unpin()` | `(cluster_id) → None` |
| `w.clusters.select_spark_version()` | `([latest, long_term_support, ml, gpu, ...]) → str` |
| `w.clusters.select_node_type()` | `([min_memory_gb, min_cores, local_disk, ...]) → str` |
| `w.clusters.list_node_types()` | `() → ListNodeTypesResponse` |
| `w.clusters.spark_versions()` | `() → GetSparkVersionsResponse` |
| `w.clusters.list_zones()` | `() → ListAvailableZonesResponse` |
| `w.clusters.ensure_cluster_is_running()` | `(cluster_id) → None` |
| `w.clusters.change_owner()` | `(cluster_id, owner_username) → None` |
| `w.clusters.get_permissions()` | `(cluster_id) → ClusterPermissions` |
| `w.clusters.set_permissions()` | `(cluster_id, [access_control_list]) → ClusterPermissions` |
| `w.clusters.update_permissions()` | `(cluster_id, [access_control_list]) → ClusterPermissions` |

---

## 作業 API
**文件：** /workspace/jobs/jobs.html

| 方法 | 簽章 |
|--------|-----------|
| `w.jobs.list()` | `([expand_tasks, limit, name, offset]) → Iterator[BaseJob]` |
| `w.jobs.get()` | `(job_id, [page_token]) → Job` |
| `w.jobs.create()` | `([name, tasks, schedule, ...]) → CreateResponse` |
| `w.jobs.update()` | `(job_id, [new_settings, fields_to_remove]) → None` |
| `w.jobs.reset()` | `(job_id, new_settings: JobSettings) → None` |
| `w.jobs.delete()` | `(job_id) → None` |
| `w.jobs.run_now()` | `(job_id, [notebook_params, job_parameters, ...]) → Wait[Run]` |
| `w.jobs.run_now_and_wait()` | `(job_id, [...], timeout) → Run` |
| `w.jobs.submit()` | `([tasks, run_name, ...]) → Wait[Run]` |
| `w.jobs.submit_and_wait()` | `([...], timeout) → Run` |
| `w.jobs.cancel_run()` | `(run_id) → Wait[Run]` |
| `w.jobs.cancel_all_runs()` | `([all_queued_runs, job_id]) → None` |
| `w.jobs.list_runs()` | `([job_id, active_only, completed_only, ...]) → Iterator[BaseRun]` |
| `w.jobs.get_run()` | `(run_id, [include_history, include_resolved_values]) → Run` |
| `w.jobs.get_run_output()` | `(run_id) → RunOutput` |
| `w.jobs.export_run()` | `(run_id, [views_to_export]) → ExportRunOutput` |
| `w.jobs.delete_run()` | `(run_id) → None` |
| `w.jobs.repair_run()` | `(run_id, [rerun_tasks, rerun_all_failed_tasks, ...]) → Wait[Run]` |
| `w.jobs.get_permissions()` | `(job_id) → JobPermissions` |
| `w.jobs.set_permissions()` | `(job_id, [access_control_list]) → JobPermissions` |

---

## SQL 倉儲 API
**文件：** /workspace/sql/warehouses.html

| 方法 | 簽章 |
|--------|-----------|
| `w.warehouses.list()` | `([page_size, page_token, run_as_user_id]) → Iterator[EndpointInfo]` |
| `w.warehouses.get()` | `(id: str) → GetWarehouseResponse` |
| `w.warehouses.create()` | `([name, cluster_size, max_num_clusters, auto_stop_mins, ...]) → Wait[...]` |
| `w.warehouses.create_and_wait()` | `([...], timeout) → GetWarehouseResponse` |
| `w.warehouses.edit()` | `(id, [...]) → Wait[GetWarehouseResponse]` |
| `w.warehouses.delete()` | `(id) → None` |
| `w.warehouses.start()` | `(id) → Wait[GetWarehouseResponse]` |
| `w.warehouses.start_and_wait()` | `(id, timeout) → GetWarehouseResponse` |
| `w.warehouses.stop()` | `(id) → Wait[GetWarehouseResponse]` |
| `w.warehouses.stop_and_wait()` | `(id, timeout) → GetWarehouseResponse` |
| `w.warehouses.get_workspace_warehouse_config()` | `() → GetWorkspaceWarehouseConfigResponse` |
| `w.warehouses.set_workspace_warehouse_config()` | `([...]) → None` |
| `w.warehouses.get_permissions()` | `(warehouse_id) → WarehousePermissions` |
| `w.warehouses.set_permissions()` | `(warehouse_id, [access_control_list]) → WarehousePermissions` |

---

## 陳述式執行 API
**文件：** /workspace/sql/statement_execution.html

| 方法 | 簽章 |
|--------|-----------|
| `w.statement_execution.execute_statement()` | `(statement, warehouse_id, [catalog, schema, wait_timeout, ...]) → StatementResponse` |
| `w.statement_execution.get_statement()` | `(statement_id) → StatementResponse` |
| `w.statement_execution.get_statement_result_chunk_n()` | `(statement_id, chunk_index) → ResultData` |
| `w.statement_execution.cancel_execution()` | `(statement_id) → None` |

---

## 資料表 API（Unity Catalog）
**文件：** /workspace/catalog/tables.html

| 方法 | 簽章 |
|--------|-----------|
| `w.tables.list()` | `(catalog_name, schema_name, [max_results, omit_columns, ...]) → Iterator[TableInfo]` |
| `w.tables.list_summaries()` | `(catalog_name, [schema_name_pattern, table_name_pattern, ...]) → Iterator[TableSummary]` |
| `w.tables.get()` | `(full_name, [include_delta_metadata, ...]) → TableInfo` |
| `w.tables.exists()` | `(full_name) → TableExistsResponse` |
| `w.tables.create()` | `(name, catalog_name, schema_name, table_type, data_source_format, storage_location, [columns, ...]) → TableInfo` |
| `w.tables.update()` | `(full_name, [owner]) → None` |
| `w.tables.delete()` | `(full_name) → None` |

---

## 目錄 API
**文件：** /workspace/catalog/catalogs.html

| 方法 | 簽章 |
|--------|-----------|
| `w.catalogs.list()` | `([include_browse, max_results, page_token]) → Iterator[CatalogInfo]` |
| `w.catalogs.get()` | `(name, [include_browse]) → CatalogInfo` |
| `w.catalogs.create()` | `(name, [comment, storage_root, ...]) → CatalogInfo` |
| `w.catalogs.update()` | `(name, [new_name, owner, comment, ...]) → CatalogInfo` |
| `w.catalogs.delete()` | `(name, [force]) → None` |

---

## 結構描述 API
**文件：** /workspace/catalog/schemas.html

| 方法 | 簽章 |
|--------|-----------|
| `w.schemas.list()` | `(catalog_name, [max_results, page_token]) → Iterator[SchemaInfo]` |
| `w.schemas.get()` | `(full_name) → SchemaInfo` |
| `w.schemas.create()` | `(name, catalog_name, [comment, storage_root, ...]) → SchemaInfo` |
| `w.schemas.update()` | `(full_name, [new_name, owner, comment, ...]) → SchemaInfo` |
| `w.schemas.delete()` | `(full_name, [force]) → None` |

---

## 磁碟區 API
**文件：** /workspace/catalog/volumes.html

| 方法 | 簽章 |
|--------|-----------|
| `w.volumes.list()` | `(catalog_name, schema_name, [max_results, page_token]) → Iterator[VolumeInfo]` |
| `w.volumes.read()` | `(name, [include_browse]) → VolumeInfo` |
| `w.volumes.create()` | `(catalog_name, schema_name, name, volume_type, [comment, storage_location]) → VolumeInfo` |
| `w.volumes.update()` | `(name, [new_name, owner, comment]) → VolumeInfo` |
| `w.volumes.delete()` | `(name) → None` |

---

## 檔案 API
**文件：** /workspace/files/files.html

| 方法 | 簽章 |
|--------|-----------|
| `w.files.upload()` | `(file_path, contents: BinaryIO, [overwrite, use_parallel]) → UploadStreamResult` |
| `w.files.upload_from()` | `(file_path, source_path, [overwrite, use_parallel]) → UploadFileResult` |
| `w.files.download()` | `(file_path) → DownloadResponse` |
| `w.files.download_to()` | `(file_path, destination, [overwrite, use_parallel]) → DownloadFileResult` |
| `w.files.delete()` | `(file_path) → None` |
| `w.files.get_metadata()` | `(file_path) → GetMetadataResponse` |
| `w.files.create_directory()` | `(directory_path) → None` |
| `w.files.delete_directory()` | `(directory_path) → None` |
| `w.files.get_directory_metadata()` | `(directory_path) → None` |
| `w.files.list_directory_contents()` | `(directory_path, [page_size, page_token]) → Iterator[DirectoryEntry]` |

---

## Serving Endpoints API
**文件：** /workspace/serving/serving_endpoints.html

| 方法 | 簽章 |
|--------|-----------|
| `w.serving_endpoints.list()` | `() → Iterator[ServingEndpoint]` |
| `w.serving_endpoints.get()` | `(name) → ServingEndpointDetailed` |
| `w.serving_endpoints.create()` | `(name, [config, ...]) → Wait[ServingEndpointDetailed]` |
| `w.serving_endpoints.create_and_wait()` | `(name, [...], timeout) → ServingEndpointDetailed` |
| `w.serving_endpoints.update_config()` | `(name, [...]) → Wait[ServingEndpointDetailed]` |
| `w.serving_endpoints.delete()` | `(name) → None` |
| `w.serving_endpoints.query()` | `(name, [inputs, messages, ...]) → QueryEndpointResponse` |
| `w.serving_endpoints.logs()` | `(name, served_model_name) → ServerLogsResponse` |
| `w.serving_endpoints.build_logs()` | `(name, served_model_name) → BuildLogsResponse` |
| `w.serving_endpoints.export_metrics()` | `(name) → ExportMetricsResponse` |
| `w.serving_endpoints.get_open_ai_client()` | `() → OpenAI` |
| `w.serving_endpoints.put_ai_gateway()` | `(name, [...]) → PutAiGatewayResponse` |
| `w.serving_endpoints.get_permissions()` | `(serving_endpoint_id) → ServingEndpointPermissions` |
| `w.serving_endpoints.set_permissions()` | `(serving_endpoint_id, [...]) → ServingEndpointPermissions` |

---

## Vector Search 索引 API
**文件：** /workspace/vectorsearch/vector_search_indexes.html

| 方法 | 簽章 |
|--------|-----------|
| `w.vector_search_indexes.list_indexes()` | `(endpoint_name, [page_token]) → Iterator[MiniVectorIndex]` |
| `w.vector_search_indexes.get_index()` | `(index_name, [include_reranker]) → VectorIndex` |
| `w.vector_search_indexes.create_index()` | `(name, endpoint_name, primary_key, index_type, [...]) → CreateVectorIndexResponse` |
| `w.vector_search_indexes.delete_index()` | `(index_name) → None` |
| `w.vector_search_indexes.sync_index()` | `(index_name) → None` |
| `w.vector_search_indexes.query_index()` | `(index_name, columns, [query_text, query_vector, filters, num_results, ...]) → QueryVectorIndexResponse` |
| `w.vector_search_indexes.query_next_page()` | `(index_name, page_token) → QueryVectorIndexResponse` |
| `w.vector_search_indexes.scan_index()` | `(index_name, [last_primary_key, num_results]) → ScanVectorIndexResponse` |
| `w.vector_search_indexes.upsert_data_vector_index()` | `(index_name, inputs_json) → UpsertDataVectorIndexResponse` |
| `w.vector_search_indexes.delete_data_vector_index()` | `(index_name, primary_keys) → DeleteDataVectorIndexResponse` |

---

## 管線 API（Delta Live Tables）
**文件：** /workspace/pipelines/pipelines.html

| 方法 | 簽章 |
|--------|-----------|
| `w.pipelines.list_pipelines()` | `([filter, max_results, ...]) → Iterator[PipelineStateInfo]` |
| `w.pipelines.get()` | `(pipeline_id) → GetPipelineResponse` |
| `w.pipelines.create()` | `([name, clusters, libraries, ...]) → CreatePipelineResponse` |
| `w.pipelines.update()` | `(pipeline_id, [...]) → None` |
| `w.pipelines.delete()` | `(pipeline_id) → None` |
| `w.pipelines.start_update()` | `(pipeline_id, [full_refresh, ...]) → StartUpdateResponse` |
| `w.pipelines.stop()` | `(pipeline_id) → Wait[GetPipelineResponse]` |
| `w.pipelines.stop_and_wait()` | `(pipeline_id, timeout) → GetPipelineResponse` |
| `w.pipelines.list_updates()` | `(pipeline_id, [...]) → ListUpdatesResponse` |
| `w.pipelines.get_update()` | `(pipeline_id, update_id) → GetUpdateResponse` |
| `w.pipelines.list_pipeline_events()` | `(pipeline_id, [...]) → Iterator[PipelineEvent]` |
| `w.pipelines.get_permissions()` | `(pipeline_id) → PipelinePermissions` |
| `w.pipelines.set_permissions()` | `(pipeline_id, [...]) → PipelinePermissions` |

---

## Secrets API
**文件：** /workspace/workspace/secrets.html

| 方法 | 簽章 |
|--------|-----------|
| `w.secrets.list_scopes()` | `() → Iterator[SecretScope]` |
| `w.secrets.create_scope()` | `(scope, [backend_azure_keyvault, scope_backend_type]) → None` |
| `w.secrets.delete_scope()` | `(scope) → None` |
| `w.secrets.list_secrets()` | `(scope) → Iterator[SecretMetadata]` |
| `w.secrets.get_secret()` | `(scope, key) → GetSecretResponse` |
| `w.secrets.put_secret()` | `(scope, key, [string_value, bytes_value]) → None` |
| `w.secrets.delete_secret()` | `(scope, key) → None` |
| `w.secrets.list_acls()` | `(scope) → Iterator[AclItem]` |
| `w.secrets.get_acl()` | `(scope, principal) → AclItem` |
| `w.secrets.put_acl()` | `(scope, principal, permission) → None` |
| `w.secrets.delete_acl()` | `(scope, principal) → None` |

---

## DBUtils
**文件：** /dbutils.html

```python
# 透過 WorkspaceClient 存取
dbutils = w.dbutils

# 檔案系統
dbutils.fs.ls(path)
dbutils.fs.cp(src, dst, recurse=False)
dbutils.fs.mv(src, dst, recurse=False)
dbutils.fs.rm(path, recurse=False)
dbutils.fs.mkdirs(path)
dbutils.fs.head(path, maxBytes=65536)
dbutils.fs.put(path, contents, overwrite=False)

# Secrets
dbutils.secrets.get(scope, key)
dbutils.secrets.getBytes(scope, key)
dbutils.secrets.list(scope)
dbutils.secrets.listScopes()
```

---

## 帳戶層級 API

若要執行帳戶層級作業，請使用 `AccountClient`：

**文件：** /account/index.html

```python
from databricks.sdk import AccountClient
a = AccountClient(
    host="https://accounts.cloud.databricks.com",
    account_id="your-account-id"
)

# 使用者
a.users.list()
a.users.create(...)
a.users.get(id)

# 工作區
a.workspaces.list()
a.workspaces.create(...)

# 群組
a.groups.list()
a.groups.create(...)
```

| API | 文件 |
|-----|---------------|
| 使用者 | /account/iam/users.html |
| 群組 | /account/iam/groups.html |
| 服務主體（Service Principals） | /account/iam/service_principals.html |
| 工作區 | /account/provisioning/workspaces.html |
| 預算 | /account/billing/budgets.html |
| 使用量 | /account/billing/usage.html |
