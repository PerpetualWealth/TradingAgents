import json
import sys
import os
from datetime import date
from pathlib import Path
from openai import OpenAI

OPEN_THINK_TAGS = ("<thinking>", "<think>")
CLOSE_THINK_TAGS = ("</thinking>", "</think>")
ALL_THINK_TAGS = OPEN_THINK_TAGS + CLOSE_THINK_TAGS
MAX_THINK_TAG_LEN = max(len(tag) for tag in ALL_THINK_TAGS)

# Configuration from environment
BASE_URL = os.getenv("TRANSLATE_BASE_URL", "https://api.openai.com/v1")
API_KEY = os.getenv("TRANSLATE_API_KEY")
MODEL = os.getenv("TRANSLATE_MODEL", "gpt-4o")

# Initialize client
try:
    if API_KEY:
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    else:
        client = None
        print("*(Warning: TRANSLATE_API_KEY not set)*", file=sys.stderr)
except Exception as e:
    print(f"*(Failed to initialize client: {str(e)})*", file=sys.stderr)
    client = None


def _find_next_tag(text, tags):
    lowered = text.lower()
    best_idx = -1
    best_tag = None

    for tag in tags:
        idx = lowered.find(tag)
        if idx != -1 and (best_idx == -1 or idx < best_idx):
            best_idx = idx
            best_tag = tag

    return best_idx, best_tag


class ThinkTagFilter:
    """流式过滤 <thinking>/<think> 标签及其内容。"""

    def __init__(self):
        self.buffer = ""
        self.in_think_block = False

    def feed(self, content, finalize=False):
        self.buffer += content
        output_chunks = []

        while self.buffer:
            if self.in_think_block:
                close_idx, close_tag = _find_next_tag(self.buffer, CLOSE_THINK_TAGS)
                if close_idx == -1:
                    if finalize:
                        # 文件结束时仍未闭合，直接丢弃剩余思考内容。
                        self.buffer = ""
                    elif len(self.buffer) > MAX_THINK_TAG_LEN:
                        # 保留一个标签长度的尾巴，防止标签跨 chunk 被截断。
                        self.buffer = self.buffer[-(MAX_THINK_TAG_LEN - 1):]
                    return "".join(output_chunks)

                self.buffer = self.buffer[close_idx + len(close_tag):]
                self.in_think_block = False
                continue

            next_idx, next_tag = _find_next_tag(self.buffer, ALL_THINK_TAGS)
            if next_idx == -1:
                if finalize:
                    output_chunks.append(self.buffer)
                    self.buffer = ""
                else:
                    safe_len = max(0, len(self.buffer) - (MAX_THINK_TAG_LEN - 1))
                    if safe_len > 0:
                        output_chunks.append(self.buffer[:safe_len])
                        self.buffer = self.buffer[safe_len:]
                return "".join(output_chunks)

            if next_idx > 0:
                output_chunks.append(self.buffer[:next_idx])

            self.buffer = self.buffer[next_idx + len(next_tag):]
            if next_tag in OPEN_THINK_TAGS:
                self.in_think_block = True

        return "".join(output_chunks)

    def flush(self):
        return self.feed("", finalize=True)


def translate_report(ticker, report_date, json_path, output_file):
    # Read JSON
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Report file not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    # Extract content
    day_data = data.get(report_date, {})
    if not day_data:
        key = list(data.keys())[0]
        day_data = data[key]

    fundamentals = day_data.get("fundamentals_report", "No data")
    market = day_data.get("market_report", "No data")
    sentiment = day_data.get("sentiment_report", "No data")
    news = day_data.get("news_report", "No data")
    investment_decision = day_data.get("trader_investment_decision", "No data")
    investment_plan = day_data.get("investment_plan", "No data")
    final_trade_decision = day_data.get("final_trade_decision", "No data")

    investment_debate = day_data.get("investment_debate_state", {})
    investment_judge = investment_debate.get("judge_decision", "No data")

    risk_debate = day_data.get("risk_debate_state", {})
    risk_judge = risk_debate.get("judge_decision", "No data")

    combined_content = f"""
=== FUNDAMENTALS ===
{fundamentals}

=== TECHNICAL ===
{market}

=== SENTIMENT ===
{sentiment}

=== NEWS ===
{news}

=== INVESTMENT DECISION ===
{investment_decision}

=== INVESTMENT PLAN ===
{investment_plan}

=== FINAL TRADE DECISION ===
{final_trade_decision}
"""

    if client is None:
        print("*(Translation failed: OpenAI client not initialized)*", file=sys.stderr)
        sys.exit(1)

    system_prompt = f"""你是一位专业的金融分析师和翻译专家，擅长将英文股票分析报告翻译为专业、流畅的中文。

## 翻译任务
用户将提供一份用 `=== SECTION NAME ===` 分隔的英文分析报告，你需要将其完整翻译为中文。

## 输出格式要求

### 整体结构
输出以下 Markdown 结构（注意章节使用二级标题）：

# 📈 {ticker} 深度分析报告 ({report_date})

## 1. 基本面分析
[翻译 FUNDAMENTALS 章节]

## 2. 市场与技术面分析
[翻译 TECHNICAL 章节]

## 3. 情绪与舆论分析
[翻译 SENTIMENT 章节]

## 4. 新闻与宏观分析
[翻译 NEWS 章节]

## 5. 投资决策
[翻译 INVESTMENT DECISION 章节]

## 6. 投资计划
[翻译 INVESTMENT PLAN 章节]

## 7. 最终交易决策
[翻译 FINAL TRADE DECISION 章节]

### 标题层级规范化（重要！）
为了保证整份报告的层级正确，**每个章节内部的所有标题必须从三级标题开始**：

- 原文的一级标题 `#` → 翻译为三级标题 `###`
- 原文的二级标题 `##` → 翻译为四级标题 `####`
- 原文的三级标题 `###` → 翻译为五级标题 `#####`
- 以此类推...

**原因**：章节本身已经是二级标题，章节内的标题必须低于二级，从三级开始，否则会导致层级混乱。

### 其他要求
1. **完整性**：翻译所有内容，不要总结或省略任何信息
2. **专业性**：使用准确的金融术语和专业语调
3. **格式**：纯 Markdown 输出，不要使用代码块（不要用 ```markdown 包裹）
4. **纯净输出**：只输出翻译后的报告内容，不要添加任何签名、注释或页脚
"""

    user_prompt = combined_content

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_completion_tokens=64000,
        stream=True
    )

    think_filter = ThinkTagFilter()

    # Stream output to file, filtering thinking/think tags
    with open(output_file, 'w') as f:
        for chunk in response:
            if chunk.choices[0].delta.content:
                content_piece = chunk.choices[0].delta.content
                # 过滤 thinking/think 标签内容
                # filtered_content = think_filter.feed(content_piece)
		#if filtered_content:
                #    print(filtered_content, end="", flush=True, file=f)
                
                print(content_piece, end="", flush=True, file=f)

        tail_content = think_filter.flush()
        if tail_content:
            print(tail_content, end="", flush=True, file=f)

        # Fixed footer
        footer = "\n\n---\n*Generated by Genius ⚡*\n"
        print(footer, flush=True, file=f)


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python translate_report.py <ticker> <date> <json_file> <output_file>", file=sys.stderr)
        sys.exit(1)

    ticker = sys.argv[1]
    report_date = sys.argv[2]
    json_path = sys.argv[3]
    output_file = sys.argv[4]

    translate_report(ticker, report_date, json_path, output_file)
