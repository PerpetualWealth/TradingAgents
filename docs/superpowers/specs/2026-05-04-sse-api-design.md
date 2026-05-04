# SSE API + MCP Tool 设计文档

## 概述

在 `api/` 目录下新增 FastAPI 服务层，将 TradingAgents 的股票分析能力以 SSE API 和 MCP Tool 两种形式暴露。不修改 `tradingagents/` 核心代码。

## 需求摘要

- **SSE API**：客户端发起分析请求，通过 SSE 实时接收分析进度事件（每个 Agent 完成时推送），最终收到决策结果
- **MCP Tool**：同步调用，只返回最终分析决策，供 AI 编程助手使用
- **多任务并发**：支持多个 ticker 同时分析，每个请求独立 SSE 流
- **零侵入**：不改动现有 `tradingagents/` 代码，仅新增 `api/` 目录

## 目录结构

```
api/
├── __init__.py          # 空
├── server.py            # FastAPI app, 路由定义, 启动入口
├── sse.py               # SSE 事件生成器：chunk → SSE event 映射
├── mcp_tool.py          # MCP Server（stdio transport），暴露 analyze_stock tool
├── deps.py              # 共享依赖：TradingAgentsGraph 构造、config 加载
├── models.py            # Pydantic 请求/响应模型
└── requirements.txt     # fastapi, uvicorn, sse-starlette, mcp
```

### 文件职责

| 文件 | 职责 |
|------|------|
| `server.py` | FastAPI app 实例、路由定义、`uvicorn.run` 启动。不含业务逻辑 |
| `sse.py` | 核心逻辑。迭代 `graph.stream()` 的 chunk，对比前后状态字段变化，yield SSE 事件 |
| `mcp_tool.py` | MCP Tool 定义，实现标准 MCP Server 协议，暴露 `analyze_stock` tool，调用 `propagate()` 同步获取最终结果。通过 `stdio` 运行 |
| `deps.py` | 共享的 `TradingAgentsGraph` 实例化、config 构建（SSE 和 MCP 复用）|
| `models.py` | Pydantic 请求体模型、SSE event 数据格式定义 |
| `requirements.txt` | `fastapi`, `uvicorn[standard]`, `sse-starlette` |

## API 端点

### `POST /analyze` → SSE stream

实时分析进度，客户端通过 `EventSource` 或等效方式消费。

**请求体**：

```json
{
  "ticker": "NVDA",
  "date": "2024-05-10",
  "analysts": ["market", "news", "fundamentals", "social"],
  "config": {}
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `ticker` | string | 是 | - | 股票代码 |
| `date` | string | 否 | 今天 | 分析日期，YYYY-MM-DD |
| `analysts` | string[] | 否 | 全部4个 | 选择的分析师 |
| `config` | object | 否 | `{}` | 覆盖 default_config |

**响应**：`Content-Type: text/event-stream`

SSE 事件序列：

```
event: analysis_start
data: {"ticker": "NVDA", "date": "2024-05-10", "analysts": [...]}

event: agent_complete
data: {"agent": "Market Analyst", "report_field": "market_report", "content": "..."}

event: agent_complete
data: {"agent": "News Analyst", "report_field": "news_report", "content": "..."}

event: debate_update
data: {"type": "investment", "judge_decision": "..."}

event: agent_complete
data: {"agent": "Trader", "report_field": "trader_investment_plan", "content": "..."}

event: debate_update
data: {"type": "risk", "judge_decision": "..."}

event: analysis_complete
data: {"decision": "BUY", "raw_decision": "...", "state": {...}}
```

### `POST /analyze/sync` → JSON response

同步调用，返回最终决策。独立于 MCP 的 HTTP 接口，供简单场景使用。

**请求体**：与 `/analyze` 相同。

**响应**：

```json
{
  "ticker": "NVDA",
  "date": "2024-05-10",
  "decision": "BUY",
  "raw_decision": "Based on comprehensive analysis...",
  "reports": {
    "market_report": "...",
    "news_report": "...",
    "sentiment_report": "...",
    "fundamentals_report": "...",
    "trader_investment_plan": "...",
    "final_trade_decision": "..."
  }
}
```

### `GET /health` → JSON response

健康检查。

```json
{"status": "ok"}
```

## SSE 事件映射逻辑

核心在 `sse.py`，通过维护 `prev_state` 字典，对比前后 chunk 的字段变化来检测事件。

### 事件触发规则

| 检测条件 | SSE event type |
|---|---|
| 首个 chunk 到达 | `analysis_start` |
| `market_report` 从空变为非空 | `agent_complete` (Market Analyst) |
| `sentiment_report` 从空变为非空 | `agent_complete` (Social Analyst) |
| `news_report` 从空变为非空 | `agent_complete` (News Analyst) |
| `fundamentals_report` 从空变为非空 | `agent_complete` (Fundamentals Analyst) |
| `investment_debate_state.judge_decision` 出现 | `debate_update` (type: investment) |
| `trader_investment_plan` 从空变为非空 | `agent_complete` (Trader) |
| `risk_debate_state.judge_decision` 出现 | `debate_update` (type: risk) |
| `final_trade_decision` 从空变为非空 | `analysis_complete` |

### SSE event 数据格式

所有 SSE event 的 `data` 均为 JSON，包含以下通用字段：

```json
{
  "event_id": "uuid",       // 唯一事件 ID
  "timestamp": "ISO8601",   // 事件时间
  "ticker": "NVDA",         // 当前分析的 ticker
  "type": "agent_complete", // 事件类型
  ...                       // 类型特定字段
}
```

各类型特定字段：

- `analysis_start`: `date`, `analysts`
- `agent_complete`: `agent`, `report_field`, `content`
- `debate_update`: `type` ("investment"|"risk"), `judge_decision`
- `analysis_complete`: `decision`, `raw_decision`

## 并发模型

`graph.stream()` 是同步阻塞调用，单次分析耗时 10-30 分钟。

```
Client POST /analyze {ticker: "NVDA"}
    │
    ├─ FastAPI async endpoint
    │   ├─ 创建 asyncio.Queue
    │   ├─ 用 asyncio.to_thread() 启动 sync graph.stream() 在线程池中
    │   │   └─ 线程内：for chunk in graph.stream():
    │   │       → 检测变化 → event → loop.call_soon_threadsafe(queue.put_nowait(event))
    │   └─ SSE generator: async for event in queue → yield event
    │
