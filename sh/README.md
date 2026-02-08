# TradingAgents 自定义脚本

这个目录包含了使用自定义 OpenAI 兼容模型的脚本。

## 📁 文件说明

### `main.py`
- **用途**：完整的 TradingAgents 分析框架
- **数据源**：yfinance（上游默认）
- **特点**：
  - 使用多个分析师（市场、新闻、基本面、社交媒体）
  - 支持辩论机制
  - 生成详细的多角度分析报告
  - 自动风险管理和决策

### `main.lite.py`
- **用途**：轻量版快速分析
- **数据源**：yfinance（直接调用）
- **特点**：
  - 单次 LLM 调用
  - 快速生成技术分析报告
  - 适合快速决策

## ⚙️ 配置说明

在项目根目录创建 `.env` 文件：

```bash
# OpenAI 兼容 API 配置
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://your-api-endpoint.com/v1

# 模型配置
DEEP_THINK_MODEL=your-model-name
QUICK_THINK_MODEL=your-model-name

# 可选：LLM 提供商（默认 openai）
LLM_PROVIDER=openai
```

## 🚀 使用方法

### 使用 main.py（完整分析）

```bash
# 使用默认配置
python sh/main.py --ticker NVDA

# 指定日期
python sh/main.py --ticker NVDA --date 2024-05-10
```

### 使用 main.lite.py（快速分析）

```bash
# 基本使用
python sh/main.lite.py --ticker NVDA

# 指定历史天数
python sh/main.lite.py --ticker NVDA --days 60

# 显示完整报告
python sh/main.lite.py --ticker NVDA --output
```

## 📊 输出

分析报告保存在：
```
eval_results/{TICKER}/TradingAgentsStrategy_logs/full_states_log_{DATE}.json
```

## 🔧 与上游的主要区别

1. **模型配置**：使用自定义 OpenAI 兼容 API
2. **数据源**：默认使用 yfinance（上游已支持）
3. **简化配置**：移除了不必要的 data_vendors 配置

## ⚡ 性能对比

| 特性 | main.py | main.lite.py |
|------|---------|--------------|
| 分析深度 | 深（多分析师） | 浅（单次 LLM） |
| 执行时间 | 较长 | 快速 |
| API 调用 | 多次 | 1次 |
| 适用场景 | 深度研究 | 快速决策 |

## 📝 注意事项

- 确保 `.env` 文件配置正确
- main.py 需要完整的 TradingAgents 框架
- main.lite.py 是独立脚本，不依赖框架
- 上游 v0.2.0 已默认使用 yfinance，无需额外配置数据源
