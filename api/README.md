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

### 1. SSE 实时分析 `POST /analyze`

发起分析请求，通过 Server-Sent Events 实时接收分析进度。每个 Agent 完成时推送一个事件，最终推送决策结果。

**请求体：**

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
| `analysts` | string[] | 否 | 全部 4 个 | 可选值：`market`, `social`, `news`, `fundamentals` |
| `config` | object | 否 | `{}` | 覆盖 DEFAULT_CONFIG 中的键值 |

**响应：** `Content-Type: text/event-stream`

**curl 调用：**

```bash
curl -N -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2024-05-10"}'
```

**事件序列示例：**

```
event: analysis_start
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"analysis_start","date":"2024-05-10","analysts":["market","social","news","fundamentals"]}

event: agent_complete
data: {"event_id":"...","timestamp":"...","ticker":"NVDA","type":"agent_complete","agent":"Market Analyst","report_field":"market_report","content":"市场技术分析报告..."}

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

**JavaScript 前端调用：**

```javascript
const evtSource = new EventSource("http://localhost:8000/analyze", {
  // 注意：EventSource 只支持 GET，POST 需要用 fetch + ReadableStream
});

// 推荐：使用 fetch 方式
async function analyze(ticker, date) {
  const response = await fetch("http://localhost:8000/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker, date }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const text = decoder.decode(value);
    // 解析 SSE 格式：event: xxx\ndata: {...}\n\n
    const lines = text.split("\n");
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const event = JSON.parse(line.slice(6));
        console.log(`[${event.type}]`, event);
      }
    }
  }
}

analyze("NVDA", "2024-05-10");
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
| `agent_complete` | 某个 Agent 分析完成 | `agent`, `report_field`, `content` |
| `debate_update` | 辩论结束（投资辩论或风控辩论） | `debate_type`（"investment" / "risk"）, `judge_decision` |
| `analysis_complete` | 全部分析完成 | `decision`, `raw_decision` |
| `error` | 分析过程出错 | `message` |

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