Client POST /analyze {ticker: "AAPL"}  ← 同时发起，独立线程+独立队列
```

关键点：
- 每个请求创建独立的 `TradingAgentsGraph` 实例（无共享状态）
- 每个请求独立的 `asyncio.Queue` 和独立线程
- 线程内 `graph.stream()` 完成 → queue 放入 sentinel (`None`) → SSE generator 关闭
- 无全局并发限制（后续可通过 `asyncio.Semaphore` 添加）

## MCP Tool

`mcp_tool.py` 实现标准 MCP Server 协议（stdio transport），暴露一个 `analyze_stock` tool。

**Tool 定义**：

```json
{
  "name": "analyze_stock",
  "description": "对指定股票进行全面分析，返回最终交易决策",
  "inputSchema": {
    "type": "object",
    "properties": {
      "ticker": {"type": "string", "description": "股票代码，如 NVDA"},
      "date": {"type": "string", "description": "分析日期 YYYY-MM-DD，默认今天"}
    },
    "required": ["ticker"]
  }
}
```

**使用方式**：在 Cursor/Claude 等 MCP 客户端的配置中添加：

```json
{
  "mcpServers": {
    "trading-agents": {
      "command": "python",
      "args": ["-m", "api.mcp_tool"]
    }
  }
}
```

MCP Tool 内部复用 `deps.py` 的 graph 构造逻辑，调用 `propagate()` 同步等待最终结果，返回结构化 JSON。

所有配置通过项目根目录 `.env` 文件管理，与现有 `OPENAI_BASE_URL`、`DEEP_THINK_MODEL` 等配置共存。

新增配置项：

```env
API_HOST=0.0.0.0
API_PORT=8000
API_LOG_LEVEL=info
```

## 依赖

新增依赖（`api/requirements.txt`）：

- `fastapi>=0.115.0`
- `uvicorn[standard]>=0.34.0`
- `sse-starlette>=2.0.0`
- `mcp>=1.0.0`

不修改 `pyproject.toml`，API 依赖独立管理。

## 与现有代码的关系

### 复用的现有能力

| 现有能力 | 来源 | 用途 |
|---|---|---|
| `graph.stream()` 逐节点流式 | `trading_graph.py` | SSE 事件源 |
| `stream_mode: "values"` 全状态推送 | `propagation.py` | 每个 chunk 包含完整 AgentState |
| `Propagator.create_initial_state()` | `propagation.py` | 创建初始状态 |
| `Propagator.get_graph_args()` | `propagation.py` | 获取 stream 参数 |
| `TradingAgentsGraph` 构造器 | `trading_graph.py` | 实例化 graph |
| `process_signal()` | `trading_graph.py` | 最终决策解析 |
| `DEFAULT_CONFIG` | `default_config.py` | 配置基础 |

### 不修改的文件

- `tradingagents/` 目录下所有文件
- `cli/` 目录下所有文件
- `start/` 目录下所有文件
- `pyproject.toml`

### 参考但不复制的文件

- `cli/main.py` (lines 1040-1160) — SSE chunk 映射逻辑的参考实现，在 `sse.py` 中重新实现简化版

## 启动方式

```bash
cd /path/to/TradingAgents
python -m api.server
```

或显式指定：

```bash
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

## 调用示例

### SSE 实时流

```bash
curl -N -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2024-05-10"}'
```

### MCP 同步调用

```bash
curl -X POST http://localhost:8000/analyze/sync \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA"}'
```

### 健康检查

```bash
curl http://localhost:8000/health
```
