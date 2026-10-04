# LangGraph Redesign: Low-Level Design and Implementation Plan

## 1. Objective

Replace Icebreaker's hand-written Responses API/tool-call loop with a LangGraph agent flow while preserving the existing OpenAI Responses API integration, MCP servers, active skills, Rich terminal UI, conversation logging, and cancellation behavior.

The custom LangChain chat model will continue to call `client.responses.create(...)`. Conversation context will be continued using the Responses API's `previous_response_id`; LangGraph will persist that ID alongside its conversation state and isolate it by thread.

## 2. Current behavior

The current request path is implemented primarily in `config.py::InputHandler`:

1. The CLI collects a user message.
2. `InputHandler._generate_response()` sends the request using `AsyncOpenAI.responses.create`.
3. Active skill instructions and MCP function schemas are attached to the request.
4. The method streams text and reasoning events directly to the Rich UI.
5. If the response contains function calls, the method calls `MCPManager.call_tool()` and appends function-call outputs to the next Responses API request.
6. The method repeats up to eight tool-call rounds, then returns the answer to `handle_input()` for display/history/logging.

`main.py::run()` creates the OpenAI client, skills manager, MCP manager, input session, and input handler. MCP connections are disconnected when the CLI exits.

## 3. Proposed architecture

```text
Rich CLI / InputHandler
  ├─ owns slash commands, input, display history, UI, cancellation, and logging
  ├─ provides user message, skill prompt, and stable conversation thread ID
  └─ invokes compiled LangGraph
       ├─ agent_node
       │    └─ ResponsesChatModel (custom LangChain BaseChatModel)
       │         └─ AsyncOpenAI.responses.create
       ├─ ToolNode
       │    └─ LangChain MCP tools
       │         └─ MCPManager.call_tool
       └─ checkpointer: messages + latest completed Responses response ID
```

Graph routing:

```text
START → agent
agent → tools when tool calls are present
agent → END when there are no tool calls
 tools → agent
```

LangGraph manages control flow and checkpointed state. The Responses API remains the authority for server-side model context. The graph must not resend the full historical conversation on every model request when a valid `previous_response_id` is available.

## 4. Design decisions and invariants

1. **Per-thread response ID:** The latest completed Responses API response ID is stored in LangGraph state and checkpointed with that thread. Never store a single global response ID on the model instance.
2. **Incremental input:** For each model call, send only the new user message or tool outputs that follow the previous model response. Do not resend all graph messages together with `previous_response_id`.
3. **Tool continuation:** A Responses API function call is represented as a LangChain tool call. `ToolNode` executes it. The next Responses API request uses the response ID that requested the tool and sends corresponding function-call output items.
4. **Commit response ID on completion:** A new ID is saved only after a complete response has been received. Failed, cancelled, or incomplete streams leave the last completed ID unchanged.
5. **Instructions are per request:** Include the active system/skill instructions in each Responses API call unless endpoint behavior has been explicitly verified to persist them.
6. **MCP remains the connection owner:** `MCPManager` continues to manage server lifecycle, server configuration, namespacing, and actual MCP calls. LangChain tools adapt its existing tool index; they do not establish duplicate MCP connections.
7. **UI stays outside the graph:** Rich rendering, commands, input handling, and logs remain in the CLI layer.
8. **Thread reset:** Reset must either clear the checkpointer state and associated response ID or assign a new thread ID. It must not accidentally continue the old server-side response chain.

## 5. Proposed modules and responsibilities

### 5.1 `responses_chat_model.py` (new)

Contains the custom LangChain chat model and API conversions.

#### `ResponsesChatModel.__init__(client, model, ...)`

- Store the existing `AsyncOpenAI` client and model name.
- Store safe default request options.
- Do not store mutable per-thread state on the model instance.
- Accept invocation-specific values through LangChain runnable config or explicit model-call options: `previous_response_id`, tools, and system instructions.

#### `_llm_type`

Return a stable model identifier such as `openai-responses`.

#### `_identifying_params`

Return non-secret model-identifying metadata. Never expose API keys or credential-bearing headers.

#### `_agenerate(messages, ...)`

Primary model operation:

