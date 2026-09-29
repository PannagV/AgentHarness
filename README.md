# Icebreaker

Icebreaker is a Rich-based terminal application for interacting with local
OpenAI-compatible model servers.

## Install and run

For local development:

```bash
pip install -r requirements.txt
python main.py
```

To install the command globally without manually activating a virtual
environment, install it with `pipx` from the project directory:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
pipx install --editable .
```

Then run it from any folder:

```powershell
icebreaker
```

The default backend is `http://localhost:1234/v1`. The model and base URL are
requested when the application starts.

## Skills

Skills are reusable instruction packages stored under the project-level
`skills/` directory. Each skill is an immediate child directory containing a
`SKILL.md` file with YAML front matter and Markdown instructions:

```text
skills/
└── example-skill/
    └── SKILL.md
```

Required front matter fields are `name` and `description`. Optional supporting
files may live in `references/`, `scripts/`, or `assets/`, although only the
`SKILL.md` instructions are currently injected into model requests.

Use these commands during a session:

```text
/skills              List valid discovered skills
/skill               Show the active skill
/skill <name>        Activate a skill
/skill clear         Clear the active skill
```

The active skill is sent as the Responses API `instructions` value and remains
separate from the user's prompt. Skill activation and selection are recorded in
the session JSONL log, but the full skill text is not logged. Invalid skill
directories are skipped and reported by `/skills` rather than preventing the
application from starting.

## Controls

- Enter inserts a newline.
- Ctrl+Enter or Ctrl+J submits a prompt.
- Ctrl+Q cancels input or interrupts generation on Windows.
- `/help` shows all available commands.

Conversation and reasoning records are written to `logs/`. Reasoning traces
may contain sensitive content and can be disabled in `ChatLogger`.

When installed globally, these paths can be overridden with environment
variables:

```powershell
$env:ICEBREAKER_SKILLS_DIR = "C:\path\to\skills"
$env:ICEBREAKER_LOG_DIR = "C:\path\to\logs"
```
