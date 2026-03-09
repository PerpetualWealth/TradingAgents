---
name: trading-agents
description: 使用 AI 代理团队对股票进行基本面和技术面分析
metadata:
  {
    "openclaw":
      {
        "emoji": "📈",
        "requires": { "bins": ["bash", "python3"] },
      },
  }
---

# Trading Agents 股票分析

使用 AI 代理团队对股票进行基本面和技术面分析。

## 使用方法

当用户要求分析股票时（如"分析 IONQ"、"解读NVDA股票"），在 main session 中通过tmux执行本工程的start目录的analyze.sh：特别注意：
- 一定在main里运行，不能在subagent里运行，因为subagent里不能发送消息
- 一定要用tmux执行analyze.sh，不能直接运行，因为分析过程会在10-30分钟，会被系统可exec给kill掉

### 具体Workflow：

#### 1. 从用户问题里推理出用户要分析的股票代码和日期
股票代码必须有，用户可以直接提供也可能只说公司名，需要推理出Ticker
日期可能为空，为空则用今天

**⚠️ 重要：关于日期**
- **禁止硬编码日期！** 必须通过 `session_status` 工具获取当天的真实日期
- 日期格式：`YYYY-MM-DD`（如 `2026-02-21`）
- tmux 会话名用 `YYYYMMDD` 格式（如 `analyze-MU-20260221`）

#### 2. 用tmux执行分析
```bash
TRADING_AGENTS_DIR=工程目录
tmux new-session -d -s "analyze-<股票代码>-<日期YYYYMMDD>" "bash $TRADING_AGENTS_DIR/start/analyze.sh —ticker <股票代码> [...其它参数]"
```
具体analyze.sh用法下文有说明

#### 3. 结果处时
tmux启动后不需要再等执行结果，在analyze.sh里会自动通知用户，一但tmux启动就算完成了，不需要等待

## analyze.sh 功能说明与用法
analyze.sh 脚本会：
1. 运行 AI 代理分析（10-30 分钟）
2. 生成中文报告并保存到知识库，如Obsidian
3. 生成摘要文件
4. 通知用户摘要内容

## 参数说明

```bash
./analyze.sh --ticker TICKER [--date DATE] [--ignore-existing false|true]
```

- `--ticker`: 股票代码（必需），如 `MSFT`、`NVDA`、`IONQ`
- `--date`: 分析日期（可选），格式 `YYYY-MM-DD`，默认为今天
- `--ignore-existing`: 是否忽略缓存（可选），值为 `false` 或 `true`，默认为 `false`

**⚠️ 重要：关于 `--ignore-existing` 参数**

- 默认情况（以及绝大多数情况）：**不要传递** `--ignore-existing` 参数，让脚本使用默认值 `false`
- 只有当用户**明确说出"重新生成"**这 4 个字**时，才使用 `--ignore-existing true`

**正确示例：**
- 用户说"分析微软" → 执行 `./analyze.sh --ticker MSFT`
- 用户说"微软重新生成" → 执行 `./analyze.sh --ticker MSFT --ignore-existing true`
- 用户说"再分析一次MSFT" → 执行 `./analyze.sh --ticker MSFT`

**错误示例：**
- ❌ 用户说"分析微软" → 执行 `./analyze.sh --ticker MSFT --ignore-existing false`（不要传递默认值）

## ⏱️ 执行时间

- AI 代理分析通常需要 **10-30 分钟**
- 请耐心等待

### 跟进执行进度
使用tmux查询会话以及attach到会话中查看运行情况

```bash
# 1. 查看tmux会话列表
tmux ls-sessions

# 2. 查看会话输出（attach到会话）
tmux attach -t <会话名>
```

注意：脚本会自动退出tmux会话，通常不需要手动查看。如需查看输出，可使用上述命令。