1. Read request options and per-call metadata.
2. Convert the provided incremental LangChain messages into Responses API input items.
3. Build `responses.create` parameters, including `model`, `input`, optional `previous_response_id`, instructions, and tools.
4. Await the API request.
5. Convert the completed response to `AIMessage`.
6. Return response ID in `AIMessage.response_metadata` (or equivalent safe metadata), together with usage and finish information if available.
7. Do not mutate shared model state.

If synchronous calls are not needed, implement the sync generation method to fail with a clear unsupported-operation error rather than starting a nested event loop.

#### `_astream(messages, ...)` (later milestone)

- Translate Responses API events into LangChain text chunks.
- Buffer required structured output such as tool calls and response ID.
- Emit/record response ID only once a completion event arrives.
- Ensure cancellation closes the underlying API stream.
- Do not advance the saved ID after an incomplete or failed stream.

### 5.2 `responses_converters.py` (new or kept private to model module)

Keep format conversion independently testable.

#### `messages_to_response_input(messages)`

Convert only new messages for the current model call:

- `HumanMessage` → Responses API user input.
- `ToolMessage` → `function_call_output`, preserving the matching tool call ID.
- Any explicitly supported additional message types → documented Responses API item format.
- Unsupported message type → clear conversion exception.

For tool results, ensure the expected association between the output and the original function call is preserved. Confirm exact input item shape against the installed OpenAI SDK and target server.

#### `response_to_ai_message(response)`

- Collect response text into message content.
- Convert each Responses API function call to a LangChain tool call, preserving name, ID, and arguments.
- Parse arguments and validate they are JSON objects; surface malformed arguments clearly.
- Attach `response.id` as `response_metadata["response_id"]`.
- Preserve relevant usage and finish metadata when available.

#### `tools_to_responses_format(tools)`

Convert LangChain tool schemas into Responses API function definitions. Validate names, descriptions, and JSON schemas. Retain MCP-qualified names and ensure each tool schema is supported by the endpoint.

### 5.3 `langchain_mcp_tools.py` (new)

#### `build_langchain_mcp_tools(mcp_manager)`

For each discovered MCP binding:

- Create a LangChain async tool using the existing tool name, description, and input schema.
- Keep an explicit mapping from qualified LangChain tool name to MCP server and original MCP tool name.
- Implement the tool coroutine by calling `mcp_manager.call_tool(qualified_name, arguments)` or an equivalent existing binding operation.
- Preserve `MCPManager` timeout, output truncation, and error behavior.
- Avoid duplicate MCP connections or bypassing `MCPManager` lifecycle.

Check LangChain tool schema/API requirements against the versions selected in the dependency files before implementing. Prefer the project's already-available schema support; add only the dependencies required for LangChain, LangGraph, and the chosen MCP adapter if one is used.

### 5.4 `agent_graph.py` (new)

#### `AgentState`

State fields:

- `messages`: LangGraph message list using an append/update reducer such as `add_messages`.
- `response_id`: latest successfully completed Responses API response ID for this thread, or `None` initially.
- `system_prompt`: base prompt with the active skill instructions for the current invocation, if stored in state.

Avoid placing secrets, API clients, or MCP client objects in checkpointed state. Those remain runtime dependencies injected into graph nodes.

#### `get_new_messages(messages)`

Return only messages that have not yet been sent to Responses API. This boundary is essential because LangGraph retains full history while the Responses API chain is continued by ID.

Expected cases:

- First turn: return the new user message(s).
- Tool continuation: return all tool result messages produced since the assistant message that requested them.
- Next user turn: return the new user message, not prior assistant/user history.

The implementation must correctly handle multiple parallel tool calls and their multiple `ToolMessage` results. If selecting by message position proves ambiguous, add an explicit cursor/last-consumed marker to graph state and update it only after successful model submission. Document the chosen approach and test it for retries and failures.

#### `agent_node(state, config)`

1. Read `thread_id` from LangGraph configurable runtime settings as needed for diagnostics; use checkpointed state—not a model-global dictionary—for context.
2. Select incremental messages with `get_new_messages`.
3. Read `state["response_id"]`.
4. Invoke the custom chat model with the incremental messages, current instructions, and prior response ID.
5. Append returned `AIMessage` to state.
6. Copy the completed response ID from the AI message metadata to `state["response_id"]`.
7. If model invocation fails or is cancelled, preserve the prior ID and propagate/return a meaningful error according to graph error policy.

