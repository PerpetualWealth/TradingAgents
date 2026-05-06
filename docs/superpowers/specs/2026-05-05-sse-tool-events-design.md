# SSE Tool 事件增强设计文档

## 概述

在现有 SSE API 基础上增加 Tool 级别的原子事件（`tool_call`、`tool_result`），让前端能实时看到分析过程中获取了哪些原始数据。重构 mockdata 为统一的原始事件流格式，确保 mock 和真实分析走同一段 SSE 加工逻辑。

## 设计原则

1. **分析优先，监控次要** — 不改变 `tradingagents/` 核心代码，不改变分析执行流程
2. **mockdata 存原始，SSE 做加工** — mockdata 是 TradingAgents 原始事件的快照，所有展示逻辑只在 `sse.py` 一处
3. **只使用确定可靠的信号源** — `graph.stream()` 和 `BaseCallbackHandler`，不使用需要反推或双流合并的方案

## 原始事件流格式

mockdata.json 是一个数组，每个元素通过 `event_type` 区分类型：

### graph_chunk

来源：`graph.stream(stream_mode="values")` 每次迭代。完整 AgentState 快照。

```json
{
  "event_type": "graph_chunk",
  "data": {
    "messages": [],
    "company_of_interest": "NVDA",
    "trade_date": "2026-05-05",
    "market_report": "",
    "sentiment_report": "",
    "news_report": "",
    "fundamentals_report": "",
    "investment_debate_state": {
      "bull_history": "",
      "bear_history": "",
      "history": "",
      "current_response": "",
      "judge_decision": "",
      "count": 0
    },
    "risk_debate_state": {
      "aggressive_history": "",
      "conservative_history": "",
      "neutral_history": "",
      "history": "",
      "latest_speaker": "",
      "current_aggressive_response": "",
      "current_conservative_response": "",
      "current_neutral_response": "",
      "judge_decision": "",
      "count": 0
    },
    "trader_investment_plan": "",
    "final_trade_decision": "",
    "past_context": ""
  }
}
```

### tool_start

来源：`BaseCallbackHandler.on_tool_start()`。Tool 开始调用。

```json
{
  "event_type": "tool_start",
  "tool": "get_stock_data",
  "input": {"ticker": "NVDA"}
}
```

### tool_result

来源：`BaseCallbackHandler.on_tool_end()`。Tool 返回数据，全量存储。

```json
{
  "event_type": "tool_result",
  "tool": "get_stock_data",
  "output": "Date,Open,High,Low,Close,Volume\n2026-04-01,188.5,192.3,..."
}
```

## 8 种 Tool

| Tool | 归属 Analyst | 获取内容 |
|------|-------------|---------|
| `get_stock_data` | Market | K线价格数据 |
| `get_indicators` | Market | 技术指标（MACD、RSI、布林带等） |
| `get_news` | Social / News | 新闻列表 |
| `get_global_news` | News | 全球新闻 |
| `get_insider_transactions` | News | 内部人交易 |
| `get_fundamentals` | Fundamentals | 基本面数据 |
| `get_balance_sheet` | Fundamentals | 资产负债表 |
| `get_cashflow` | Fundamentals | 现金流量表 |
| `get_income_statement` | Fundamentals | 利润表 |

## SSE 事件映射

`sse.py` 中的 `process_raw_event()` 统一处理所有原始事件。

### 原始事件 → SSE 事件映射表

| 原始事件 | 条件 | SSE 事件 |
|---------|------|---------|
| `graph_chunk`（首个） | — | `analysis_start` |
| `graph_chunk` | report 字段从空变非空 | `agent_complete` |
| `graph_chunk` | `investment_debate_state.judge_decision` 从空变非空 | `debate_update` (investment) |
| `graph_chunk` | `risk_debate_state.judge_decision` 从空变非空 | `debate_update` (risk) |
| `graph_chunk` | `final_trade_decision` 从空变非空 | `analysis_complete` |
| `tool_start` | — | `tool_call` |
| `tool_result` | — | `tool_result` |

### SSE 事件格式

所有 SSE 事件都包含通用信封：

```json
{
  "event_id": "uuid",
  "timestamp": "ISO8601",
  "ticker": "NVDA",
  "type": "事件类型",
  ...
}
```

各类型字段：

**tool_call**
```json
{
  "type": "tool_call",
  "tool": "get_stock_data",
  "input": {"ticker": "NVDA"}
}
```

**tool_result**
```json
{
  "type": "tool_result",
  "tool": "get_stock_data",
  "output": "原始数据..."
}
```

