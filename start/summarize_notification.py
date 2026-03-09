import sys
import os
from openai import OpenAI

# Force UTF-8 for stdin/stdout
try:
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass


def log(msg):
    # Silence debug output
    pass


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


def summarize_for_notification(full_report_md, ticker, date, output_file):
    if client is None:
        msg = "⚠️ 配置错误: OpenAI client 未初始化，请检查 TRANSLATE_API_KEY"
        log(msg)
        return msg

    if not full_report_md.strip():
        msg = "⚠️ 报告内容为空，无法生成摘要。"
        log(msg)
        return msg

    system_prompt = """你是一位专业的金融报告总结专家，擅长从长篇股票分析报告中提炼核心信息，为投资者生成简洁、高价值的决策摘要。

## 核心要求
**输出语言：中文（简体）**
**输出格式：纯文本，不要使用 Markdown 代码块**

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
3. 纯净输出，不要开场白和签名"""

    try:
        log("Sending request to API...")
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_report_md}
            ],
            max_completion_tokens=4000
        )
        content = response.choices[0].message.content.strip()
        log("Response received successfully.")

        # 保存到文件（头部加固定标题），覆盖已存在的文件
        header = f"🔔 **{ticker} 分析完成！**\n\n"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(header + content)

    except Exception as e:
        msg = f"⚠️ 摘要生成失败: {str(e)}"
        log(msg)
        print(msg)
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        # 读取参数
        if len(sys.argv) >= 4:
            ticker = sys.argv[1]
            date = sys.argv[2]
            output_file = sys.argv[3]
        else:
            ticker = "UNKNOWN"
            date = "UNKNOWN"
            output_file = "/tmp/summary_UNKNOWN.txt"

        full_report = sys.stdin.read()
        log(f"Read {len(full_report)} chars for {ticker}/{date}")
        summarize_for_notification(full_report, ticker, date, output_file)
    except Exception as e:
        log(f"Critical Error: {str(e)}")
        print(f"⚠️ 脚本执行错误: {str(e)}")
        sys.stdout.flush()