Use a LangChain-supported per-invocation config mechanism or explicit wrapper method for request-specific options. Do not mutate shared model configuration between concurrent threads.

#### Tool routing

Use the LangGraph tool-call condition (or an equivalent small routing function) to inspect the last AI message:

- Tool calls present → `tools` node.
- No tool calls → `END`.

#### `build_graph(model, tools, checkpointer)`

- Create a `StateGraph` for `AgentState`.
- Register `agent` and `tools` nodes.
- Route from `START` to `agent`.
- Add conditional routing from `agent` to `tools` or `END`.
- Route from `tools` back to `agent`.
- Compile with a checkpointer.

Use a development in-memory checkpointer initially if appropriate. Select a persistent checkpointer separately if conversations must survive process restarts; document its storage configuration and privacy implications.

### 5.5 CLI integration (`main.py`, `config.py`)

#### Graph setup in `main.run()`

Continue to:

- Prompt for model and base URL.
- Construct `AsyncOpenAI`.
- Initialize `ChatLogger`, `SkillsManager`, and `MCPManager`.
- Connect MCP servers and disconnect them in `finally`.

Add:

1. Build LangChain MCP tools from the connected `MCPManager`.
2. Construct `ResponsesChatModel` with the existing client.
3. Construct and compile the LangGraph with the chosen checkpointer.
4. Pass the graph to `InputHandler`.

#### `InputHandler.__init__`

Replace direct model ownership with graph ownership (and retain other UI/services). Store a stable thread ID for the active conversation. If multiple independent conversations are introduced later, assign each its own thread ID.

#### `InputHandler._generate_response(user_input)`

Replace the manual Responses API loop with graph invocation:

1. Create a `HumanMessage` for the user input.
2. Build current base and active-skill instructions.
3. Invoke graph with the message, instructions, and `configurable.thread_id`.
4. Render returned text and handle graph/model errors.
5. Return answer/status in a shape suitable for existing `handle_input()` and logger behavior.

First implement non-streaming graph invocation. Add graph streaming after tests establish correct tool and context behavior.

#### `InputHandler.handle_input(user_input)`

Keep slash-command handling and existing user-facing behavior. For ordinary messages:

- Invoke `_generate_response`.
- Update display history consistently.
- Preserve completed/interrupted logging behavior.
- Do not store full skill text in logs.

#### `InputHandler.reset_conversation()`

- Clear UI-owned message history and reasoning display state.
- Clear checkpoint state if supported, or rotate to a new thread ID.
- Ensure the new thread begins without `response_id`.
- Record the reset event through `ChatLogger` as today.

#### Skill activation

Keep `SkillsManager` as the source of loaded skill text. Resolve the active skill's instructions per turn and pass them to the graph/model as request instructions. Activating or clearing a skill affects subsequent model calls and does not require replaying old conversation messages.

## 6. Request lifecycle and state transitions

### 6.1 New user turn without tools

1. CLI creates a `HumanMessage` and invokes graph with the active `thread_id`.
2. Checkpointer loads this thread's state, including prior messages and `response_id`.
3. Graph appends the new user message.
4. `agent_node` selects only the new user input.
5. Wrapper calls Responses API with `previous_response_id` if present and current instructions/tools.
6. Wrapper converts response to `AIMessage` and includes the completed response ID.
7. `agent_node` stores the ID and message in graph state.
8. No tool calls are found; graph ends.
9. CLI renders and logs the answer.

### 6.2 Tool call and continuation

1. Agent returns an `AIMessage` with one or more tool calls and response ID `R1`.
2. Graph persists the AI message and `R1`.
3. Routing sends the state to `ToolNode`.
4. `ToolNode` executes LangChain MCP tools; MCP adapter calls `MCPManager`.
5. `ToolNode` appends `ToolMessage` results with corresponding tool call IDs.
6. Graph routes back to `agent_node`.
7. Agent node selects the tool outputs only.
8. Wrapper calls Responses API with `previous_response_id=R1` and function-call output input items.
9. The resulting completed response ID replaces `R1`; if more tools are requested, the graph loops again.
10. Once a final answer has no tool calls, graph ends and CLI renders it.

### 6.3 API error or interruption

- The previous completed response ID remains the last known-good ID.
- The graph must not checkpoint a partial response ID.
- CLI displays/logs the failure or interruption using existing behavior.
- Retry policy must be explicit. In particular, do not blindly retry tool execution if it may have side effects.

