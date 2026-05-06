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
