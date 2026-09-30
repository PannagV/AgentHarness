# Changelog

This file records the changes made during the current implementation session.

## 2026-09-30 — Stream large responses incrementally

- Replaced per-delta reconstruction of the full Markdown response with direct
  console writes for each output delta.
- Stop and clear the transient Rich loading display when the first text arrives,
  avoiding full-screen redraws as the response grows.
- Disable Rich markup parsing for model-generated deltas to preserve literal text.
- Continue accumulating the complete response for conversation history and logs;
  history still renders Markdown after generation.
- Added regression tests for incremental delta display and empty responses.

## 2026-09-30 — Support Python 3.13

- Lowered the project minimum Python version from 3.14 to 3.13.
- Updated `.python-version`, `pyproject.toml`, and `uv.lock` so `pipx`
  installation works with Python 3.13.3.

## 2026-09-29 — Icebreaker rename, skills, and global CLI

- Renamed the project distribution from `agentharness` to `icebreaker`.
- Added the `icebreaker` console command through `cli.py` and `pyproject.toml`.
- Preserved `python main.py` for local development.
- Added setuptools packaging metadata for the flat Python module layout.
- Documented editable `pipx` installation so the command can run from any folder
  without manually activating a virtual environment.
- Added `ICEBREAKER_SKILLS_DIR` to override the skills directory.
- Added `ICEBREAKER_LOG_DIR` to override the log directory.
- Added `skills_manager.py` for discovering and validating `skills/*/SKILL.md`.
- Added YAML front matter parsing through `pyyaml`.
- Added explicit skill commands:
  - `/skills`
  - `/skill`
  - `/skill <name>`
  - `/skill clear`
- Injected active skill instructions through the Responses API `instructions`
  field without mixing them into user input.
- Added skill activation and clearing lifecycle events to JSONL logs.
- Added active skill names to exchange and interruption records.
- Added safe skill resource path validation.
- Added regression tests for skill discovery, malformed skills, multiline YAML,
  and path traversal protection.
- Updated `README.md`, `Agents.md`, `pyproject.toml`, `requirements.txt`, and
  `uv.lock` for the new project name and runtime behavior.

## 2026-09-29 — Initial codebase exploration

- Inspected the repository structure and identified the Python CLI layout.
- Reviewed `main.py`, `config.py`, `README.md`, `.gitignore`, and `LICENSE`.
- Identified the original application as a Rich terminal client for a local OpenAI-compatible model server.
- Identified the original logging implementation as in-memory arrays written only on reset or exit.
- Documented the original logging problems:
  - Duplicate `.json` extensions
  - Invalid concatenated JSON arrays caused by append-mode writes
  - Duplicate data on repeated checkpoints
  - Unsaved data if the process crashes
  - Reasoning traces not being cleared on reset
  - Potentially unbound response streams after request failures

## Base URL selection

- Added a default base URL constant:

  ```text
  http://localhost:1234/v1
  ```

- Added startup base URL selection.
- Pressing Enter at the base URL prompt uses the localhost default.
- Created the OpenAI client after collecting the user-selected URL.
- Removed the initial startup import cycle by delaying the `config` import.
- Changed `InputHandler` to receive the client instead of importing it from `main.py`.

## Logging redesign

- Replaced checkpoint-style whole-array persistence with `ChatLogger` in `logger.py`.
- Added append-only JSON Lines (`.jsonl`) output.
- Added separate chat and reasoning trace directories.
- Added daily log filenames based on UTC dates.
- Added UTC timestamps.
- Added unique session IDs.
- Added model and base URL metadata.
- Added exchange records.
- Added error records.
- Added lifecycle event records.
- Added model-change records.
- Added reset and exit records.
- Added interrupted-response records.
- Added optional reasoning trace logging.
- Made log directories create themselves recursively.
- Removed the need to rewrite the entire conversation at exit or reset.

## Model switching and history

- Moved active model ownership into `InputHandler`.
- Added `/model` and `/m` commands.
- Model changes are applied to future requests without backend model discovery.
- Model changes are logged with both previous and new model names.
- Added `/history` for current-session history display.
- Added Rich panels for user and assistant messages.
- Added model labels to assistant history entries.
- Added interrupted status labels to partial assistant responses.
- Normalized in-memory messages into a flat list of message dictionaries.
- Updated help text to document model switching and history.
- Updated reset behavior to clear both messages and reasoning state.

## Multiline prompts and interruption

- Added `input_ui.py` with a `MultilineInput` wrapper around `prompt_toolkit`.
- Changed Enter to insert a newline rather than submit the prompt.
- Added explicit prompt submission with Ctrl+Enter/Ctrl+J.
- Added Escape followed by Enter as an additional submission sequence.
- Added Ctrl+Q to cancel an unfinished input draft.
- Converted the main application loop to `asyncio`.
- Switched the runtime client to `AsyncOpenAI`.
- Converted response streaming to asynchronous iteration.
- Added a Windows `msvcrt` watcher for Ctrl+Q during generation.
- Added cooperative stream interruption behavior.
- Preserved partial assistant output after interruption.
- Prevented empty assistant messages from being added after failed requests.
- Added interrupted reasoning logging.
- Updated help text with multiline and interruption controls.

## Dependencies and documentation

- Added `requirements.txt` containing:

  ```text
  openai
  rich
  prompt-toolkit
  ```

- Added `agents.md` describing the project architecture, runtime behavior, conventions, logging format, controls, and known limitations.
- Added this `chanelog.md` file.

## Validation status

- Editor diagnostics were run against the changed Python files.
- The environment currently cannot resolve `openai`, `rich`, or `prompt_toolkit` because those packages are not installed in the active Python environment.
- No runtime or automated tests were run.
- The terminal sandbox was unavailable for command-based validation because the WSL Bubblewrap environment could not be created.
