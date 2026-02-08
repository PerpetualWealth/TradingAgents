# TradingAgents 自定义脚本

这个目录包含了使用自定义 OpenAI 兼容模型的 TradingAgents 入口脚本。

## 📁 文件说明

### `main.py`
**完整的 TradingAgents 分析**（标准配置）
- 使用所有 4 个分析师（市场、新闻、基本面、社交媒体）
- 标准辩论轮数
- 适合完整的深度分析

### `main.lite.py`
**轻量版 TradingAgents 分析**（快速配置）
- 使用所有 4 个分析师（市场、新闻、基本面、社交媒体）
- **辩论轮数: 1**（更快）
- **数据源: 全部 yfinance**（无需额外 API）
- 适合快速分析

## ⚙️ 配置说明

在项目根目录创建 `.env` 文件：

```bash
# OpenAI 兼容 API 配置
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://your-api-endpoint.com/v1

# 模型配置
DEEP_THINK_MODEL=your-deep-model-name
QUICK_THINK_MODEL=your-quick-model-name

# 可选：LLM 提供商（默认 openai）
LLM_PROVIDER=openai
```

## 🚀 使用方法

### main.py（完整分析）

```bash
# 使用默认配置
python sh/main.py --ticker NVDA

# 指定日期
python sh/main.py --ticker NVDA --date 2024-05-10
```

**特点**：
- 使用上游默认的数据源配置
- 标准辩论轮数
- 完整的多分析师分析

### main.lite.py（快速分析）

```bash
# 使用默认配置
python sh/main.lite.py --ticker NVDA

# 指定日期
python sh/main.lite.py --ticker NVDA --date 2024-05-10
```

**特点**：
- 辩论轮数: 1
- 所有数据源使用 yfinance（无需额外 API key）
- 快速完成分析

## 📊 输出

分析报告保存在：
```
eval_results/{TICKER}/TradingAgentsStrategy_logs/full_states_log_{DATE}.json
```

## 🔧 与上游 CLI 的区别

上游提供了交互式 CLI：
```bash
python cli/main.py
```

**自定义脚本的优势**：
- ✅ 直接使用 `.env` 配置（无需每次选择）
- ✅ 支持自定义 OpenAI 兼容 API
- ✅ 可以通过命令行参数快速运行
- ✅ 适合自动化和批量分析

## ⚡ main.py vs main.lite.py

| 特性 | main.py | main.lite.py |
|------|---------|--------------|
| 分析师 | 全部 4 个 | 全部 4 个 |
| 辩论轮数 | 标准配置 | 1 轮 |
| 数据源 | 上游默认 | 全部 yfinance |
| 执行时间 | 标准 | 更快 |
| 适用场景 | 标准分析 | 快速决策 |

## 📝 注意事项

1. **环境变量**：确保项目根目录有 `.env` 文件
2. **数据源**：
   - main.py 使用上游默认配置（可自定义）
   - main.lite.py 强制使用 yfinance
3. **模型**：两个脚本都支持自定义 OpenAI 兼容模型
4. **上游版本**：基于 v0.2.0，已支持 yfinance news 和 global_news

## 🔍 故障排查

### 问题：get_global_news 报错
**解决**：上游 v0.2.0 已修复，确保使用最新代码

### 问题：自定义 API 不工作
**解决**：检查 `.env` 中的 `OPENAI_BASE_URL` 配置

### 问题：找不到数据
**解决**：
- main.py: 检查上游默认配置
- main.lite.py: 确保 yfinance 可访问
