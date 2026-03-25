# 認證模式

具優先次序排序的多方法認證策略。

## 基於優先次序的認證

使用回復支援多種認證方法：

```python
class AuthenticatedDataSource(DataSource):
    def __init__(self, options):
        # 優先 1：Databricks Unity Catalog 認證
        self.databricks_credential = options.get("databricks_credential")

        # 優先 2：雲預設認證（受管識別）
        self.default_credential = options.get("default_credential", "false").lower() == "true"

        # 優先 3：服務主體
        self.tenant_id = options.get("tenant_id")
        self.client_id = options.get("client_id")
        self.client_secret = options.get("client_secret")

        # 優先 4：API 金鑰
        self.api_key = options.get("api_key")

        # 優先 5：使用者名稱/密碼
        self.username = options.get("username")
        self.password = options.get("password")

        # 驗證至少設定一種方法
        self._validate_auth()

    def _validate_auth(self):
        """驗證至少設定一種認證方法。"""
        has_databricks_cred = bool(self.databricks_credential)
        has_default_cred = self.default_credential
        has_service_principal = all([self.tenant_id, self.client_id, self.client_secret])
        has_api_key = bool(self.api_key)
        has_basic_auth = bool(self.username and self.password)

        if not any([has_databricks_cred, has_default_cred, has_service_principal,
                    has_api_key, has_basic_auth]):
            raise AssertionError(
                "需要認證。提供以下其中一種："
                "'databricks_credential'、'default_credential=true'、"
                "'tenant_id/client_id/client_secret'、'api_key' 或 'username/password'"
            )
```

## Azure 認證

### Unity Catalog 服務認證

```python
def _get_azure_credential_uc(credential_name):
    """從 Unity Catalog 取得認證。"""
    import databricks.service_credentials

    return databricks.service_credentials.getServiceCredentialsProvider(credential_name)
```

### 預設認證（受管識別）

```python
def _get_azure_credential_default(authority=None):
    """取得受管識別的 DefaultAzureCredential。"""
    from azure.identity import DefaultAzureCredential

    if authority:
        return DefaultAzureCredential(authority=authority)
    return DefaultAzureCredential()
```

### 服務主體

```python
def _get_azure_credential_sp(tenant_id, client_id, client_secret, authority=None):
    """取得服務主體認證。"""
    from azure.identity import ClientSecretCredential

    if authority:
        return ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            authority=authority
        )
    return ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
```

### 多雲支援

```python
def _get_azure_cloud_config(cloud_name):
    """取得雲特定端點和權限。"""
    from azure.identity import AzureAuthorityHosts

    cloud_configs = {
        "public": (None, None),
        "government": (
            AzureAuthorityHosts.AZURE_GOVERNMENT,
            "https://api.loganalytics.us"
        ),
        "china": (
            AzureAuthorityHosts.AZURE_CHINA,
            "https://api.loganalytics.azure.cn"
        ),
    }

    cloud = (cloud_name or "public").lower().strip()

    if cloud not in cloud_configs:
        valid = ", ".join(cloud_configs.keys())
        raise ValueError(f"無效的雲 '{cloud_name}'。有效值：{valid}")

    return cloud_configs[cloud]

def _create_azure_client_with_cloud(options):
    """建立具雲特定組態的 Azure 用戶端。"""
    cloud_name = options.get("azure_cloud", "public")
    authority, endpoint = _get_azure_cloud_config(cloud_name)

    # 根據優先次序取得認證
    credential = _get_credential(options, authority)

    # 使用雲特定端點建立用戶端
    from azure.monitor.query import LogsQueryClient

    if endpoint:
        return LogsQueryClient(credential, endpoint=endpoint)
    return LogsQueryClient(credential)
```

## API 金鑰認證

### 標頭型

```python
def _get_api_key_auth(api_key):
    """取得 API 金鑰認證標頭。"""
    return {"Authorization": f"Bearer {api_key}"}

def _create_session_with_api_key(api_key):
    """使用 API 金鑰建立 requests 工作階段。"""
    import requests

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {api_key}"})
    return session
```

### 查詢參數型

```python
def _build_url_with_api_key(base_url, api_key):
    """新增 API 金鑰作為查詢參數。"""
    from urllib.parse import urlencode

    params = {"api_key": api_key}
    return f"{base_url}?{urlencode(params)}"
```

## 基本認證

```python
def _get_basic_auth(username, password):
    """取得 HTTP 基本驗證。"""
    from requests.auth import HTTPBasicAuth
    return HTTPBasicAuth(username, password)

def _create_session_with_basic_auth(username, password):
    """使用基本驗證建立工作階段。"""
    import requests

    session = requests.Session()
    session.auth = (username, password)
    return session
```

