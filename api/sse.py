import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, Any, List, Optional

from tradingagents.graph.trading_graph import TradingAgentsGraph
from api.deps import create_graph


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


def detect_events(
    chunk: Dict[str, Any],
    prev_state: Dict[str, Any],
    ticker: str,
    analysts: List[str],
    is_first: bool,
    graph: "TradingAgentsGraph" = None,
) -> List[Dict[str, Any]]:
    events = []

    if is_first:
        events.append(
            _make_event("analysis_start", ticker, date=chunk.get("trade_date", ""), analysts=analysts)
        )

    for field, agent_name in REPORT_FIELDS.items():
        prev_val = prev_state.get(field, "")
        curr_val = chunk.get(field, "")
        if not prev_val and curr_val:
            events.append(
                _make_event(
                    "agent_complete",
                    ticker,
                    agent=agent_name,
                    report_field=field,
                    content=curr_val,
                )
            )

    prev_invest_judge = ""
    if prev_state.get("investment_debate_state"):
        prev_invest_judge = prev_state["investment_debate_state"].get("judge_decision", "")
    curr_invest_judge = ""
    if chunk.get("investment_debate_state"):
        curr_invest_judge = chunk["investment_debate_state"].get("judge_decision", "")
    if not prev_invest_judge and curr_invest_judge:
        debate = chunk["investment_debate_state"]
        events.append(
            _make_event(
                "debate_update",
                ticker,
                debate_type="investment",
                judge_decision=debate.get("judge_decision", ""),
            )
        )

    prev_risk_judge = ""
    if prev_state.get("risk_debate_state"):
        prev_risk_judge = prev_state["risk_debate_state"].get("judge_decision", "")
    curr_risk_judge = ""
    if chunk.get("risk_debate_state"):
        curr_risk_judge = chunk["risk_debate_state"].get("judge_decision", "")
    if not prev_risk_judge and curr_risk_judge:
        debate = chunk["risk_debate_state"]
        events.append(
            _make_event(
                "debate_update",
                ticker,
                debate_type="risk",
                judge_decision=debate.get("judge_decision", ""),
            )
        )

    prev_decision = prev_state.get("final_trade_decision", "")
    curr_decision = chunk.get("final_trade_decision", "")
    if not prev_decision and curr_decision:
        if graph is not None:
            parsed = graph.process_signal(curr_decision)
        else:
            parsed = curr_decision
        events.append(
            _make_event(
                "analysis_complete",
                ticker,
                decision=parsed,
                raw_decision=curr_decision,
            )
        )

    return events


def _run_stream_in_thread(
    graph: TradingAgentsGraph,
    ticker: str,
    trade_date: str,
    analysts: List[str],
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
):
    try:
        past_context = graph.memory_log.get_past_context(ticker)
        init_state = graph.propagator.create_initial_state(ticker, trade_date, past_context=past_context)
        args = graph.propagator.get_graph_args()

        prev_state: Dict[str, Any] = {}
        is_first = True

        for chunk in graph.graph.stream(init_state, **args):
            events = detect_events(chunk, prev_state, ticker, analysts, is_first, graph)
            for event in events:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            prev_state = chunk
            is_first = False

    except Exception as e:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            _make_event("error", ticker, message=str(e)),
        )
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, None)


async def analyze_sse_stream(
    ticker: str,
    trade_date: str,
    analysts: Optional[List[str]] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    selected = analysts or ["market", "social", "news", "fundamentals"]
    graph = create_graph(selected, config_overrides)

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

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
