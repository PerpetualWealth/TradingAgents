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
