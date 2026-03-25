# MLflow 3 Trace 分析模式

跨 Agent 架構分析 MLflow trace 的實用程式碼模式。

## 何時使用 MCP vs Python SDK

| 使用情境 | 建議方式 |
|---------|---------|
| 互動式 trace 探索 | **MLflow MCP Server**——快速搜尋、欄位提取 |
| Agent 驅動的分析 | **MLflow MCP Server**——子 agent 搜尋並標記 trace |
| 產生評估腳本 | **MLflow Python SDK**——產生可執行的 Python 程式碼 |
| 自訂分析管道 | **MLflow Python SDK**——完整控制、複雜聚合 |
| 從 trace 建立 dataset | **MLflow Python SDK**——將 trace 轉換為評估格式 |
| CI/CD 整合 | **MLflow Python SDK**——獨立腳本 |

### MLflow MCP Server（供 Agent 使用）

最適合互動式探索與 Agent 驅動的 trace 分析：
- `search_traces` — 以 `extract_fields` 篩選與搜尋
- `get_trace` — 以選擇性欄位提取深入分析
- `set_trace_tag` — 標記 trace 供後續建立 dataset 使用
- `log_feedback` — 將分析發現持久化儲存
- `log_expectation` — 儲存基準答案供評估使用

### MLflow Python SDK（供產生程式碼使用）

最適合產生可執行的評估腳本：
- `mlflow.search_traces()` — 程式化 trace 存取
- `mlflow.genai.evaluate()` — 執行評估
- `MlflowClient()` — 完整 API 存取
- DataFrame 操作 — 複雜聚合與分析

---

## 目錄

