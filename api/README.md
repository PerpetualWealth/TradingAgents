# TradingAgents API

SSE 实时流式 API + MCP Tool，将 TradingAgents 的股票分析能力暴露为 HTTP 服务和 AI 编程助手工具。

## 快速开始

### 安装依赖

```bash
pip install -r api/requirements.txt
```

### 配置

在项目根目录 `.env` 中添加（通常已存在，只需确认以下配置）：

```env
# LLM 配置（已有）
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-xxx
DEEP_THINK_MODEL=gpt-4o
QUICK_THINK_MODEL=gpt-4o-mini
LLM_PROVIDER=openai

# API 服务配置
API_HOST=0.0.0.0
API_PORT=8000
API_LOG_LEVEL=info
```

### 启动服务

```bash
python -m api.server
```

或直接用 uvicorn：

```bash
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

---

## API 端点

### 1. SSE 实时分析 `GET /analyze`

发起分析请求，通过 Server-Sent Events 实时接收分析进度。每个 Agent 完成时推送一个事件，最终推送决策结果。标准 SSE 使用 GET 请求，兼容浏览器 `EventSource` API。

**Query 参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `ticker` | string | 是 | - | 股票代码 |
| `date` | string | 否 | 今天 | 分析日期，YYYY-MM-DD |
| `analysts` | string | 否 | 全部 4 个 | 逗号分隔，可选值：`market`, `social`, `news`, `fundamentals` |

**响应：** `Content-Type: text/event-stream`

**curl 调用：**

```bash
curl -N "http://localhost:8000/analyze?ticker=NVDA&date=2024-05-10"
```

**事件序列示例：**

```
event: analysis_start
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"analysis_start","date":"2024-05-10","analysts":["market","social","news","fundamentals"]}

event: tool_call
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"tool_call","tool":"get_stock_data","input":{"ticker":"NVDA"}}

event: tool_result
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"tool_result","tool":"get_stock_data","output":"Date,Open,High,Low,Close..."}

event: tool_call
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"tool_call","tool":"get_indicators","input":{"ticker":"NVDA"}}

event: tool_result
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"tool_result","tool":"get_indicators","output":"MACD:-0.88,RSI:40.88..."}

event: agent_complete
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"agent_complete","agent":"Market Analyst","report_field":"market_report","content":"市场技术分析报告..."}

event: tool_call
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"tool_call","tool":"get_news","input":{"ticker":"NVDA"}}

event: tool_result
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"tool_result","tool":"get_news","output":"新闻列表..."}

event: agent_complete
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"agent_complete","agent":"News Analyst","report_field":"news_report","content":"新闻分析报告..."}

event: agent_complete
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"agent_complete","agent":"Social Analyst","report_field":"sentiment_report","content":"社交媒体情绪分析..."}

event: agent_complete
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"agent_complete","agent":"Fundamentals Analyst","report_field":"fundamentals_report","content":"基本面分析报告..."}

event: debate_update
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"debate_update","debate_type":"investment","judge_decision":"..."}

event: agent_complete
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"agent_complete","agent":"Trader","report_field":"trader_investment_plan","content":"交易计划..."}

event: debate_update
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"debate_update","debate_type":"risk","judge_decision":"..."}

event: analysis_complete
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"analysis_complete","decision":"BUY","raw_decision":"..."}
```

**JavaScript 前端调用（标准 EventSource）：**

```javascript
const evtSource = new EventSource("http://localhost:8000/analyze?ticker=NVDA&date=2024-05-10");

evtSource.addEventListener("analysis_start", (e) => {
  console.log("分析开始", JSON.parse(e.data));
});

evtSource.addEventListener("agent_complete", (e) => {
  const data = JSON.parse(e.data);
  console.log(`[${data.agent}] 完成`);
});

evtSource.addEventListener("analysis_complete", (e) => {
  const data = JSON.parse(e.data);
  console.log(`最终决策: ${data.decision}`);
  evtSource.close();
});

