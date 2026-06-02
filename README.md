# lithe-jsonrpc

## 介绍
不只一个基于jsonrpc协议的接口层，还提供了应用程序所需基础设施集成；

```
Client → raw JSON
    │
    ├─[1]─ parse_request() → JsonRpcRequest.model_validate(data)
    │       Pydantic 直接校验: jsonrpc="2.0", id 类型, method 非空
    │
    ├─[2]─ MethodRegistry.dispatch(method, params, context)
    │       ├─ 根据 method 名查找 RpcMethod
    │       └─ RpcMethod.call(params, context)
    │
    ├─[3]─ call() 构建 kwargs dict
    │       ├─ list params → 按序映射到参数名
    │       ├─ dict params → 直接解包
    │       └─ 注入 JsonRpcContext（如果声明了）
    │
    ├─[4]─ self.func(**kwargs)  ← @inject 包装后的函数
    │       │
    │       └─ fast-depends 内部:
    │           ├─ a="3" + annot=int → Pydantic: "3"→3 ✓
    │           ├─ greeting=Depends(get_greeting) → resolve 依赖 → Pydantic 校验结果
    │           └─ user: CreateUserModel → Pydantic 深度校验嵌套字段
    │
    ├─[5]─ 原始函数执行，返回 result
    │
    └─[6]─ format_response(result, id) → JsonRpcResponse
            model_dump_json(exclude_none=True) → JSON → Client
```

### 第一层：协议引擎

| # | 功能 | lithe-jsonrpc | 证据 |
|---|------|:---:|------|
| 1 | 方法注册器 | ✅ | `@server.method()` + `MethodRegistry` [routing.py:91-93](packages/lithe-jsonrpc/lithe_jsonrpc/routing.py:91-93) |
| 2 | JSON-RPC 2.0 编解码 | ✅ | Pydantic 模型：`Request`/`Response`/`Error`/`Notification`，四种结构全齐 [protocol.py:14-76](packages/lithe-jsonrpc/lithe_jsonrpc/protocol.py:14-76) |
| 3 | 参数解析器 | ✅ | positional list → `*args` / keyword dict → `**kwargs` [routing.py:81-108](packages/lithe-jsonrpc/lithe_jsonrpc/routing.py:81-108) |
| 4 | 返回值序列化 | ✅ | `format_response()` + `to_json(exclude_none=True)` [protocol.py:94-100](packages/lithe-jsonrpc/lithe_jsonrpc/protocol.py:94-100) |
| 5 | 标准错误映射 | ✅ | 五个标准码：-32700/-32600/-32601/-32602/-32603，异常体系完整 [errors.py:27-95](packages/lithe-jsonrpc/lithe_jsonrpc/errors.py:27-95) |
| 6 | 消息分帧 | ✅ | 换行符 `\n` 分隔 [stdio.py:55](packages/lithe-jsonrpc/lithe_jsonrpc/transport/stdio.py:55) |

### 第二层：应用基础设施

| # | 功能 | lithe-jsonrpc | 证据 |
|---|------|:---:|------|
| 7 | 生命周期钩子 | ✅ | `@server.lifespan()` async generator [lifespan.py:33-39](packages/lithe-jsonrpc/lithe_jsonrpc/lifespan.py:33-39) |
| 8 | 请求上下文 | ✅ | `JsonRpcContext` — 含 `method`/`request_id`/`transport`/`notify()` [context.py:10-33](packages/lithe-jsonrpc/lithe_jsonrpc/context.py:10-33) |
| 9 | 依赖注入 | ✅ | `fast-depends` 的 `Depends()`，**和 FastAPI 同一引擎** [routing.py:17-19](packages/lithe-jsonrpc/lithe_jsonrpc/routing.py:17-19) |
| 10 | 中间件管道 | ✅ | `@server.middleware` + `MiddlewareStack`，标准 `call_next` 洋葱模型 [middleware.py:53-70](packages/lithe-jsonrpc/lithe_jsonrpc/middleware.py:53-70) |
| 11 | 自定义业务错误 | ✅ | `ServerDefinedError(code, message, data)`，-32000~-32099 [errors.py:88-100](packages/lithe-jsonrpc/lithe_jsonrpc/errors.py:88-100) |
| 12 | 类型校验 | ✅ | Pydantic 自动校验，通过 `fast-depends` 的 `@inject` [routing.py:42](packages/lithe-jsonrpc/lithe_jsonrpc/routing.py:42) |
| 13 | 通知支持 | ✅ | `request.is_notification` + `_handle_notification` [server.py:164-176](packages/lithe-jsonrpc/lithe_jsonrpc/server.py:164-176) |
| 14 | 批量请求 | ✅ | `parse_request()` 检测数组 → 逐个 dispatch [protocol.py:58-65](packages/lithe-jsonrpc/lithe_jsonrpc/protocol.py:58-65) |

### 第三层：运维与生产化

| # | 功能 | lithe-jsonrpc | 说明 |
|---|------|:---:|------|
| 15 | 方法自省 | ⚠️ | demo 里有 `system.listMethods`，但非内置。可以 3 行加到 `Lithe.__init__` |
| 16 | Schema 导出 | ❌ | 未实现，但 Pydantic v2 可以 `model_json_schema()` 自动生成，容易加 |
| 17 | 超时控制 | ❌ | 未实现，可以在中间件层添加 |
| 18 | 后台任务 | ❌ | 未实现，可以用 anyio task group 在 lifespan 中管理 |
| 19 | 传输层抽象 | ✅ | `Transport` ABC + stdio + WebSocket 双实现 [transport/](packages/lithe-jsonrpc/lithe_jsonrpc/transport/) |
| 20 | 心跳保活 | ⚠️ | 未内置，但 `ping` 方法一行搞定 |
| 21 | 日志追踪 | ⚠️ | 未内置，在中间件中加 trace_id 即可 |
| 22 | 优雅关闭 | ✅ | lifespan `yield` → cleanup + stdin EOF → break [server.py:175-178](packages/lithe-jsonrpc/lithe_jsonrpc/server.py:175-178) |