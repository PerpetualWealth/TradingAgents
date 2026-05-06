# SSE Tool Events Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tool-level atomic events (tool_call, tool_result) to SSE stream, refactor mockdata to unified raw event format, ensure mock and real paths use identical processing logic.

**Architecture:** Single event stream format in mockdata.json with `event_type` discriminator. `BaseCallbackHandler` captures tool events during real analysis. `sse.py` has a single `process_raw_event()` function that both mock and real paths feed into.

**Tech Stack:** FastAPI, asyncio.Queue, BaseCallbackHandler (langchain_core), threading for callback → queue bridge

---

### Task 1: Backup existing mockdata and create RecordingCallback

**Files:**
- Modify: `api/record_chunks.py`
- Backup: `api/mockdata.json` → `api/mockdata.json.bak`

- [ ] **Step 1: Backup existing mockdata**

```bash
cp api/mockdata.json api/mockdata.json.bak
```

- [ ] **Step 2: Rewrite `api/record_chunks.py` with RecordingCallback and new event format**

```python
#!/usr/bin/env python3
"""Record real graph.stream() chunks + tool events to JSON for mock data."""

import sys
import json
import itertools
import threading
from pathlib import Path
from datetime import date
from typing import Any, Dict, List

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=True)

from langchain_core.callbacks import BaseCallbackHandler
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
import os

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = os.getenv("LLM_PROVIDER", "openai")
config["deep_think_llm"] = os.getenv("DEEP_THINK_MODEL", "gpt-4o-mini")
config["quick_think_llm"] = os.getenv("QUICK_THINK_MODEL", "gpt-4o-mini")
config["backend_url"] = os.getenv("OPENAI_BASE_URL")

ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
trade_date = sys.argv[2] if len(sys.argv) > 2 else date.today().isoformat()

print(f"Recording analysis for {ticker} on {trade_date}...")

_seq = itertools.count()
_lock = threading.Lock()
events: List[Dict[str, Any]] = []


class RecordingCallback(BaseCallbackHandler):
    def __init__(self):
        self._current_tool = ""

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        tool_name = serialized.get("name", "unknown")
        with _lock:
            self._current_tool = tool_name
            events.append({
                "seq": next(_seq),
                "event_type": "tool_start",
                "tool": tool_name,
                "input": input_str if isinstance(input_str, dict) else {"query": str(input_str)},
            })
        print(f"  tool_start: {tool_name}")

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        tool_name = self._current_tool
        with _lock:
            events.append({
                "seq": next(_seq),
                "event_type": "tool_result",
                "tool": tool_name,
                "output": str(output),
            })
        print(f"  tool_result: {tool_name} ({len(str(output))} chars)")


def serialize_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    result = {}
    for key, value in chunk.items():
        if key == "messages":
            result["messages"] = []
            for msg in value:
                if hasattr(msg, "content"):
                    result["messages"].append({
                        "type": msg.__class__.__name__,
                        "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                    })
                else:
                    result["messages"].append(str(msg))
        elif isinstance(value, (str, int, float, bool, type(None))):
            result[key] = value
        elif isinstance(value, dict):
            result[key] = value
        else:
            result[key] = str(value)
    return result


recording_callback = RecordingCallback()

graph = TradingAgentsGraph(
    selected_analysts=["market", "social", "news", "fundamentals"],
    debug=True,
    config=config,
    callbacks=[recording_callback],
)

past_context = graph.memory_log.get_past_context(ticker)
init_state = graph.propagator.create_initial_state(ticker, trade_date, past_context=past_context)
args = graph.propagator.get_graph_args(callbacks=[recording_callback])

for chunk in graph.graph.stream(init_state, **args):
    with _lock:
        events.append({
            "seq": next(_seq),
            "event_type": "graph_chunk",
            "data": serialize_chunk(chunk),
        })
    report_status = (
        f"market={'✓' if chunk.get('market_report') else '·'} "
        f"social={'✓' if chunk.get('sentiment_report') else '·'} "
        f"news={'✓' if chunk.get('news_report') else '·'} "
        f"fund={'✓' if chunk.get('fundamentals_report') else '·'} "
        f"trader={'✓' if chunk.get('trader_investment_plan') else '·'} "
        f"decision={'✓' if chunk.get('final_trade_decision') else '·'}"
    )
    print(f"  graph_chunk ({len(events)} total): {report_status}")

events.sort(key=lambda e: e["seq"])
for e in events:
    e.pop("seq")

output_path = project_root / "api" / "mockdata.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(events, f, ensure_ascii=False, indent=2)

tool_count = sum(1 for e in events if e["event_type"].startswith("tool_"))
chunk_count = sum(1 for e in events if e["event_type"] == "graph_chunk")
print(f"\nDone! {len(events)} events ({chunk_count} chunks, {tool_count} tool events) saved to {output_path}")
```

