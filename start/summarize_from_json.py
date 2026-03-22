#!/usr/bin/env python3
"""
直接从英文JSON报告生成中文摘要，避免翻译损失
使用TRANSLATE_MODEL配置，保持灵活性
"""
import json
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# 加载.env文件
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

# Configuration from environment (与summarize_notification.py保持一致)
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


def log(msg):
    """调试日志"""
    print(f"[summarize_from_json] {msg}", file=sys.stderr)


def is_minimax_model(model: str) -> bool:
    """检查是否是 MiniMax 模型"""
    return model.lower().startswith("minimax")


def extract_key_data(json_file):
    """从JSON中提取关键数据，减少上下文需求"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 提取日期和股票代码
        date = list(data.keys())[0]
        analysis_data = data[date]

        ticker = analysis_data.get('company_of_interest', 'N/A')
        trade_date = analysis_data.get('trade_date', date)

        # 提取关键分析结果
        market_report = analysis_data.get('market_report', '')
        final_decision = analysis_data.get('decision', 'N/A')
        risk_assessment = analysis_data.get('risk_assessment', '')

        # 构建精简的内容用于摘要
        key_content = f"""
股票代码: {ticker}
分析日期: {trade_date}

## 市场分析报告
{market_report[:15000]}  # 限制长度，避免上下文过大

## 投资决策
{final_decision}

## 风险评估
{risk_assessment[:5000]}
"""

        return {
            'ticker': ticker,
            'date': trade_date,
            'content': key_content,
            'raw_data': analysis_data
        }

    except Exception as e:
        log(f"JSON解析失败: {e}")
        return None


def summarize_from_json(json_file, output_file):
    """直接从JSON生成中文摘要"""
    if client is None:
        msg = "⚠️ 配置错误: OpenAI client 未初始化，请检查 TRANSLATE_API_KEY"
        log(msg)
        return msg

    # 提取关键数据
    key_data = extract_key_data(json_file)
    if not key_data:
        return "⚠️ JSON数据解析失败"

    ticker = key_data['ticker']
    content = key_data['content']

    log(f"开始处理 {ticker} 的摘要生成...")
    log(f"使用模型: {MODEL}")
    log(f"内容长度: {len(content)} 字符")

    # 检查内容大小，避免超过上下文限制
    content_size_kb = len(content.encode('utf-8')) / 1024
    log(f"内容大小: {content_size_kb:.1f} KB")

    if content_size_kb > 100:  # 如果内容过大，发出警告
        log(f"⚠️  内容较大({content_size_kb:.1f}KB)，可能接近上下文限制")

    system_prompt = """你是一位专业的金融报告总结专家，擅长直接从英文股票分析JSON数据中提炼核心信息，为投资者生成简洁、高价值的决策摘要。

## 核心要求
**输出语言：中文（简体）**
**输出格式：纯文本，不要使用 Markdown 代码块**
**数据来源：直接分析提供的英文JSON数据，不要依赖已翻译的内容**

## 输出格式要求

### 整体结构
严格按照以下顺序和格式输出：

🎯 **最终决策**: [买入/持有/卖出]，简要理由。

🏢 **基本面精要**
- 核心观点1
- 核心观点2
- 核心观点3
- 核心观点4（可选）

📈 **技术面精要**
- 关键信号1
- 关键信号2
- 关键信号3
- 关键信号4（可选）

📰 **新闻与情绪**
- 重要新闻或市场情绪1
- 重要新闻或市场情绪2
- 重要新闻或市场情绪3（可选）

### 格式规范
1. 每个标题前后必须空一行
2. 列表用 `•`
3. 纯净输出，不要开场白和签名
4. 直接从英文数据提取信息，确保准确性

## 重要提示
- 你分析的是原始英文数据，不是翻译后的内容
- 确保投资决策、数字、技术指标的准确性
- 如果JSON中没有某些信息，标注"数据中无此信息"
- 保持专业术语的准确性
- 输出格式必须与现有摘要格式完全一致"""

    try:
        log("发送API请求...")

        # 构建请求参数
        create_params = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            "max_completion_tokens": 4000,
            "temperature": 0.3,
            "stream": True
        }

        # MiniMax: 使用 reasoning_split 分离思考内容
        if is_minimax_model(MODEL):
            create_params["extra_body"] = {"reasoning_split": True}

        response = client.chat.completions.create(**create_params)

        # 处理流式响应
        full_response = ""
        for chunk in response:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content

        summary = full_response.strip()
        log("摘要生成成功")

        # 保存到文件
        header = f"🔔 **{ticker} 分析完成！**\n\n"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(header + summary)

        log(f"摘要已保存到: {output_file}")
        return summary

    except Exception as e:
        error_msg = f"⚠️ 摘要生成失败: {str(e)}"
        log(error_msg)
        return error_msg


def main():
    if len(sys.argv) < 4:
        print("Usage: summarize_from_json.py <TICKER> <DATE> <JSON_FILE> [OUTPUT_FILE]", file=sys.stderr)
        sys.exit(1)

    ticker = sys.argv[1]
    date = sys.argv[2]
    json_file = sys.argv[3]

    # 默认输出文件路径
    default_output = f"/tmp/summary_{ticker}_{date}.txt"
    output_file = sys.argv[4] if len(sys.argv) > 4 else default_output

    result = summarize_from_json(json_file, output_file)

    if result.startswith("⚠️"):
        sys.exit(1)


if __name__ == "__main__":
    main()
