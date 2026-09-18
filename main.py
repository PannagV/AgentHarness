from openai import OpenAI
import config
from rich.console import Console
from rich.console import Group
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
            border_style="violet",
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

    MODEL_NAME = console.input(f'Enter Model Name: ') or "nvidia/nemotron-3-nano-4b"
    messages = []
    show_welcome(MODEL_NAME)

    # Handling input command options
    while True:
        
        USER_INPUT = Prompt.ask("\n[italic]Operator > [/italic]")

        if USER_INPUT.lower() in ["/exit", "/quit"]:
            console.log(f'Exiting...')
            break

        elif USER_INPUT.lower() in ["/help", "/h"]:
            config.help()
            continue

        elif USER_INPUT.lower() in ["/reset", "/clear"]:
            messages.clear()
            console.print("[green]Conversation history cleared.[/green]\n")
            continue

        messages.append({"role": "user", "content": USER_INPUT})

        answer = ""
        status = ThreeDots()
        response_panel = Panel(Markdown(""), border_style="green")

        with Live(
            Group(status, response_panel),
            console=console,
            refresh_per_second=10,
        ) as live:
            try:
                stream = client.responses.create(
                    model=MODEL_NAME,
                    input=USER_INPUT,
                    stream=True
                )
            except Exception as error:
                live.update(Panel(f"[bold red]Request failed:[/bold red] {error}", border_style="red"))
                continue

            for event in stream:
                if event.type == "response.output_text.delta":
                    answer += event.delta
                    response_panel = Panel(Markdown(answer), border_style="green")
                    live.update(Group(status, response_panel))

            live.update(response_panel)

        messages.append({
            "role": "assistant",
            "content": answer
        })

        print()