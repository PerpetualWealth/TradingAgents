import os
import json
import asyncio
import re
from datetime import date
from typing import Optional, List

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from api.models import AnalyzeRequest, SyncAnalyzeResponse, HealthResponse
from api.sse import analyze_sse_stream
from api.deps import create_graph

app = FastAPI(title="TradingAgents API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT_ANALYSES", "3"))
_analysis_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-^]{1,20}$")


def _validate_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"Invalid ticker: {ticker}")
    return ticker


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@app.get("/analyze")
async def analyze(
    ticker: str = Query(..., description="Stock ticker symbol"),
    date: Optional[str] = Query(None, alias="date", description="Analysis date YYYY-MM-DD"),
    analysts: Optional[str] = Query(None, description="Comma-separated analysts: market,social,news,fundamentals"),
    output_language: Optional[str] = Query(None, description="Output language for reports, e.g. Chinese, English, Japanese"),
):
    ticker = _validate_ticker(ticker)
    from datetime import date as date_type
    trade_date = date or date_type.today().isoformat()
    analyst_list = analysts.split(",") if analysts else None
    config_overrides = {}
    if output_language:
        config_overrides["output_language"] = output_language

    async def event_generator():
        async with _analysis_semaphore:
            async for event in analyze_sse_stream(
                ticker=ticker,
                trade_date=trade_date,
                analysts=analyst_list,
                config_overrides=config_overrides or None,
            ):
                yield {
                    "event": event["type"],
                    "data": json.dumps(event, ensure_ascii=False),
                }

    return EventSourceResponse(event_generator())


@app.post("/analyze/sync", response_model=SyncAnalyzeResponse)
async def analyze_sync(request: AnalyzeRequest):
    ticker = _validate_ticker(request.ticker)
    trade_date = request.date or date.today().isoformat()
    analysts = request.analysts or ["market", "social", "news", "fundamentals"]
    config_overrides = request.config or {}
    if request.output_language:
        config_overrides["output_language"] = request.output_language

    async with _analysis_semaphore:
        graph = create_graph(analysts, config_overrides or None)

        def run():
            return graph.propagate(ticker, trade_date)

        final_state, decision = await asyncio.get_event_loop().run_in_executor(None, run)

    return SyncAnalyzeResponse(
        ticker=ticker,
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