- [ ] **Step 3: Verify the script runs without import errors**

Run: `python -c "import api.record_chunks" 2>/dev/null; echo "Import check done"`

- [ ] **Step 4: Commit backup and new recording script**

```bash
git add api/mockdata.json.bak api/record_chunks.py
git commit -m "feat(api): add event-stream recording script with tool callbacks, backup existing mockdata"
```

---

### Task 2: Rewrite `api/sse.py` with unified `process_raw_event()`

**Files:**
- Modify: `api/sse.py`

This is the core refactor. The key change: a single `process_raw_event()` function that both mock and real paths call. No more separate `detect_events()` for chunks and separate handling for tools.

- [ ] **Step 1: Rewrite `api/sse.py`**

```python
import asyncio
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, Any, List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from tradingagents.graph.trading_graph import TradingAgentsGraph
from api.deps import create_graph

MOCK_DATA_PATH = Path(__file__).parent / "mockdata.json"

REPORT_FIELDS = {
    "market_report": "Market Analyst",
    "sentiment_report": "Social Analyst",
    "news_report": "News Analyst",
    "fundamentals_report": "Fundamentals Analyst",
    "trader_investment_plan": "Trader",
}


def _make_event(event_type: str, ticker: str, **kwargs) -> Dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "type": event_type,
        **kwargs,
    }


class SSEEventProcessor:
    def __init__(self, ticker: str, analysts: List[str], graph: "TradingAgentsGraph" = None):
        self.ticker = ticker
        self.analysts = analysts
        self.graph = graph
        self.prev_state: Dict[str, Any] = {}
        self.is_first_chunk = True

    def process_raw_event(self, raw_event: Dict[str, Any]) -> List[Dict[str, Any]]:
        event_type = raw_event.get("event_type", "")

        if event_type == "graph_chunk":
            return self._process_chunk(raw_event.get("data", {}))
        elif event_type == "tool_start":
            return self._process_tool_start(raw_event)
        elif event_type == "tool_result":
            return self._process_tool_result(raw_event)

        return []

    def _process_chunk(self, chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = []

        if self.is_first_chunk:
            events.append(
                _make_event("analysis_start", self.ticker, date=chunk.get("trade_date", ""), analysts=self.analysts)
            )
            self.is_first_chunk = False

        for field, agent_name in REPORT_FIELDS.items():
            prev_val = self.prev_state.get(field, "")
            curr_val = chunk.get(field, "")
            if not prev_val and curr_val:
                events.append(
                    _make_event("agent_complete", self.ticker, agent=agent_name, report_field=field, content=curr_val)
                )

        prev_invest_judge = ""
        if self.prev_state.get("investment_debate_state"):
            prev_invest_judge = self.prev_state["investment_debate_state"].get("judge_decision", "")
        curr_invest_judge = ""
        if chunk.get("investment_debate_state"):
            curr_invest_judge = chunk["investment_debate_state"].get("judge_decision", "")
        if not prev_invest_judge and curr_invest_judge:
            debate = chunk["investment_debate_state"]
            events.append(
                _make_event(
                    "debate_update", self.ticker,
                    debate_type="investment",
                    judge_decision=debate.get("judge_decision", ""),
                    bull_history=debate.get("bull_history", ""),
                    bear_history=debate.get("bear_history", ""),
                    history=debate.get("history", ""),
                    investment_plan=chunk.get("investment_plan", ""),
                )
            )

        prev_risk_judge = ""
        if self.prev_state.get("risk_debate_state"):
            prev_risk_judge = self.prev_state["risk_debate_state"].get("judge_decision", "")
        curr_risk_judge = ""
        if chunk.get("risk_debate_state"):
            curr_risk_judge = chunk["risk_debate_state"].get("judge_decision", "")
        if not prev_risk_judge and curr_risk_judge:
            debate = chunk["risk_debate_state"]
            events.append(
                _make_event(
                    "debate_update", self.ticker,
                    debate_type="risk",
                    judge_decision=debate.get("judge_decision", ""),
                    aggressive_history=debate.get("aggressive_history", ""),
                    conservative_history=debate.get("conservative_history", ""),
                    neutral_history=debate.get("neutral_history", ""),
                    history=debate.get("history", ""),
                )
            )

        prev_decision = self.prev_state.get("final_trade_decision", "")
        curr_decision = chunk.get("final_trade_decision", "")
        if not prev_decision and curr_decision:
            if self.graph is not None:
                parsed = self.graph.process_signal(curr_decision)
            else:
                parsed = curr_decision
            events.append(
                _make_event("analysis_complete", self.ticker, decision=parsed, raw_decision=curr_decision)
            )

        self.prev_state = chunk
        return events

    def _process_tool_start(self, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            _make_event("tool_call", self.ticker, tool=raw.get("tool", ""), input=raw.get("input", {}))
        ]

    def _process_tool_result(self, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            _make_event("tool_result", self.ticker, tool=raw.get("tool", ""), output=raw.get("output", ""))
        ]


class SSEStreamCallback(BaseCallbackHandler):
    def __init__(self, ticker: str, processor: SSEEventProcessor, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        self.ticker = ticker
        self.processor = processor
        self.loop = loop
        self.queue = queue
        self._current_tool = ""

    def on_tool_start(self, serialized: Dict[str, Any], input_str: Any, **kwargs: Any) -> None:
        tool_name = serialized.get("name", "unknown")
        self._current_tool = tool_name
        raw = {"event_type": "tool_start", "tool": tool_name, "input": input_str if isinstance(input_str, dict) else {"query": str(input_str)}}
        for event in self.processor.process_raw_event(raw):
            self.loop.call_soon_threadsafe(self.queue.put_nowait, event)

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        raw = {"event_type": "tool_result", "tool": self._current_tool, "output": str(output)}
        for event in self.processor.process_raw_event(raw):
            self.loop.call_soon_threadsafe(self.queue.put_nowait, event)


def _run_stream_in_thread(
    graph: TradingAgentsGraph,
    ticker: str,
    trade_date: str,
    analysts: List[str],
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
):
    processor = SSEEventProcessor(ticker, analysts, graph)
    stream_callback = SSEStreamCallback(ticker, processor, loop, queue)

    try:
        past_context = graph.memory_log.get_past_context(ticker)
        init_state = graph.propagator.create_initial_state(ticker, trade_date, past_context=past_context)
        args = graph.propagator.get_graph_args(callbacks=[stream_callback])

        for chunk in graph.graph.stream(init_state, **args):
            raw = {"event_type": "graph_chunk", "data": chunk}
            for event in processor.process_raw_event(raw):
                loop.call_soon_threadsafe(queue.put_nowait, event)

    except Exception as e:
        loop.call_soon_threadsafe(queue.put_nowait, _make_event("error", ticker, message=str(e)))
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, None)


async def _mock_sse_stream(
    ticker: str,
    trade_date: str,
    analysts: List[str],
    queue: asyncio.Queue,
):
    with open(MOCK_DATA_PATH, "r", encoding="utf-8") as f:
        raw_events = json.load(f)

    processor = SSEEventProcessor(ticker, analysts)

    for raw_event in raw_events:
        if raw_event.get("event_type") == "graph_chunk":
            raw_event["data"]["company_of_interest"] = ticker
            raw_event["data"]["trade_date"] = trade_date

        for event in processor.process_raw_event(raw_event):
            await asyncio.sleep(0.1)
            await queue.put(event)

    await queue.put(None)


async def analyze_sse_stream(
    ticker: str,
    trade_date: str,
    analysts: Optional[List[str]] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    selected = analysts or ["market", "social", "news", "fundamentals"]

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    if ticker.upper() == "MOCK":
        loop.create_task(_mock_sse_stream(ticker, trade_date, selected, queue))
    else:
        graph = create_graph(selected, config_overrides)
        loop.run_in_executor(
            None,
            _run_stream_in_thread,
            graph,
            ticker,
            trade_date,
            selected,
            loop,
            queue,
        )

    while True:
        event = await queue.get()
        if event is None:
            break
        yield event
```