**analysis_start / agent_complete / debate_update / analysis_complete** — 保持现有格式不变。

### 完整 SSE 事件序列示例

```
event: analysis_start
data: {"type":"analysis_start","ticker":"NVDA","date":"2026-05-05",...}

event: tool_call
data: {"type":"tool_call","tool":"get_stock_data","input":{"ticker":"NVDA"},...}

event: tool_result
data: {"type":"tool_result","tool":"get_stock_data","output":"Date,Open,...",...}

event: tool_call
data: {"type":"tool_call","tool":"get_indicators","input":{"ticker":"NVDA"},...}

event: tool_result
data: {"type":"tool_result","tool":"get_indicators","output":"MACD:-0.88,...",...}

event: agent_complete
data: {"type":"agent_complete","agent":"Market Analyst","report_field":"market_report","content":"...",...}

event: tool_call
data: {"type":"tool_call","tool":"get_news","input":{"ticker":"NVDA"},...}

event: tool_result
data: {"type":"tool_result","tool":"get_news","output":"新闻列表...",...}

event: agent_complete
data: {"type":"agent_complete","agent":"Social Analyst",...}

event: agent_complete
data: {"type":"agent_complete","agent":"News Analyst",...}

event: agent_complete
data: {"type":"agent_complete","agent":"Fundamentals Analyst",...}

event: debate_update
data: {"type":"debate_update","debate_type":"investment","bull_history":"...","bear_history":"...","judge_decision":"...",...}

event: agent_complete
data: {"type":"agent_complete","agent":"Trader",...}

event: debate_update
data: {"type":"debate_update","debate_type":"risk","aggressive_history":"...","conservative_history":"...","neutral_history":"...","judge_decision":"...",...}

event: analysis_complete
data: {"type":"analysis_complete","decision":"OVERWEIGHT","raw_decision":"...",...}
```

## 数据流架构

### mock 路径

```
mockdata.json → 逐个原始事件 → process_raw_event() → SSE event
```

### 真实路径

```
graph.stream() ──→ graph_chunk 事件 ──┐
                                      ├→ process_raw_event() → SSE event
BaseCallbackHandler → tool 事件 ──────┘
```

两个路径在 `process_raw_event()` 汇合，所有加工逻辑只在此函数中。

## 事件收集机制（真实路径）

### graph_chunk

来自 `graph.graph.stream(init_state, **args)`，主线程同步迭代。每次迭代产出一个 `graph_chunk` 事件。

### tool_start / tool_result

来自自定义 `RecordingCallback(BaseCallbackHandler)`，通过 `TradingAgentsGraph` 构造器的 `callbacks` 参数注入。

```python
class RecordingCallback(BaseCallbackHandler):
    def __init__(self, event_queue, loop):
        self.event_queue = event_queue
        self.loop = loop

    def on_tool_start(self, serialized, input_str, **kwargs):
        event = {"event_type": "tool_start", "tool": serialized.get("name", ""), "input": input_str}
        self.loop.call_soon_threadsafe(self.event_queue.put_nowait, event)

    def on_tool_end(self, output, **kwargs):
        event = {"event_type": "tool_result", "tool": self._current_tool, "output": str(output)}
        self.loop.call_soon_threadsafe(self.event_queue.put_nowait, event)
```

通过 `loop.call_soon_threadsafe()` 从 callback 线程安全地写入 `asyncio.Queue`。

### 不做的事

- **不使用** `stream_mode="updates"`（需要双流合并）
- **不反推** 节点名（不稳定）
- **不使用** `on_llm_start` / `on_llm_end`（纯技术事件，无业务价值）

## 涉及文件

| 文件 | 改动 | 说明 |
|------|------|------|
| `api/mockdata.json` | 备份现有 → 重新录制 | 新格式：统一事件流 |
| `api/record_chunks.py` | 重写 | 新增 RecordingCallback，产出新格式 |
| `api/sse.py` | 重构 | 新增 process_raw_event()，mock 和真实统一 |
| `api/server.py` | 不改 | — |
| `api/mcp_tool.py` | 不改 | — |
| `api/models.py` | 不改 | — |
| `api/deps.py` | 不改 | — |
| `tradingagents/` | 不改 | — |

## mockdata 管理

- 现有 mockdata.json 备份为 `api/mockdata.json.bak`
- 用 `record_chunks.py` 重新录制 NVDA 分析
- 录制脚本基于现有 `start/main.py` 的配置模式
