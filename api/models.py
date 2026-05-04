from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol, e.g. NVDA")
    date: Optional[str] = Field(
        None,
        description="Analysis date in YYYY-MM-DD format. Defaults to today.",
    )
    analysts: Optional[List[str]] = Field(
        None,
        description="List of analysts to use. Options: market, social, news, fundamentals. Defaults to all.",
    )
    config: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Override keys in DEFAULT_CONFIG.",
    )


class SyncAnalyzeResponse(BaseModel):
    ticker: str
    date: str
    decision: str
    raw_decision: str
    reports: Dict[str, str]


class HealthResponse(BaseModel):
    status: str = "ok"
