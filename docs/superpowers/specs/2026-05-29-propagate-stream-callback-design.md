# Design: Expose Stream Chunks from propagate() via Callback

## Problem

`TradingAgentsGraph.propagate()` encapsulates the full analysis lifecycle (memory resolution → graph execution → logging → memory storage), but its internal `_run_graph()` method consumes the `graph.stream()` iterator directly. Callers that need real-time chunks (SSE API) must bypass `propagate()` entirely, losing memory resolution, state logging, decision storage, and checkpoint support.

## Solution

Add an optional `on_chunk` callback parameter to `propagate()` and `_run_graph()`. When provided, each stream chunk is passed to the callback before internal processing. Existing callers pass nothing and are unaffected.

## Changes

### `tradingagents/graph/trading_graph.py`

**`propagate()`** — add `on_chunk` parameter, forward to `_run_graph()`:

```python
def propagate(self, company_name, trade_date, on_chunk=None):
    ...
    return self._run_graph(company_name, trade_date, on_chunk=on_chunk)
```

**`_run_graph()`** — add `on_chunk` parameter, invoke per chunk:

```python
def _run_graph(self, company_name, trade_date, on_chunk=None):
    ...
    if self.debug:
        for chunk in self.graph.stream(...):
            if on_chunk:
                on_chunk(chunk)
            chunk["messages"][-1].pretty_print()
            trace.append(chunk)
        final_state = trace[-1]
    else:
        final_state = self.graph.invoke(...)
    ...
```

Non-debug (`graph.invoke()`) path ignores `on_chunk` since there are no intermediate chunks.

### `api/sse.py`

Replace direct `graph.graph.stream()` call with `graph.propagate(on_chunk=...)`. The `on_chunk` callback feeds graph chunks into the SSE event processor and queue, while tool events continue flowing through the existing `SSEStreamCallback` passed via `get_graph_args(callbacks=[...])`.

`_run_stream_in_thread` becomes:

```python
def _run_stream_in_thread(graph, ticker, trade_date, analysts, loop, queue):
    processor = SSEEventProcessor(ticker, analysts, graph)
    stream_callback = SSEStreamCallback(ticker, processor, loop, queue)

    def on_chunk(chunk):
        raw = {"event_type": "graph_chunk", "data": chunk}
        for event in processor.process_raw_event(raw):
            loop.call_soon_threadsafe(queue.put_nowait, event)

    args = graph.propagator.get_graph_args(callbacks=[stream_callback])

    try:
        graph.propagate(ticker, trade_date, on_chunk=on_chunk)
    except Exception as e:
        loop.call_soon_threadsafe(queue.put_nowait, _make_event("error", ticker, message=str(e)))
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, None)
```

Key detail: `get_graph_args(callbacks=[...])` must be called before `propagate()` so the SSEStreamCallback is active during graph execution. `propagate()` internally calls `_run_graph()` which calls `self.graph.stream(init_state, **args)` — the `args` (with callbacks) need to be injected. Since `propagate()` calls `self.propagator.get_graph_args()` internally without callbacks, we need to pass callbacks through or override args. Simplest: set `graph.propagator` args externally before calling propagate, or pass callbacks into propagate.

### No changes to

- `start/main.py` — calls `propagate()` without `on_chunk`, unchanged
- `api/server.py` POST `/analyze/sync` — calls `propagate()` without `on_chunk`, unchanged
- `api/mcp_tool.py` — calls `propagate()` without `on_chunk`, unchanged
- `main.py` — calls `propagate()` without `on_chunk`, unchanged

## Open Issue: Callbacks Injection

`propagate()` → `_run_graph()` internally calls `self.propagator.get_graph_args()` without callbacks. For the SSE path, `SSEStreamCallback` must be in the graph args. Two options:

1. Add `callbacks` parameter to `propagate()`, forward through `_run_graph()` to `get_graph_args()`
2. Pre-set args on the propagator before calling `propagate()`

Option 1 is cleaner. `propagate()` and `_run_graph()` get an optional `callbacks` parameter that defaults to `None` (uses `get_graph_args()` as before).

Final signatures:

```python
def propagate(self, company_name, trade_date, on_chunk=None, callbacks=None):
def _run_graph(self, company_name, trade_date, on_chunk=None, callbacks=None):
```

## Impact

- SSE events: unchanged in type and count
- API behavior: gains memory resolution, state logging, decision storage, checkpoint support
- CLI behavior: completely unchanged
- Other API endpoints: completely unchanged