## 7. Dependencies and compatibility

Update `pyproject.toml` and lock/dependency files with compatible LangChain and LangGraph packages after checking the project's Python version and current dependency constraints.

Before implementation, verify the configured model server supports all required Responses API features:

- `responses.create`.
- `previous_response_id` and its retention/lifetime semantics.
- Function tools and tool-call output continuation.
- Required request parameters, including instructions.
- Streaming events if streaming is planned.

The current project uses the OpenAI Responses API directly. Do not replace it with a Chat Completions integration unless the design is intentionally changed. Confirm the installed OpenAI SDK exposes the required async Responses API methods and response/event structures.

## 8. Testing plan

Use a fake async Responses API client for deterministic unit and graph tests.

### Converter tests

- Human/user message conversion.
- Tool result/function-call output conversion and call ID preservation.
- Assistant text conversion.
- Function-call conversion, valid JSON arguments, malformed JSON, and non-object arguments.
- Unsupported message and schema handling.

### Model wrapper tests

- First call has no `previous_response_id`.
- Follow-up includes supplied ID and only incremental input.
- Instructions/tools/model settings are passed correctly.
- Completed response ID is returned in message metadata.
- API errors do not return a new ID.
- Stream interruption does not return/commit an incomplete ID.

### MCP adapter tests

- Qualified names map to the correct MCP binding.
- Arguments reach `MCPManager.call_tool` intact.
- Timeout, error, and output truncation behavior is preserved.

### Graph tests

- No-tool path reaches `END`.
- Tool-call path runs `ToolNode` and loops to the model.
- Multiple tool calls and results preserve call IDs and order.
- Only incremental input is passed on each model call.
- Response ID is saved after completion and reused on tool continuation/follow-up turns.
- Two `thread_id` values never share messages or response IDs.
- Reset/new thread starts with no previous response ID.
- Checkpoint reload restores the thread's state.

### Integration checks

Against the configured local/server endpoint, verify a simple text exchange, a tool call, a tool result continuation, a second user turn using the prior response ID, and reset behavior. Do not claim full compatibility from unit tests alone.

## 9. Implementation milestones

### Milestone 1 — Compatibility and dependency spike

- Confirm server support for Responses API continuation and function tools.
- Select compatible LangChain/LangGraph versions.
- Add dependencies and lockfile updates.

### Milestone 2 — Conversion and wrapper

- Implement request/response converters.
- Implement non-streaming `ResponsesChatModel._agenerate`.
- Test request shapes and response mappings using a fake client.

### Milestone 3 — MCP tool adapter

- Convert discovered MCP tools to LangChain tools.
- Verify one tool invokes the existing MCP manager correctly.

### Milestone 4 — Graph and checkpointed continuation

- Implement state, incremental message selection, nodes, routing, and checkpointer.
- Test text-only and tool-cycle graph paths, including per-thread IDs.

### Milestone 5 — CLI integration

- Construct the graph in `main.run()`.
- Replace `InputHandler._generate_response` manual loop.
- Preserve commands, skill selection, history, logging, and MCP shutdown.
- Implement reset via checkpoint clearing or thread rotation.

### Milestone 6 — Streaming and cancellation

- Implement `_astream` and graph event consumption.
- Connect existing Ctrl+Q cancellation behavior.
- Verify incomplete responses never replace the last completed response ID.

### Milestone 7 — End-to-end validation and documentation

- Run project tests and targeted integration checks.
- Update user documentation for dependencies, thread persistence, server compatibility, and any changed streaming behavior.

## 10. Open implementation checks

Resolve these during the compatibility spike before finalizing implementation details:

1. Does the target model server support `previous_response_id`, and how long are response IDs retained?
2. Does the endpoint require tool schemas or function-call outputs in a nonstandard format?
3. Does the Responses API server retain system instructions between chained responses, or must they be sent on every call? This design assumes instructions are sent each time.
4. Which LangChain chat-model base class and tool schema APIs are compatible with the selected package versions?
5. Which checkpointer is appropriate for the intended persistence lifetime and local privacy requirements?
6. What is the recovery strategy when a response ID expires or becomes invalid? A future fallback may reconstruct context from checkpointed LangChain messages, but that requires sending history instead of relying only on the response ID.