## OAuth2 認證

### 客戶端認證流

```python
def _get_oauth2_token(token_url, client_id, client_secret, scope):
    """使用客戶端認證取得 OAuth2 權杖。"""
    import requests

    response = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope
        }
    )
    response.raise_for_status()

    return response.json()["access_token"]

class OAuth2Writer:
    def __init__(self, options):
        self.token_url = options["token_url"]
        self.client_id = options["client_id"]
        self.client_secret = options["client_secret"]
        self.scope = options.get("scope", "")
        self._token = None
        self._token_expiry = None

    def _get_valid_token(self):
        """取得有效權杖，如過期則重新整理。"""
        from datetime import datetime, timedelta

        if not self._token or datetime.now() >= self._token_expiry:
            self._token = _get_oauth2_token(
                self.token_url,
                self.client_id,
                self.client_secret,
                self.scope
            )
            # 假設未提供時為 1 小時有效期
            self._token_expiry = datetime.now() + timedelta(hours=1)

        return self._token

    def write(self, iterator):
        """使用 OAuth2 認證寫入。"""
        import requests

        token = self._get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}

        for row in iterator:
            requests.post(self.url, json=row.asDict(), headers=headers)
```

## 完整認證工廠

```python
def get_credential(options):
    """
    根據組態優先次序取得認證。

    優先次序：
    1. databricks_credential
    2. default_credential
    3. 服務主體 (tenant_id/client_id/client_secret)
    4. API 金鑰
    5. 使用者名稱/密碼
    """

    # 優先 1：Databricks 認證
    if options.get("databricks_credential"):
        import databricks.service_credentials
        return databricks.service_credentials.getServiceCredentialsProvider(
            options["databricks_credential"]
        )

    # 優先 2：雲預設認證
    if options.get("default_credential", "false").lower() == "true":
        authority = options.get("authority")
        if authority:
            from azure.identity import DefaultAzureCredential
            return DefaultAzureCredential(authority=authority)
        from azure.identity import DefaultAzureCredential
        return DefaultAzureCredential()

    # 優先 3：服務主體
    if all(k in options for k in ["tenant_id", "client_id", "client_secret"]):
        from azure.identity import ClientSecretCredential
        authority = options.get("authority")
        if authority:
            return ClientSecretCredential(
                tenant_id=options["tenant_id"],
                client_id=options["client_id"],
                client_secret=options["client_secret"],
                authority=authority
            )
        return ClientSecretCredential(
            tenant_id=options["tenant_id"],
            client_id=options["client_id"],
            client_secret=options["client_secret"]
        )

    # 優先 4：API 金鑰
    if "api_key" in options:
        return {"Authorization": f"Bearer {options['api_key']}"}

    # 優先 5：基本驗證
    if "username" in options and "password" in options:
        from requests.auth import HTTPBasicAuth
        return HTTPBasicAuth(options["username"], options["password"])

    raise ValueError("未設定有效的認證方法")
```

## 安全最佳實踐

### 永不記錄機密值

```python
class SecureDataSource(DataSource):
    def __init__(self, options):
        self._sensitive_keys = {
            "password", "api_key", "client_secret", "token", "access_token"
        }

        # 儲存實際值
        self.options = options

        # 建立記錄用的清理版本
        self._safe_options = self._sanitize_options(options)

    def _sanitize_options(self, options):
        """遮罩機密值用於記錄。"""
        safe = {}
        for key, value in options.items():
            if key.lower() in self._sensitive_keys:
                safe[key] = "***REDACTED***"
            else:
                safe[key] = value
        return safe

    def __repr__(self):
        return f"SecureDataSource({self._safe_options})"
```

### 使用機密管理

```python
def _load_secrets_from_dbutils(scope, keys):
    """從 Databricks 機密載入機密。"""
    try:
        from pyspark.dbutils import DBUtils
        from pyspark.sql import SparkSession

        spark = SparkSession.getActiveSession()
        dbutils = DBUtils(spark)

        secrets = {}
        for key in keys:
            secrets[key] = dbutils.secrets.get(scope=scope, key=key)

        return secrets

    except Exception as e:
        raise ValueError(f"無法從範圍 '{scope}' 載入機密：{e}")

# 用法
if "secret_scope" in options:
    secrets = _load_secrets_from_dbutils(
        options["secret_scope"],
        ["password", "api_key"]
    )
    options.update(secrets)
```
