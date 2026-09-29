# Icebreaker Project Guide

## Overview

Icebreaker is a Python terminal application for interacting with local OpenAI-compatible language model servers. It provides a Rich-based terminal UI, streaming responses, runtime model selection, multiline prompt input, cancellable generation, conversation history, and append-only JSONL logging.

The default backend is intended to be a local server such as LM Studio:

```text
http://localhost:1234/v1
```

The application does not currently provide a web UI, remote authentication, model discovery, or persistent conversation restoration.

## Repository layout

```text
Icebreaker/
├── Agents.md
├── Changelog.md
├── config.py
├── input_ui.py
├── logger.py
├── main.py
├── cli.py
├── skills_manager.py
├── skills/
│   └── <skill-name>/SKILL.md
├── requirements.txt
├── README.md
├── LICENSE
├── .gitignore
└── logs/
    ├── chatlog/
    └── reasoning_trace/
```

`__pycache__/` may also exist locally and is ignored by Git.

## Runtime dependencies

The application expects:

- `openai` for OpenAI-compatible synchronous/asynchronous client APIs
- `rich` for terminal formatting and live response rendering
- `prompt-toolkit` for multiline editing and keyboard bindings
- `pyyaml` for parsing skill front matter

Install them with:

```bash
pip install -r requirements.txt
```

For a globally available command without manually activating a virtual
environment, install the editable project with `pipx install --editable .`.
The command is then `icebreaker` and works from any directory.

Packaging is configured in `pyproject.toml`; `uv.lock` records the locked dependencies.

## Application flow

The entry point is `main.py`.

1. `main.py` starts an asynchronous event loop.
2. The user enters a model name, with a default of `nvidia/nemotron-3-nano-4b`.
3. The user enters an OpenAI-compatible base URL, with a default of `http://localhost:1234/v1`.
4. An `AsyncOpenAI` client is created using the selected URL.
5. A `ChatLogger` is created for the session.
6. `MultilineInput` reads prompts from the terminal.
7. `SkillsManager` discovers valid skills under `skills/`.
8. `InputHandler` handles commands or starts an asynchronous streamed response.
9. Completed, interrupted, failed, lifecycle, and skill events are logged as JSONL records.

Run the application from the project directory with:

```bash
python main.py
```

## Main modules

### `cli.py`

`cli.py` is the installed command-line entry point. The `icebreaker` console
script calls `cli.main()`, which starts the existing asynchronous `main.run()`
loop. Running `python main.py` remains supported for local development.

### `main.py`

Owns application startup and the main async loop.

Important constants:

```python
DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL_NAME = "nvidia/nemotron-3-nano-4b"
```

`ThreeDots` is a Rich renderable used for the animated generation indicator.

The startup client is `AsyncOpenAI`, not the synchronous `OpenAI` client. The base URL and model are collected before the client and handler are initialized.

### `input_ui.py`

Owns terminal input behavior through `prompt_toolkit`.

`MultilineInput` provides:

- Enter: insert a newline
- Ctrl+Enter/Ctrl+J: submit the current prompt
- Escape followed by Enter: submit the current prompt
- Ctrl+Q: cancel an unfinished draft

`InputResult` distinguishes submitted text from cancelled input and exit results.

The `Ctrl+J` binding is included because many terminals represent Ctrl+Enter as a control character rather than a literal `c-enter` key name.

### `config.py`

Contains `InputHandler`, which owns the active interaction state:

- OpenAI client
- Current model name
- Conversation history
- Current reasoning trace
- Command dispatch table
- Chat logger

Supported commands:

```text
/help, /h       Show help
/model, /m      Change the active model
/history        Show current-session history
/reset, /clear  Clear current in-memory history
/id             Show the current session ID
/skills         List available skills
/skill          Show the active skill
/skill <name>   Activate a skill
/skill clear    Clear the active skill
/exit, /quit    Exit the application
```

#### Model switching

`/model` prompts for a new model identifier. The value is applied to subsequent requests without querying the backend for validation. A `model_changed` event is logged.

Model changes do not rewrite existing messages. Assistant history entries retain the model used for that response.

#### History

`/history` displays the current in-memory conversation using Rich panels. User messages use a blue panel. Assistant messages use Markdown and include the model name. Interrupted assistant messages are labeled accordingly.

History is session-local. The application does not currently load prior sessions from disk.

#### Response streaming

Responses are requested with the active model and streamed asynchronously. Reasoning deltas and output deltas are collected separately.

