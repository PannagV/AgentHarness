import asyncio
import os
import time
from pathlib import Path

from openai import AsyncOpenAI
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL_NAME = "nvidia/nemotron-3-nano-4b"
DEFAULT_API_KEY = "lm-studio"

console = Console(color_system="auto")


def show_welcome(model_name: str) -> None:
    console.print(
        Panel.fit(
            f"[green]{model_name}[/green]\n"
            "Type [bold]/help[/bold] for commands or [bold]/exit[/bold] to quit.",
            border_style="green",
            padding=(1, 2),
        )
    )


class ThreeDots:
    def __rich_console__(self, console, options):
        active_dot = int(time.monotonic() * 4) % 3
        dots = Text()

        for index in range(3):
            dots.append(
                ".",
                style="bold white" if index == active_dot else "dim white",
            )
            if index < 2:
                dots.append("")

        yield dots


async def run() -> None:
    from config import InputHandler
    from input_ui import MultilineInput
    from logger import ChatLogger
    from mcp_manager import MCPManager
    from skills_manager import SkillsManager

    model_name = console.input(
        f"[bold] Enter Model Name [{DEFAULT_MODEL_NAME}]: "
    ).strip() or DEFAULT_MODEL_NAME
    base_url = console.input(
        f"[bold] Enter Base URL [{DEFAULT_BASE_URL}]: "
    ).strip() or DEFAULT_BASE_URL
    apiKey = console.input(
        f"[bold] Enter API key [{DEFAULT_API_KEY}]: "
    ).strip() or DEFAULT_API_KEY

    client = AsyncOpenAI(
        base_url=base_url,
        api_key=apiKey,
    )
    logger = ChatLogger(model_name=model_name, base_url=base_url)
    skills_directory = Path(
        os.environ.get("ICEBREAKER_SKILLS_DIR", Path(__file__).parent / "skills")
    ).expanduser()
    skills_manager = SkillsManager(skills_directory)
    mcp_manager = MCPManager(Path(__file__).parent)
    await mcp_manager.connect_all()
    for name, transport, state in mcp_manager.server_summaries():
        if state == "connected":
            console.print(f"[green]MCP server connected:[/green] {name} ({transport})")
        else:
            console.print(f"[yellow]MCP server unavailable:[/yellow] {name}: {state}")

    input_session = MultilineInput()
    input_handler = InputHandler(
        client, ThreeDots, model_name, logger, skills_manager, mcp_manager
    )

    show_welcome(model_name)

    try:
        while True:
            try:
                result = await input_session.prompt()
            except (EOFError, KeyboardInterrupt):
                input_handler.exit_program()
                return

            if result.exited:
                input_handler.exit_program()
            if result.cancelled:
                console.print("[yellow]Input cancelled.[/yellow]")
                continue
            if not result.text.strip():
                continue

            await input_handler.handle_input(result.text)
    finally:
        await mcp_manager.disconnect_all()


if __name__ == "__main__":
    asyncio.run(run())
