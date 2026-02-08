#!/usr/bin/env python3
"""
TradingAgents Lite - 轻量版股票分析
使用 yfinance 数据 + Minimax 单次 LLM 调用
快速生成分析报告
"""

import os
import json
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

import yfinance as yf


def load_config():
    """加载配置"""
    config_path = os.path.expanduser("~/tradingagent-env")
    if os.path.exists(config_path):
        load_dotenv(config_path)

    return {
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.minimaxi.com/v1"),
        "model": os.getenv("DEEP_THINK_MODEL", "MiniMax-M2.1"),
    }


def get_stock_data(ticker: str, days: int = 30) -> dict:
    """获取股票数据"""
    stock = yf.Ticker(ticker)
    info = stock.info

    # 历史数据
    hist = stock.history(period=f"{days}d")

    # 计算技术指标
    if len(hist) > 0:
        close = hist['Close']
        ma5 = close.rolling(5).mean().iloc[-1] if len(close) >= 5 else close.iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else close.iloc[-1]

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1] if rs.iloc[-1] != 0 else 50

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_hist = macd - signal

        return {
            "ticker": ticker,
            "company": info.get("longName", info.get("shortName", ticker)),
            "current_price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
            "change_percent": info.get("regularMarketChangePercent", 0) * 100,
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0),
            "market_cap": info.get("marketCap", 0) / 1e9,  # Billions
            "pe_ratio": info.get("trailingPE", 0),
            "eps": info.get("trailingEPS", 0),
            "volume": info.get("volume", info.get("regularMarketVolume", 0)),
            "avg_volume": info.get("averageVolume", info.get("averageDailyVolume3Month", 0)),
            "history": hist.iloc[-10:].to_dict('records'),
            "technicals": {
                "ma5": round(ma5, 2),
                "ma20": round(ma20, 2),
                "rsi": round(rsi, 1),
                "macd": round(macd.iloc[-1], 2) if hasattr(macd, 'iloc') else 0,
                "macd_signal": round(signal.iloc[-1], 2) if hasattr(signal, 'iloc') else 0,
            }
        }
    return {}


def generate_analysis_prompt(data: dict) -> str:
    """生成分析提示词"""
    tech = data.get("technicals", {})
    current = data.get("current_price", 0)
    high = data.get("fifty_two_week_high", 0)
    low = data.get("fifty_two_week_low", 0)

    # 计算价格位置
    if high > low:
        price_position = ((current - low) / (high - low)) * 100
    else:
        price_position = 50

    return f"""
你是一个专业的股票分析师。请分析以下股票数据并给出详细报告：

## 股票信息
- 代码: {data['ticker']}
- 公司: {data['company']}

## 价格数据
- 当前价格: ${current:.2f}
- 今日涨跌: {data['change_percent']:+.2f}%
- 52周高/低: ${high:.2f} / ${low:.2f}
- 当前价格位置: {price_position:.0f}% (相对于52周区间)

## 技术指标
- MA5: ${tech.get('ma5', 0):.2f}
- MA20: ${tech.get('ma20', 0):.2f}
- RSI(14): {tech.get('rsi', 50):.1f}
- MACD: {tech.get('macd', 0):.2f}
- MACD Signal: {tech.get('macd_signal', 0):.2f}

## 估值指标
- 市值: ${data['market_cap']:.1f}B
- P/E: {data['pe_ratio']:.2f}
- EPS: ${data['eps']:.2f}

## 最近10日走势
{chr(10).join([f"- {d['Date'] if hasattr(d, 'Date') else str(d)}: Close=${d['Close']:.2f}" for d in data.get('history', [])])}

请生成以下分析报告：

1. **技术分析** - 分析价格走势、技术指标信号（RSI、MACD、均线）
2. **估值分析** - P/E、市值、EPS 评估
3. **趋势判断** - 短期、中期趋势
4. **投资建议** - BUY/SELL/HOLD 及理由
5. **风险提示** - 主要风险因素

请用中文回复，结构清晰，结论明确。
"""


def analyze_with_llm(prompt: str, config: dict) -> str:
    """使用 LLM 生成分析"""
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"]
        )

        response = client.chat.completions.create(
            model=config["model"],
            messages=[
                {"role": "system", "content": "你是一个专业的股票分析师，擅长技术分析和基本面分析。回复简洁、结构清晰。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )

        return response.choices[0].message.content
    except Exception as e:
        return f"LLM 调用失败: {e}"


def save_report(ticker: str, data: dict, analysis: str):
    """保存报告"""
    report_dir = Path(f"eval_results/{ticker}/TradingAgentsStrategy_logs/")
    report_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    report_file = report_dir / f"full_states_log_{today}.json"

    report = {
        "analysis_date": today,
        "ticker": ticker,
        "company": data.get("company", ""),
        "market_report": analysis,
        "final_trade_decision": "PENDING_LLM",
        "raw_data": data
    }

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report_file


def main():
    import argparse

    parser = argparse.ArgumentParser(description="TradingAgents Lite - 轻量版股票分析")
    parser.add_argument("--ticker", type=str, required=True, help="股票代码")
    parser.add_argument("--days", type=int, default=30, help="历史数据天数")
    parser.add_argument("--output", action="store_true", help="输出分析结果")

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"📈 TradingAgents Lite 分析")
    print(f"   股票: {args.ticker}")
    print(f"{'='*60}\n")

    # 加载配置
    config = load_config()
    if not config["api_key"]:
        print("❌ 错误: 未找到 API Key，请检查 ~/tradingagent-env")
        return

    # 获取数据
    print("📊 获取数据中...")
    data = get_stock_data(args.ticker, args.days)
    if not data:
        print(f"❌ 无法获取 {args.ticker} 的数据")
        return

    print(f"✅ 数据获取完成")
    print(f"   当前价: ${data['current_price']:.2f}")
    print(f"   MA5: ${data['technicals']['ma5']:.2f}")
    print(f"   RSI: {data['technicals']['rsi']:.1f}")

    # 生成分析
    print("\n🤖 LLM 分析中...")
    prompt = generate_analysis_prompt(data)
    analysis = analyze_with_llm(prompt, config)

    # 保存报告
    report_file = save_report(args.ticker, data, analysis)
    print(f"\n📁 报告已保存: {report_file}")

    # 输出结果
    if args.output:
        print(f"\n{'='*60}")
        print("📊 分析报告")
        print(f"{'='*60}")
        print(analysis)

    # 提取决策关键词
    decision = "HOLD"
    if "BUY" in analysis.upper() or "买入" in analysis:
        decision = "BUY"
    elif "SELL" in analysis.upper() or "卖出" in analysis:
        decision = "SELL"

    print(f"\n{'='*60}")
    print(f"🎯 建议: {decision}")
    print(f"{'='*60}")

    return data, analysis, decision


if __name__ == "__main__":
    main()
