# claude-agent-sdk Issue #462 的 Event Loop 修正 ✅ 已解決

## 狀態：✅ **可正常運作 - 可用於正式環境**

本文說明針對 claude-agent-sdk issue #462 所實作的完整修正方案；此方案已成功完成實作與測試。

## 問題

`claude-agent-sdk` 在 FastAPI/uvicorn 情境中存在一個嚴重錯誤（[#462](https://github.com/anthropics/claude-agent-sdk-python/issues/462)），會導致 subprocess transport 失效。常見症狀包括：

1. **只回傳初始化訊息**：SDK 只會回傳最初的 `SystemMessage`，隨後就結束
2. **工具不會執行**：agent 無法使用 MCP tools（例如 Databricks 指令）
3. **subprocess 卡住**：subprocess 已啟動，但 Python 再也收不到後續 stdout

這使得 SDK 在包含 middleware、logging 與其他正式環境常見模式的 FastAPI 部署中幾乎無法使用。

## 根本原因

### 問題 1：Event Loop 汙染
當 `claude-agent-sdk` 在 FastAPI/uvicorn 情境中執行時，現有的 event loop 會干擾 subprocess transport 使用的 `anyio.TextReceiveStream`，導致它無法接收完整的 subprocess 輸出。

### 問題 2：Context Variable 遺失
Python 的 `contextvars`（用於每個請求的 Databricks 認證）**不會自動傳播到新執行緒**。當我們為了全新的 event loop 建立新執行緒時，Databricks auth context 會遺失，進而讓所有 Databricks tool 呼叫失敗。

### 問題 3：空字串與 None
Claude agent 有時會對 `context_id` 之類的選用參數傳入空字串（`""`），而不是 `null` / `None`。Databricks API 會嘗試把空字串解析成數字，造成 `NumberFormatException`。因此 MCP tool wrappers 必須把空字串轉成 `None`。

## 解法

我們實作了三個部分的修正：

### 第 1 部分：在獨立執行緒中使用全新的 Event Loop
在獨立執行緒中，讓 Claude agent 於完全乾淨的 event loop 內執行（位於 `server/services/agent.py`）：

```python
def _run_agent_in_fresh_loop(message, options, result_queue, context):
  """在全新的 event loop 中執行 agent（issue #462 的 workaround）。"""
  def run_with_context():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_query():
      async def prompt_generator():
        yield {'type': 'user', 'message': {'role': 'user', 'content': message}}

      try:
        async for msg in query(prompt=prompt_generator(), options=options):
          result_queue.put(('message', msg))
      except Exception as e:
        result_queue.put(('error', e))
      finally:
        result_queue.put(('done', None))

    try:
      loop.run_until_complete(run_query())
    finally:
      loop.close()

  # 在複製後的 context 中執行
  context.run(run_with_context)
```

### 第 2 部分：傳播 Context
在建立執行緒前先複製 `contextvars` context，以保留 Databricks 認證資訊（位於 `server/services/agent.py`）：

```python
from contextvars import copy_context

# 在 stream_agent_response() 中：
# 為此請求設定 auth context
set_databricks_auth(databricks_host, databricks_token)

try:
  # ... setup options ...

  # 在建立執行緒前先複製 context
  ctx = copy_context()
  result_queue = queue.Queue()

  agent_thread = threading.Thread(
    target=_run_agent_in_fresh_loop,
    args=(message, options, result_queue, ctx),  # 傳入 context
    daemon=True
  )
  agent_thread.start()

  # 從 queue 處理訊息
  while True:
    msg_type, msg = await asyncio.get_event_loop().run_in_executor(
      None, result_queue.get
    )
    if msg_type == 'done':
      break
    elif msg_type == 'error':
      raise msg
    elif msg_type == 'message':
      # 將訊息 yield 給前端...
```

### 第 3 部分：把空字串轉成 None
在 MCP tool wrappers 中，把空字串轉成 `None`（位於 `databricks-mcp-server/databricks_mcp_server/tools/compute.py`）：

```python
@mcp.tool
def execute_databricks_command(
    code: str,
    cluster_id: Optional[str] = None,
    context_id: Optional[str] = None,
    # ... other params
) -> Dict[str, Any]:
    # 將空字串轉成 None（Claude agent 有時會傳入 "" 而不是 null）
    if cluster_id == "":
        cluster_id = None
    if context_id == "":
        context_id = None

    # ... rest of function
```

這樣可避免 Databricks API 在嘗試把空字串解析為數字時觸發 `NumberFormatException`。

## 運作方式

1. **主執行緒（FastAPI）**：執行 FastAPI/uvicorn 的 event loop
2. **Agent 執行緒**：為 Claude agent 建立全新且隔離的 event loop
3. **Context 複製**：把 `contextvars` context（包含 Databricks auth）複製到新執行緒
4. **Queue 通訊**：使用 thread-safe queue 把訊息傳回主執行緒
5. **非同步橋接**：主執行緒使用 `run_in_executor` 非同步讀取 queue

## 優點

✅ **修復 subprocess transport**：全新 event loop 可將 agent 與 FastAPI 的 event loop 隔離
✅ **保留認證資訊**：透過複製 context，把 Databricks 憑證傳到新執行緒
✅ **維持串流能力**：以 queue 為基礎的通訊可以正確串流所有訊息
✅ **可用於正式環境**：可搭配 middleware、logging、Sentry 與其他 FastAPI 模式運作
✅ **MCP tools 可正常執行**：Databricks 指令與其他 MCP tools 都能成功執行

## 測試方式

若要驗證修正是否生效：

1. 啟動開發伺服器：`bash scripts/start_dev.sh`
2. 在瀏覽器開啟應用程式：http://localhost:3000
3. 請 agent 執行 Databricks 指令
4. 確認工具有成功執行（檢查日誌中是否出現成功的 Databricks API 呼叫）

## 參考資料

- 原始 Issue：https://github.com/anthropics/claude-agent-sdk-python/issues/462
- Python contextvars：https://docs.python.org/3/library/contextvars.html
- Threading and contextvars：https://peps.python.org/pep-0567/#implementation-notes
