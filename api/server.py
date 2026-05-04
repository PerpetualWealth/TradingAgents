import os
import json
import asyncio
from datetime import date

import uvicorn
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

from api.models import AnalyzeRequest, SyncAnalyzeResponse, HealthResponse
from api.sse import analyze_sse_stream
from api.deps import create_graph

app = FastAPI(title="TradingAgents API", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@app.post("/analyze")
async def analyze(request: AnalyzeRequest):
    trade_date = request.date or date.today().isoformat()
    analysts = request.analysts

    async def event_generator():
        async for event in analyze_sse_stream(
            ticker=request.ticker,
            trade_date=trade_date,
            analysts=analysts,
            config_overrides=request.config or None,
        ):
            yield {
                "event": event["type"],
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@app.post("/analyze/sync", response_model=SyncAnalyzeResponse)
async def analyze_sync(request: AnalyzeRequest):
    trade_date = request.date or date.today().isoformat()
    analysts = request.analysts or ["market", "social", "news", "fundamentals"]
    graph = create_graph(analysts, request.config or None)

    def run():
        return graph.propagate(request.ticker, trade_date)

    final_state, decision = await asyncio.get_event_loop().run_in_executor(None, run)

    return SyncAnalyzeResponse(
        ticker=request.ticker,
        date=trade_date,
        decision=decision,
        raw_decision=final_state.get("final_trade_decision", ""),
        reports={
            "market_report": final_state.get("market_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "news_report": final_state.get("news_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "trader_investment_plan": final_state.get("trader_investment_plan", ""),
            "final_trade_decision": final_state.get("final_trade_decision", ""),
        },
    )


if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    log_level = os.getenv("API_LOG_LEVEL", "info")
    uvicorn.run("api.server:app", host=host, port=port, log_level=log_level, reload=False)
