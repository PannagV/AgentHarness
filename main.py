from openai import OpenAI
import config
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.status import Status

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

if __name__ == "__main__":

    MODEL_NAME = console.input(f'Enter Model Name: ') or "nvidia/nemotron-3-nano-4b"
    messages = []
    show_welcome(MODEL_NAME)

    # Handling input command options
    while True:
        
        USER_INPUT = Prompt.ask("[italic]Operator > [/italic] ")

        if USER_INPUT.lower() in ["/exit", "/quit"]:
            console.log(f'Exiting...')
            break

        elif USER_INPUT.lower() in ["/help", "/h"]:
            config.help()
            continue

        elif USER_INPUT.lower() in ["/reset", "/clear"]:
            messages.clear()
            console.print("[green]Conversation history cleared.[/green]")
            continue

        messages.append({"role": "user", "content": USER_INPUT})

        try:
            stream = client.responses.create(
                model=MODEL_NAME,
                input=USER_INPUT,
                stream=True
            )
        except Exception as error:
            console.print(f"[bold red]Request failed:[/bold red] {error}")
            continue

        answer = ""

        with Status("[grey italic]Thinking...[/grey italic]", console=console):
            for event in stream:
                if event.type == "response.output_text.delta":
                    answer += event.delta

        console.print(Panel(Markdown(answer), border_style="green"))

        messages.append({
            "role": "assistant",
            "content": answer
        })

        print()