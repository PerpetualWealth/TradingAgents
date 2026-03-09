#!/usr/bin/env python3
"""
TradingAgents - 使用自定义 OpenAI 兼容模型
从 .env 加载配置，支持自定义 baseURL
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


def run_analysis(ticker: str, trade_date: str = None):
    """运行分析"""
    # 先加载 .env 到环境变量（强制覆盖全局环境变量）
    script_dir = Path(__file__).parent.parent
    env_path = script_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print(f"✅ 已加载配置: {env_path}")

    # 读取环境变量
    backend_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    deep_think_model = os.getenv("DEEP_THINK_MODEL", "gpt-4o-mini")
    quick_think_model = os.getenv("QUICK_THINK_MODEL", "gpt-4o-mini")
    api_key = os.getenv("OPENAI_API_KEY", "")

    print(f"🔗 Backend URL: {backend_url}")
    print(f"🤖 Deep LLM: {deep_think_model}")
    print(f"⚡ Quick LLM: {quick_think_model}")
    print(f"🔑 API Key: {api_key[:10]}...")

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = os.getenv("LLM_PROVIDER", "openai")
    config["deep_think_llm"] = deep_think_model
    config["quick_think_llm"] = quick_think_model
    config["backend_url"] = backend_url

    # 上游 v0.2.0 已默认使用 yfinance，无需配置 data_vendors
    # 如需使用 alpha_vantage，可取消注释以下配置：
    # config["data_vendors"]["fundamental_data"] = "alpha_vantage"
    # config["data_vendors"]["news_data"] = "alpha_vantage"

    # 辩论轮数（可选，默认为 1）
    config["max_debate_rounds"] = 1

    ta = TradingAgentsGraph(debug=True, config=config)
    final_state, decision = ta.propagate(ticker, trade_date)

    print(f"\n🎯 最终决策: {decision}")
    print(f"📁 报告: eval_results/{ticker}/TradingAgentsStrategy_logs/full_states_log_{trade_date}.json")

    return final_state, decision


def main():
    import argparse
    from datetime import date

    parser = argparse.ArgumentParser(description="TradingAgents 分析")
    parser.add_argument("--ticker", type=str, default="NVDA", help="股票代码")
    parser.add_argument("--date", type=str, default=None, help="交易日期 (YYYY-MM-DD)")
    parser.add_argument("--debug", action="store_true", help="调试模式")

    args = parser.parse_args()

    trade_date = args.date or date.today().isoformat()

    print(f"\n🚀 开始分析 {args.ticker} ({trade_date})...")
    run_analysis(args.ticker, trade_date)


if __name__ == "__main__":
    main()