- [ ] **Step 2: Verify import works**

Run: `cd /Users/pengziran/development/PerpetualWealth/TradingAgents && python -c "from api.sse import SSEEventProcessor; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add api/sse.py
git commit -m "refactor(api): unified process_raw_event() for graph_chunk and tool events"
```

---

### Task 3: Update `api/server.py` — no changes needed

`server.py` already imports `analyze_sse_stream` from `api.sse` and wraps it in `EventSourceResponse`. The function signature has not changed. No modifications needed.

- [ ] **Step 1: Verify server imports still work**

Run: `cd /Users/pengziran/development/PerpetualWealth/TradingAgents && python -c "from api.server import app; print('OK')"`
Expected: `OK`

---

### Task 4: Record new mockdata with tool events

**Files:**
- Modify: `api/mockdata.json` (generated by recording)

This task runs the actual NVDA analysis to produce new mockdata. Takes 10-30 minutes.

- [ ] **Step 1: Run recording in tmux**

```bash
tmux new-session -d -s "record-nvda-v2" "cd /Users/pengziran/development/PerpetualWealth/TradingAgents && python -u api/record_chunks.py NVDA 2026-05-05 2>&1 | tee /tmp/nvda_record_v2.log"
```

- [ ] **Step 2: Wait for completion, verify output**