evtSource.onerror = () => evtSource.close();
```

### 2. 同步分析 `POST /analyze/sync`

同步调用，等待分析完成后返回最终结果（耗时 10-30 分钟）。

**请求体：** 与 `/analyze` 相同。

**curl 调用：**

```bash
curl -X POST http://localhost:8000/analyze/sync \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA"}'
```

**响应：**

```json
{
  "ticker": "NVDA",
  "date": "2024-05-10",
  "decision": "BUY",
  "raw_decision": "Based on comprehensive analysis...",
  "reports": {
    "market_report": "...",
    "sentiment_report": "...",
    "news_report": "...",
    "fundamentals_report": "...",
    "trader_investment_plan": "...",
    "final_trade_decision": "..."
  }
}
```

### 3. 健康检查 `GET /health`

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok"}
```

---

## SSE 事件类型

| 事件类型 | 触发时机 | 关键字段 |
|----------|----------|----------|
| `analysis_start` | 分析开始 | `date`, `analysts` |
| `tool_call` | 工具开始调用 | `tool`, `input` |
| `tool_result` | 工具返回数据 | `tool`, `output` |
| `agent_complete` | 某个 Agent 分析完成 | `agent`, `report_field`, `content` |
| `debate_update` | 辩论结束（投资辩论或风控辩论） | `debate_type`（"investment" / "risk"）, `judge_decision` |
| `analysis_complete` | 全部分析完成 | `decision`, `raw_decision` |
| `error` | 分析过程出错 | `message` |

### 8 种 Tool

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

**Agent 完成顺序：**

```
Market Analyst → Social Analyst → News Analyst → Fundamentals Analyst
  → Bull/Bear 辩论 → Research Manager → Trader
    → Aggressive/Conservative/Neutral 风控辩论 → Portfolio Manager → 最终决策
```

---

## MCP Tool

`api/mcp_tool.py` 实现了标准 MCP Server（stdio transport），可在 Cursor、Claude Desktop、Windsurf 等 AI 编程助手中直接调用。

### 配置

在 MCP 客户端的配置文件中添加：

**Cursor** (`.cursor/mcp.json`)：

```json
{
  "mcpServers": {
    "trading-agents": {
      "command": "python",
      "args": ["-m", "api.mcp_tool"],
      "cwd": "/path/to/TradingAgents"
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`)：

```json
{
  "mcpServers": {
    "trading-agents": {
      "command": "python",
      "args": ["-m", "api.mcp_tool"],
      "cwd": "/path/to/TradingAgents"
    }
  }
}
```

### 使用

配置完成后，在 AI 编程助手中直接对话即可触发：

> "帮我分析一下 NVDA"

AI 会自动调用 `analyze_stock` tool，传入 `ticker: "NVDA"`，等待几分钟后返回完整的分析决策。

### Tool 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ticker` | string | 是 | 股票代码，如 NVDA、AAPL、TSLA |
| `date` | string | 否 | 分析日期 YYYY-MM-DD，默认今天 |

---

## 文件结构

```
api/
├── __init__.py          # 包标识
├── server.py            # FastAPI 应用，路由定义，启动入口
├── sse.py               # SSE 事件生成器，核心 chunk → event 映射逻辑
├── mcp_tool.py          # MCP Server（stdio），暴露 analyze_stock tool
├── deps.py              # 共享依赖：.env 加载、config 构建、graph 实例化
├── models.py            # Pydantic 请求/响应模型
├── requirements.txt     # API 专用依赖
└── README.md            # 本文件
```

## 并发说明

- 每个分析请求在独立线程中运行 `graph.stream()`，互不阻塞
- 每个请求创建独立的 `TradingAgentsGraph` 实例，无共享状态
- 支持同时分析多个 ticker（如同时 POST NVDA 和 AAPL）
- 单次分析耗时约 10-30 分钟，取决于 LLM 响应速度

## 架构

```
Client POST /analyze {ticker: "NVDA"}
    │
    ├─ FastAPI async endpoint
    │   ├─ 创建 asyncio.Queue
    │   ├─ asyncio.run_in_executor() → 线程池中运行 sync graph.stream()
    │   │   └─ 线程内：for chunk in graph.stream():
    │   │       → detect_events(chunk, prev_state) → event
    │   │       → loop.call_soon_threadsafe(queue.put(event))
    │   └─ SSE generator: await queue.get() → yield event
    │
    ↓  Client receives SSE events in real-time
```