Successful requests:

- Add a user message to memory
- Add an assistant message if output was received
- Persist an exchange record
- Persist reasoning if reasoning logging is enabled

Failed requests:

- Show an error panel
- Persist an error record
- Do not add an empty assistant message

Interrupted requests:

- Preserve partial output if any was received
- Mark the assistant history entry as `interrupted`
- Persist an interrupted record
- Persist any collected reasoning as `reasoning_interrupted`

`ICEBREAKER_SKILLS_DIR` can override the skills root when the command is
installed globally. Otherwise, the project-local `skills/` directory is used.

### `skills_manager.py`

`SkillsManager` discovers immediate child directories under `skills/`, validates
`SKILL.md` YAML front matter, and loads skill instructions. Each valid skill
requires matching directory and metadata names plus non-empty `name`,
`description`, and Markdown instructions. Invalid skills are skipped and
reported through `/skills`.

`Skill.resolve_resource()` safely resolves paths within a skill directory, but
resources are not automatically loaded or executed.

### `logger.py`

`ChatLogger` provides append-only JSON Lines persistence.

By default, paths are rooted beside the source file. `ICEBREAKER_LOG_DIR`
can override the log root for global installations:

```text
logs/chatlog/chatlog_YYYY-MM-DD.jsonl
logs/reasoning_trace/reasoning_trace_YYYY-MM-DD.jsonl
```

Each line is an independent JSON object. This avoids the invalid concatenated-array problem from the original implementation.

Common metadata fields include:

- `timestamp` — UTC ISO 8601 timestamp
- `type` — record type
- `session_id` — unique session identifier
- `model` — active model when applicable
- `base_url` — selected backend URL when configured
- `skill` — active skill name when applicable

Possible chat record types include:

- `exchange`
- `interrupted`
- `error`
- `model_changed`
- `reset`
- `exit`
- `skill_activated`
- `skill_cleared`

Reasoning is logged separately and can be disabled using the `log_reasoning` constructor option.

API keys are not written to logs.

## Input and cancellation behavior

Multiline prompts are not submitted by pressing Enter. The complete prompt is sent only after an explicit submit key.

During generation, `config.py` starts a Windows keyboard watcher that checks for `Ctrl+Q`. When detected, the response is treated as interrupted and the stream is closed when possible.

The current cancellation watcher uses `msvcrt` on Windows. Non-Windows terminals currently do not have equivalent generation-time Ctrl+Q monitoring, although multiline input itself remains provided by `prompt_toolkit`.

## Conversation data model

In-memory history uses a flat list of message dictionaries:

```python
[
    {"role": "user", "content": "..."},
    {
        "role": "assistant",
        "content": "...",
        "model": "...",
        "status": "completed",
    },
]
```

Assistant `status` is normally `completed` and may be `interrupted`.

The current history is for display only. It is not yet sent back to the model as context for future requests.

## Logging and privacy considerations

Reasoning traces may contain sensitive content and can be significantly larger than normal chat records. Treat `logs/reasoning_trace/` as debug output and disable it when necessary:

```python
ChatLogger(..., log_reasoning=False)
```

Runtime logs are ignored by `.gitignore` through:

```text
logs/*
```

## Development conventions

- Keep terminal presentation in Rich-facing code.
- Keep terminal editing and key bindings in `input_ui.py`.
- Keep persistence in `logger.py`.
- Keep command and conversation behavior in `InputHandler`.
- Prefer UTC timestamps for persisted data.
- Do not log API keys or other credentials.
- Do not rewrite complete log files; append one JSON object per line.
- Do not add empty assistant messages for failed requests.
- Keep model changes explicit in the log.
- Keep skill instructions separate from user input when building requests.
- Do not execute skill resources automatically.

## Known limitations and follow-up work

1. Third-party packages must be installed before runtime validation.
2. The complete conversation history is not sent to the model on later requests.
3. The model name is accepted without backend validation.
4. The OpenAI-compatible server must support the Responses API streaming interface used by the application.
5. `config.py` still catches a broad `Exception` around the model request so backend-specific failures can be displayed; this can be narrowed after the supported backend error types are established.
6. The installed non-editable wheel does not bundle the project-local `skills/` directory; use `pipx install --editable .` or set `ICEBREAKER_SKILLS_DIR` for globally installed use.
7. The project requires Python 3.14 or newer.
8. Automatic skill selection is not implemented; skills are selected explicitly with `/skill <name>`.