```bash
tail -5 /tmp/nvda_record_v2.log
```

Expected: `Done! N events (M chunks, K tool events) saved to .../api/mockdata.json`

- [ ] **Step 3: Verify mockdata has all three event types**

```bash
python3 -c "import json; data=json.load(open('api/mockdata.json')); types=set(e['event_type'] for e in data); print(f'Event types: {types}'); print(f'Total: {len(data)} events')"
```

Expected: `Event types: {'graph_chunk', 'tool_start', 'tool_result'}`

- [ ] **Step 4: Commit new mockdata**

```bash
git add api/mockdata.json
git commit -m "feat(api): re-record mockdata with unified event stream format (graph_chunk + tool events)"
```

---

### Task 5: Restart service and verify SSE with MOCK

**Files:** No file changes.

- [ ] **Step 1: Restart the API service**

```bash
launchctl unload ~/Library/LaunchAgents/com.tradingagents.api.plist
sleep 1
launchctl load ~/Library/LaunchAgents/com.tradingagents.api.plist
sleep 2
curl -s http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 2: Test MOCK SSE — verify new event types appear**

```bash
curl -N "http://localhost:8000/analyze?ticker=MOCK&date=2026-05-05" 2>/dev/null | grep "^event:" | sort | uniq -c
```

Expected: Output contains `tool_call`, `tool_result`, `analysis_start`, `agent_complete`, `debate_update`, `analysis_complete`

- [ ] **Step 3: Verify tool_call and tool_result event structure**

```bash
curl -N "http://localhost:8000/analyze?ticker=MOCK&date=2026-05-05" 2>/dev/null | grep "^event: tool_" | head -6
```

Expected: Alternating `tool_call` and `tool_result` events with `tool` and `input`/`output` fields.

---

### Task 6: Update `api/README.md` with new event types

**Files:**
- Modify: `api/README.md`

- [ ] **Step 1: Add tool_call and tool_result to SSE Event Types section**

In the SSE Event Types table, add two rows:

| Event Type | Trigger | Key Fields |
|-----------|---------|-----------|
| `tool_call` | Tool starts executing | `tool`, `input` |
| `tool_result` | Tool returns data | `tool`, `output` |

Update the event sequence example to include tool events between agent events.

- [ ] **Step 2: Commit**

```bash
git add api/README.md
git commit -m "docs(api): add tool_call and tool_result to SSE event documentation"
```