| # | 模式 | 說明 |
|---|------|------|
| 1 | [取得 Trace](#pattern-1-從-mlflow-取得-trace) | 從 experiment 取得 trace |
| 2 | [取得單一 Trace](#pattern-2-依-id-取得單一-trace) | 依 ID 取得特定 trace |
| 3 | [Span 階層](#pattern-3-span-階層分析) | 分析親子結構 |
| 4 | [依 Span 類型分析延遲](#pattern-4-依-span-類型分析延遲) | LLM、TOOL、RETRIEVER 延遲細分 |
| 5 | [依元件分析延遲](#pattern-5-依元件名稱分析延遲) | 各階段／元件的時間分析 |
| 6 | [瓶頸偵測](#pattern-6-瓶頸偵測) | 找出最慢的元件 |
| 7 | [錯誤偵測](#pattern-7-錯誤模式偵測) | 找出並分類錯誤 |
| 8 | [工具呼叫分析](#pattern-8-工具呼叫分析) | 分析工具／函式呼叫 |
| 9 | [LLM 呼叫分析](#pattern-9-llm-呼叫分析) | Token 使用量與延遲 |
| 10 | [Trace 比較](#pattern-10-trace-比較) | 比較多個 trace |
| 11 | [Trace 報告](#pattern-11-產生-trace-分析報告) | 產生完整報告 |
| 12 | [MCP Server 使用](#pattern-12-使用-mlflow-mcp-server-進行-trace-分析) | 透過 MCP 快速查詢 trace |
| 13 | [架構偵測](#pattern-13-架構偵測) | 自動偵測 agent 類型 |
| 14 | [透過 MCP 使用 Assessment](#pattern-14-使用-assessment-進行持久化分析) | 在 MLflow 中儲存分析發現 |

---

## Pattern 1: 從 MLflow 取得 Trace

從 experiment 取得 trace 進行分析。

```python
import mlflow
from mlflow import MlflowClient

client = MlflowClient()

# 依 experiment ID 取得 trace
traces = client.search_traces(
    experiment_ids=["your_experiment_id"],
    max_results=100
)

# 依 experiment 名稱取得 trace
experiment = mlflow.get_experiment_by_name("/Users/user@domain.com/my-experiment")
traces = client.search_traces(
    experiment_ids=[experiment.experiment_id],
    max_results=50
)

# 依時間範圍篩選 trace
from datetime import datetime, timedelta
yesterday = int((datetime.now() - timedelta(days=1)).timestamp() * 1000)
traces = client.search_traces(
    experiment_ids=["your_experiment_id"],
    filter_string=f"timestamp_ms > {yesterday}"
)
```

---

## Pattern 2: 依 ID 取得單一 Trace

取得特定 trace 進行詳細分析。

```python
from mlflow import MlflowClient

client = MlflowClient()

# 依 ID 取得 trace
trace = client.get_trace(trace_id="tr-abc123def456")

# 存取 trace 資訊
print(f"Trace ID: {trace.info.trace_id}")
print(f"狀態：{trace.info.status}")
print(f"執行時間：{trace.info.execution_time_ms}ms")

# 存取 trace 資料（span）
spans = trace.data.spans
print(f"Span 總數：{len(spans)}")
```

---

## Pattern 3: Span 階層分析

分析 trace 中 span 的階層結構。

```python
from mlflow.entities import Trace
from typing import Dict, List, Any

def analyze_span_hierarchy(trace: Trace) -> Dict[str, Any]:
    """分析 span 階層與結構。

    適用於任何 agent 架構（DSPy、LangGraph 等）。
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    # 建立親子關係
    span_by_id = {s.span_id: s for s in spans}
    children = {}
    root_spans = []

    for span in spans:
        if span.parent_id is None:
            root_spans.append(span)
        else:
            if span.parent_id not in children:
                children[span.parent_id] = []
            children[span.parent_id].append(span)

    def build_tree(span, depth=0):
        """遞迴建立 span 樹狀結構。"""
        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6
        node = {
            "name": span.name,
            "span_type": str(span.span_type) if span.span_type else "UNKNOWN",
            "duration_ms": round(duration_ms, 2),
            "depth": depth,
            "children": []
        }
        for child in children.get(span.span_id, []):
            node["children"].append(build_tree(child, depth + 1))
        return node

    return {
        "root_count": len(root_spans),
        "total_spans": len(spans),
        "hierarchy": [build_tree(root) for root in root_spans]
    }

# 使用方式
hierarchy = analyze_span_hierarchy(trace)
print(f"根 span 數：{hierarchy['root_count']}")
print(f"Span 總數：{hierarchy['total_spans']}")
```

---

## Pattern 4: 依 Span 類型分析延遲

分析各 span 類型的延遲分佈。

```python
from mlflow.entities import Trace, SpanType
from typing import Dict, List
from collections import defaultdict

def latency_by_span_type(trace: Trace) -> Dict[str, Dict]:
    """依 span 類型細分延遲。

    回傳各 span 類型（LLM、TOOL、RETRIEVER 等）的延遲統計。
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    type_latencies = defaultdict(list)

    for span in spans:
        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6
        span_type = str(span.span_type) if span.span_type else "UNKNOWN"
        type_latencies[span_type].append({
            "name": span.name,
            "duration_ms": duration_ms
        })

    results = {}
    for span_type, items in type_latencies.items():
        durations = [i["duration_ms"] for i in items]
        results[span_type] = {
            "count": len(items),
            "total_ms": round(sum(durations), 2),
            "avg_ms": round(sum(durations) / len(durations), 2),
            "max_ms": round(max(durations), 2),
            "min_ms": round(min(durations), 2),
            "spans": items
        }

    return results

# 使用方式
latency_stats = latency_by_span_type(trace)
for span_type, stats in sorted(latency_stats.items(), key=lambda x: -x[1]["total_ms"]):
    print(f"{span_type}: {stats['total_ms']}ms 合計（{stats['count']} 個 span）")
```

---

## Pattern 5: 依元件名稱分析延遲

依元件／階段名稱分析延遲（架構無關）。

```python
from mlflow.entities import Trace
from typing import Dict, List
from collections import defaultdict

def latency_by_component(
    trace: Trace,
    component_patterns: List[str] = None
) -> Dict[str, Dict]:
    """依元件名稱模式細分延遲。

    Args:
        trace: 要分析的 MLflow trace
        component_patterns: 選填，要比對的模式清單。
                           若為 None，則提取所有唯一的 span 名稱。

    適用於任何架構——DSPy 階段、LangGraph 節點等。
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    component_latencies = defaultdict(list)

    for span in spans:
        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6
        span_name = span.name.lower()

        if component_patterns:
            # 與模式比對
            for pattern in component_patterns:
                if pattern.lower() in span_name:
                    component_latencies[pattern].append({
                        "span_name": span.name,
                        "duration_ms": duration_ms
                    })
                    break
        else:
            # 直接使用 span 名稱
            component_latencies[span.name].append({
                "duration_ms": duration_ms
            })

    results = {}
    for component, items in component_latencies.items():
        durations = [i["duration_ms"] for i in items]
        results[component] = {
            "count": len(items),
            "total_ms": round(sum(durations), 2),
            "avg_ms": round(sum(durations) / len(durations), 2) if durations else 0,
            "max_ms": round(max(durations), 2) if durations else 0,
        }

    return results

# 使用方式——DSPy 多 agent
dspy_components = ["classifier", "rewriter", "gatherer", "executor"]
stats = latency_by_component(trace, dspy_components)

# 使用方式——LangGraph
langgraph_components = ["planner", "executor", "tool_call", "compress"]
stats = latency_by_component(trace, langgraph_components)

# 使用方式——自動偵測所有元件
stats = latency_by_component(trace)
```

---

## Pattern 6: 瓶頸偵測

找出 trace 中最慢的元件。

```python
from mlflow.entities import Trace
from typing import Dict, List, Tuple

def find_bottlenecks(
    trace: Trace,
    top_n: int = 5,
    exclude_patterns: List[str] = None
) -> List[Dict]:
    """找出 trace 中最慢的 span。

    Args:
        trace: 要分析的 MLflow trace
        top_n: 要回傳的最慢 span 數量
        exclude_patterns: 要排除的 span 名稱模式（例如包裝用的 span）

    回傳含時間資訊的最慢 span 清單。
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()
    exclude_patterns = exclude_patterns or ["forward", "predict", "root"]

    span_timings = []
    for span in spans:
        # 跳過符合排除模式的 span
        span_name_lower = span.name.lower()
        if any(p in span_name_lower for p in exclude_patterns):
            continue

        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6
        span_timings.append({
            "name": span.name,
            "span_type": str(span.span_type) if span.span_type else "UNKNOWN",
            "duration_ms": round(duration_ms, 2),
            "span_id": span.span_id
        })

    # 依延遲由高到低排序
    span_timings.sort(key=lambda x: -x["duration_ms"])

    return span_timings[:top_n]

# 使用方式
bottlenecks = find_bottlenecks(trace, top_n=5)
print("前 5 個最慢的 Span：")
for i, b in enumerate(bottlenecks, 1):
    print(f"  {i}. {b['name']}（{b['span_type']}）：{b['duration_ms']}ms")
```

---

## Pattern 7: 錯誤模式偵測

找出並分析 trace 中的錯誤模式。

```python
from mlflow.entities import Trace, SpanStatusCode
from typing import Dict, List

def detect_errors(trace: Trace) -> Dict[str, List]:
    """偵測 trace 中的錯誤模式。

    回傳分類後的錯誤及其 context。
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    errors = {
        "failed_spans": [],
        "exceptions": [],
        "empty_outputs": [],
        "warnings": []
    }

    for span in spans:
        # 檢查 span 狀態
        if span.status and span.status.status_code == SpanStatusCode.ERROR:
            errors["failed_spans"].append({
                "name": span.name,
                "span_type": str(span.span_type),
                "error_message": span.status.description if span.status.description else "未知錯誤"
            })

        # 檢查 event 中的例外
        if span.events:
            for event in span.events:
                if "exception" in event.name.lower():
                    errors["exceptions"].append({
                        "span_name": span.name,
                        "event": event.name,
                        "attributes": event.attributes
                    })

        # 檢查空輸出（潛在問題）
        if span.outputs is None or span.outputs == {} or span.outputs == []:
            errors["empty_outputs"].append({
                "name": span.name,
                "span_type": str(span.span_type)
            })

    return errors

# 使用方式
errors = detect_errors(trace)
if errors["failed_spans"]:
    print(f"找到 {len(errors['failed_spans'])} 個失敗的 span")
    for e in errors["failed_spans"]:
        print(f"  - {e['name']}: {e['error_message']}")
```

---

## Pattern 8: 工具呼叫分析

分析 trace 中的工具／函式呼叫。

```python
from mlflow.entities import Trace, SpanType
from typing import Dict, List

def analyze_tool_calls(trace: Trace) -> Dict[str, Any]:
    """分析 trace 中的工具呼叫。

    適用於 UC functions、LangChain tools 或任何 TOOL span 類型。
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    # 找出 tool span
    tool_spans = [s for s in spans if s.span_type == SpanType.TOOL]

    tool_calls = []
    for span in tool_spans:
        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6

        # 提取工具名稱（處理完整限定名稱）
        tool_name = span.name
        if "." in tool_name:
            tool_name_short = tool_name.split(".")[-1]
        else:
            tool_name_short = tool_name

        tool_calls.append({
            "tool_name": tool_name_short,
            "full_name": span.name,
            "duration_ms": round(duration_ms, 2),
            "inputs": span.inputs,
            "outputs_preview": str(span.outputs)[:200] if span.outputs else None,
            "success": span.status.status_code != SpanStatusCode.ERROR if span.status else True
        })

    # 彙總統計
    tool_stats = {}
    for tc in tool_calls:
        name = tc["tool_name"]
        if name not in tool_stats:
            tool_stats[name] = {"count": 0, "total_ms": 0, "successes": 0}
        tool_stats[name]["count"] += 1
        tool_stats[name]["total_ms"] += tc["duration_ms"]
        if tc["success"]:
            tool_stats[name]["successes"] += 1

    return {
        "total_tool_calls": len(tool_calls),
        "unique_tools": len(tool_stats),
        "calls": tool_calls,
        "stats": tool_stats
    }

# 使用方式
tool_analysis = analyze_tool_calls(trace)
print(f"工具呼叫總次數：{tool_analysis['total_tool_calls']}")
for tool, stats in tool_analysis['stats'].items():
    print(f"  {tool}: {stats['count']} 次呼叫，合計 {stats['total_ms']}ms")
```

---

## Pattern 9: LLM 呼叫分析

分析 trace 中的 LLM 呼叫。

```python
from mlflow.entities import Trace, SpanType
from typing import Dict, List, Any

def analyze_llm_calls(trace: Trace) -> Dict[str, Any]:
    """分析 trace 中的 LLM 呼叫。

    提取模型資訊、Token 使用量及延遲。
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

    # 找出 LLM/CHAT_MODEL span
    llm_spans = [s for s in spans
                 if s.span_type in [SpanType.LLM, SpanType.CHAT_MODEL]]

    llm_calls = []
    for span in llm_spans:
        duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6

        # 從 attributes 提取 token 資訊
        attributes = span.attributes or {}

        llm_calls.append({
            "name": span.name,
            "duration_ms": round(duration_ms, 2),
            "model": attributes.get("mlflow.chat_model.model") or attributes.get("llm.model_name"),
            "input_tokens": attributes.get("mlflow.chat_model.input_tokens"),
            "output_tokens": attributes.get("mlflow.chat_model.output_tokens"),
            "total_tokens": attributes.get("mlflow.chat_model.total_tokens"),
        })

    # 計算總計
    total_input = sum(c["input_tokens"] or 0 for c in llm_calls)
    total_output = sum(c["output_tokens"] or 0 for c in llm_calls)
    total_latency = sum(c["duration_ms"] for c in llm_calls)

    return {
        "total_llm_calls": len(llm_calls),
        "total_latency_ms": round(total_latency, 2),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "calls": llm_calls
    }

# 使用方式
llm_analysis = analyze_llm_calls(trace)
print(f"LLM 呼叫次數：{llm_analysis['total_llm_calls']}")
print(f"Token 總計：{llm_analysis['total_input_tokens']} 輸入 / {llm_analysis['total_output_tokens']} 輸出")
print(f"LLM 延遲：{llm_analysis['total_latency_ms']}ms")
```

---

## Pattern 10: Trace 比較

比較多個 trace 以識別規律。

```python
from mlflow.entities import Trace
from typing import List, Dict, Any

def compare_traces(traces: List[Trace]) -> Dict[str, Any]:
    """比較多個 trace 以識別規律。

    適用於前後對比或批次分析。
    """
    trace_stats = []

    for trace in traces:
        spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()

        # 取根 span 計算總時間
        root_spans = [s for s in spans if s.parent_id is None]
        total_ms = 0
        if root_spans:
            root = root_spans[0]
            total_ms = (root.end_time_ns - root.start_time_ns) / 1e6

        trace_stats.append({
            "trace_id": trace.info.trace_id,
            "total_ms": round(total_ms, 2),
            "span_count": len(spans),
            "status": str(trace.info.status)
        })

    # 計算彙總指標
    latencies = [t["total_ms"] for t in trace_stats]

    return {
        "trace_count": len(traces),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "min_latency_ms": round(min(latencies), 2) if latencies else 0,
        "max_latency_ms": round(max(latencies), 2) if latencies else 0,
        "p50_latency_ms": round(sorted(latencies)[len(latencies)//2], 2) if latencies else 0,
        "success_rate": sum(1 for t in trace_stats if "OK" in t["status"]) / len(trace_stats) if trace_stats else 0,
        "traces": trace_stats
    }

# 使用方式
comparison = compare_traces(traces)
print(f"分析了 {comparison['trace_count']} 個 trace")
print(f"平均延遲：{comparison['avg_latency_ms']}ms")
print(f"成功率：{comparison['success_rate']:.1%}")
```

---

## Pattern 11: 產生 Trace 分析報告

將多種分析模式組合成完整的報告。

```python
from mlflow.entities import Trace
from typing import Dict, Any

def generate_trace_report(trace: Trace) -> Dict[str, Any]:
    """產生完整的 trace 分析報告。

    整合階層、延遲、錯誤及瓶頸分析。
    """
    # 引入上述分析函式
    hierarchy = analyze_span_hierarchy(trace)
    latency_by_type = latency_by_span_type(trace)
    bottlenecks = find_bottlenecks(trace, top_n=3)
    errors = detect_errors(trace)
    tool_analysis = analyze_tool_calls(trace)
    llm_analysis = analyze_llm_calls(trace)

    # 取根 span 資訊
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()
    root_spans = [s for s in spans if s.parent_id is None]
    total_ms = 0
    if root_spans:
        root = root_spans[0]
        total_ms = (root.end_time_ns - root.start_time_ns) / 1e6

    return {
        "summary": {
            "trace_id": trace.info.trace_id,
            "status": str(trace.info.status),
            "total_duration_ms": round(total_ms, 2),
            "total_spans": len(spans),
        },
        "hierarchy": hierarchy,
        "latency_by_type": latency_by_type,
        "bottlenecks": bottlenecks,
        "errors": errors,
        "tool_calls": tool_analysis,
        "llm_calls": llm_analysis,
        "recommendations": generate_recommendations(
            bottlenecks, errors, llm_analysis, total_ms
        )
    }

def generate_recommendations(
    bottlenecks: List[Dict],
    errors: Dict,
    llm_analysis: Dict,
    total_ms: float
) -> List[str]:
    """從分析結果產生可行動的改善建議。"""
    recommendations = []

    # 延遲建議
    if bottlenecks and bottlenecks[0]["duration_ms"] > total_ms * 0.5:
        b = bottlenecks[0]
        recommendations.append(
            f"瓶頸：'{b['name']}' 佔總時間的 {b['duration_ms']/total_ms*100:.0f}%。"
            f"建議優化此元件。"
        )

    # LLM 呼叫建議
    if llm_analysis["total_llm_calls"] > 5:
        recommendations.append(
            f"LLM 呼叫次數過多：偵測到 {llm_analysis['total_llm_calls']} 次 LLM 呼叫。"
            f"考慮批次處理或減少呼叫次數。"
        )

    # 錯誤建議
    if errors["failed_spans"]:
        recommendations.append(
            f"錯誤：偵測到 {len(errors['failed_spans'])} 個失敗的 span。"
            f"請檢查：{[e['name'] for e in errors['failed_spans'][:3]]}"
        )

    if not recommendations:
        recommendations.append("未偵測到主要問題。Trace 狀態良好。")

    return recommendations

# 使用方式
report = generate_trace_report(trace)
print(f"Trace {report['summary']['trace_id']}")
print(f"執行時間：{report['summary']['total_duration_ms']}ms")
print(f"Span 數：{report['summary']['total_spans']}")
print("\n改善建議：")
for rec in report['recommendations']:
    print(f"  - {rec}")
```

---

## Pattern 12: 使用 MLflow MCP Server 進行 Trace 分析

使用 MLflow MCP server 快速查詢 trace。

```python
# 透過 Claude Code，使用 MCP server 工具：

# 在 experiment 中搜尋 trace
mcp__mlflow-mcp__search_traces(
    experiment_id="your_experiment_id",
    max_results=10,
    output="table"
)

# 取得詳細 trace 資訊
mcp__mlflow-mcp__get_trace(
    trace_id="tr-abc123",
    extract_fields="info.trace_id,info.status,data.spans.*.name"
)

# 依狀態篩選
mcp__mlflow-mcp__search_traces(
    experiment_id="123",
    filter_string="status = 'OK'",
    max_results=20
)
```

---

## Pattern 13: 架構偵測

從 trace 結構自動偵測 agent 架構。

```python
from mlflow.entities import Trace, SpanType
from typing import Dict, Any

def detect_architecture(trace: Trace) -> Dict[str, Any]:
    """從 trace 模式偵測 agent 架構。

    回傳架構類型與關鍵特徵。
    """
    spans = trace.data.spans if hasattr(trace, 'data') else trace.search_spans()
    span_names = [s.name.lower() for s in spans]
    span_types = [s.span_type for s in spans]

    # 架構指示器
    indicators = {
        "dspy_multi_agent": any(
            p in " ".join(span_names)
            for p in ["classifier", "rewriter", "gatherer", "executor"]
        ),
        "langgraph": any(
            p in " ".join(span_names)
            for p in ["langgraph", "graph", "node", "state"]
        ),
        "rag": SpanType.RETRIEVER in span_types,
        "tool_calling": SpanType.TOOL in span_types,
        "simple_chat": len(set(span_types)) <= 2 and SpanType.CHAT_MODEL in span_types,
    }

    # 判斷主要架構
    if indicators["dspy_multi_agent"]:
        arch_type = "dspy_multi_agent"
    elif indicators["langgraph"]:
        arch_type = "langgraph"
    elif indicators["rag"] and indicators["tool_calling"]:
        arch_type = "rag_with_tools"
    elif indicators["rag"]:
        arch_type = "rag"
    elif indicators["tool_calling"]:
        arch_type = "tool_calling"
    else:
        arch_type = "simple_chat"

    return {
        "architecture": arch_type,
        "indicators": indicators,
        "span_type_distribution": {
            str(st): sum(1 for s in spans if s.span_type == st)
            for st in set(span_types)
        }
    }

# 使用方式
arch = detect_architecture(trace)
print(f"偵測到的架構：{arch['architecture']}")
print(f"Span 類型分佈：{arch['span_type_distribution']}")
```

---

## 最佳實踐

### 1. 永遠處理缺少的資料
```python
# Trace 可能含有不完整的資料
spans = trace.data.spans if hasattr(trace, 'data') else []
duration = (span.end_time_ns - span.start_time_ns) / 1e6 if span.end_time_ns else 0
```

### 2. 正規化 Span 名稱
```python
# 處理完整限定名稱（UC functions 等）
def normalize_name(name: str) -> str:
    return name.split(".")[-1] if "." in name else name
```

### 3. 使用適當的篩選條件
```python
# 排除包裝用的 span，以取得準確的瓶頸偵測結果
exclude = ["forward", "predict", "__init__", "root"]
```

### 4. 快取耗費資源的分析
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_trace_analysis(trace_id: str):
    trace = client.get_trace(trace_id)
    return generate_trace_report(trace)
```

---

## Pattern 14: 使用 Assessment 進行持久化分析

將分析發現直接儲存至 MLflow 供後續使用。Agent 工作階段中使用 MCP 工具。

### 記錄分析 Feedback（透過 MCP）

```
# 在 agent 分析過程中儲存發現
mcp__mlflow-mcp__log_feedback(
    trace_id="tr-abc123",
    name="bottleneck_detected",
    value="retriever",
    source_type="CODE",
    rationale="Retriever span accounts for 65% of total latency"
)
```

### 記錄預期行為／基準答案（透過 MCP）

```
# 當您知道正確輸出應該是什麼時
mcp__mlflow-mcp__log_expectation(
    trace_id="tr-abc123",
    name="expected_output",
    value='{"status": "success", "answer": "The quarterly revenue was $2.3M"}'
)
```

### 取得 Assessment（透過 MCP）

```
mcp__mlflow-mcp__get_assessment(
    trace_id="tr-abc123",
    assessment_id="bottleneck_detected"
)
```

### 搜尋已標記的 Trace 以建立 Dataset（透過 MCP）

分析過程中標記 trace 後，可在之後搜尋：

```
# 找出所有標記為評估候選的 trace
mcp__mlflow-mcp__search_traces(
    experiment_id="123",
    filter_string="tags.eval_candidate = 'error_case'",
    extract_fields="info.trace_id,data.request,data.response"
)
```

### 將已標記的 Trace 轉換為 Dataset（Python SDK）

產生評估程式碼時，使用 Python SDK 建立 dataset：

```python
import mlflow

# 搜尋已標記的 trace
traces = mlflow.search_traces(
    filter_string="tags.eval_candidate = 'error_case'",
    max_results=100
)

# 轉換為評估 dataset 格式
eval_data = []
for _, trace in traces.iterrows():
    eval_data.append({
        "inputs": trace["request"],
        "outputs": trace["response"],
        "metadata": {"source_trace": trace["trace_id"]}
    })

# 用於評估
results = mlflow.genai.evaluate(
    data=eval_data,
    scorers=[...]
)
```
