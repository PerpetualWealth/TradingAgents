import sys
import json
from pathlib import Path
from datetime import date

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from api.deps import create_graph

server = Server("trading-agents")


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="analyze_stock",
            description="对指定股票进行全面分析，返回最终交易决策（Buy/Hold/Sell 等）。分析过程需要几分钟。",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "股票代码，如 NVDA、AAPL、TSLA",
                    },
                    "date": {
                        "type": "string",
                        "description": "分析日期，格式 YYYY-MM-DD，默认今天",
                    },
                },
                "required": ["ticker"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name != "analyze_stock":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    ticker = arguments["ticker"]
    trade_date = arguments.get("date") or date.today().isoformat()

    graph = create_graph()
    final_state, decision = graph.propagate(ticker, trade_date)

    result = {
        "ticker": ticker,
        "date": trade_date,
        "decision": decision,
        "raw_decision": final_state.get("final_trade_decision", ""),
        "reports": {
            "market_report": final_state.get("market_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "news_report": final_state.get("news_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "trader_investment_plan": final_state.get("trader_investment_plan", ""),
        },
    }

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
