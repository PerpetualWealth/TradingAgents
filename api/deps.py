import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


def load_env():
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)


load_env()


def build_config(overrides: Dict[str, Any] = None) -> Dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = os.getenv("LLM_PROVIDER", "openai")
    config["deep_think_llm"] = os.getenv("DEEP_THINK_MODEL", "gpt-4o-mini")
    config["quick_think_llm"] = os.getenv("QUICK_THINK_MODEL", "gpt-4o-mini")
    config["backend_url"] = os.getenv("OPENAI_BASE_URL")
    if overrides:
        config.update(overrides)
    return config


def create_graph(
    analysts: Optional[List[str]] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> TradingAgentsGraph:
    config = build_config(config_overrides)
    selected = analysts or ["market", "social", "news", "fundamentals"]
    return TradingAgentsGraph(
        selected_analysts=selected,
        debug=True,
        config=config,
    )
