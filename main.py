from openai import OpenAI
import config
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.live import Live
from rich.text import Text
import time

client = OpenAI(
    base_url = "http://localhost:1234/v1",
    api_key = "lm-studio"
)


console = Console(
    color_system="auto"
)


def show_welcome(model_name):
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
            dots.append(".", style="bold white" if index == active_dot else "dim white")
            if index < 2:
                dots.append("")

        yield dots

if __name__ == "__main__":

    MODEL_NAME = console.input(f'[bold] Enter Model Name: ') or "nvidia/nemotron-3-nano-4b"
    
    show_welcome(MODEL_NAME)
    input_handler = config.InputHandler()

    # Handling input command options
    while True:
        
        USER_INPUT = Prompt.ask("\n[italic]User > [/italic]")
        input_handler.handle_input(USER_INPUT, MODEL_NAME)    