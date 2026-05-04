本工程是fork自上游开源项目，用于Agent分析股票

fork后主要修改位于start目录

当用户要求执行分析股票时，如"分析NVDA"，"微软可能买吗？"等股票分析意图，阅读`start/SKILL.md`的说明，严格使用SKILL.md的要求使用tmux不阻塞的方式进行运行分析

## API Server

启动 SSE API 服务：

```bash
python -m api.server
```

SSE 实时分析：

```bash
curl -N -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2024-05-10"}'
```

MCP Tool（用于 Cursor/Claude 等 AI 编程助手）：

```json
{
  "mcpServers": {
    "trading-agents": {
      "command": "python",
      "args": ["-m", "api.mcp_tool"]
    }
  }
}
```

