import asyncio
import contextlib
import inspect
import os
import sys
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from logger import ChatLogger


console = Console()


class InputHandler:
    def __init__(
        self,
        client: Any,
        dots_renderer: type,
        model_name: str,
        logger: ChatLogger,
    ) -> None:
        self.client = client
        self.dots_renderer = dots_renderer
        self.model_name = model_name
        self.logger = logger
        self.messages: list[dict[str, str]] = []
        self.reasoning_trace: list[str] = []
        self.commands = {
            "/help": self.help,
            "/h": self.help,
            "/model": self.change_model,
            "/m": self.change_model,
            "/history": self.show_history,
            "/exit": self.exit_program,
            "/quit": self.exit_program,
            "/reset": self.reset_conversation,
            "/clear": self.reset_conversation,
            "/id": self.show_conversation_id,
        }

    def show_conversation_id(self) -> None:
        console.print(
            f"Current conversation ID: [cyan]{self.logger.session_id}[/cyan]"
        )

    def change_model(self) -> None:
        new_model = Prompt.ask(
            "Model",
            default=self.model_name,
            show_default=True,
        ).strip()

        if not new_model:
            console.print("[yellow]Model unchanged.[/yellow]")
            return

        previous_model = self.model_name
        if new_model == previous_model:
            console.print(f"[yellow]Already using model:[/yellow] {new_model}")
            return

        self.model_name = new_model
        self.logger.model_name = new_model
        self.logger.log_event(
            "model_changed",
            previous_model=previous_model,
            model=new_model,
        )
        console.print(f"[green]Using model:[/green] {new_model}")

    def show_history(self) -> None:
        if not self.messages:
            console.print("[yellow]No conversation history available.[/yellow]")
            return

        console.print("[bold cyan]Conversation History[/bold cyan]")
        for message in self.messages:
            role = message["role"]
            content = message["content"]

            if role == "user":
                console.print(Panel(content, title="User", border_style="blue"))
                continue

            model = message.get("model", self.model_name)
            status = message.get("status", "completed")
            title = f"Assistant · {model}"
            if status == "interrupted":
                title += " · interrupted"

            console.print(
                Panel(
                    Markdown(content or "[No output received]"),
                    title=title,
                    border_style="yellow" if status == "interrupted" else "green",
                )
            )

    def help(self) -> None:
        console.print(
            """
Available commands:
-----------------------------------------
/help, /h       Show this help message
/model, /m      Change the active model
/history        Show the current conversation history
/reset, /clear  Clear the current conversation
/id             Show the current conversation ID
/exit, /quit    Exit the program

Multiline input:
Enter            Insert a new line
Ctrl+Enter/Ctrl+J Submit the prompt
Ctrl+Q           Cancel input or interrupt generation
"""
        )

    def exit_program(self) -> None:
        self.logger.log_event("exit")
        console.log("Exiting...")
        sys.exit(0)

    def reset_conversation(self) -> None:
        self.logger.log_event("reset")
        self.messages.clear()
        self.reasoning_trace.clear()
        console.print("[green]Conversation history cleared.[/green]")

    async def _watch_for_cancel(self, cancel_event: asyncio.Event) -> None:
        """Watch for Ctrl+Q while the model stream is active on Windows."""
        if os.name != "nt":
            return

        import msvcrt

        while not cancel_event.is_set():
            if msvcrt.kbhit() and msvcrt.getwch() == "\x11":
                cancel_event.set()
                return
            await asyncio.sleep(0.05)

    async def _close_stream(self, stream: Any) -> None:
        close = getattr(stream, "close", None)
        if close is None:
            return

        result = close()
        if inspect.isawaitable(result):
            await result

    async def _generate_response(self, user_input: str) -> tuple[str, list[str], str]:
        answer = ""
        reasoning: list[str] = []
        status = "completed"
        cancel_event = asyncio.Event()
        cancel_task = asyncio.create_task(self._watch_for_cancel(cancel_event))
        stream = None
        response_panel = Panel(Markdown(""), border_style="green")

        try:
            with Live(
                Group(self.dots_renderer(), response_panel),
                console=console,
                refresh_per_second=10,
            ) as live:
                try:
                    stream = await self.client.responses.create(
                        model=self.model_name,
                        input=user_input,
                        stream=True,
                    )
                except Exception as error:
                    self.logger.log_error(user_input, str(error), self.model_name)
                    live.update(
                        Panel(
                            f"[bold red]Request failed:[/bold red] {error}",
                            border_style="red",
                        )
                    )
                    return "", [], "failed"

                async for event in stream:
                    if cancel_event.is_set():
                        status = "interrupted"
                        break

                    if event.type == "response.reasoning_text.delta":
                        reasoning.append(event.delta)
                    elif event.type == "response.output_text.delta":
                        answer += event.delta
                        response_panel = Panel(
                            Markdown(answer),
                            border_style="yellow" if status == "interrupted" else "green",
                        )
                        live.update(Group(self.dots_renderer(), response_panel))

                if cancel_event.is_set():
                    status = "interrupted"
                    live.update(
                        Panel(
                            Markdown(answer or "[No output received]"),
                            title="Generation interrupted",
                            border_style="yellow",
                        )
                    )
                else:
                    live.update(response_panel)
        except asyncio.CancelledError:
            status = "interrupted"
        finally:
            cancel_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cancel_task
            if stream is not None and status == "interrupted":
                await self._close_stream(stream)

        return answer, reasoning, status

    async def handle_input(self, user_input: str) -> None:
        command = user_input.strip().lower()
        if command in self.commands:
            self.commands[command]()
            return

        self.reasoning_trace.clear()
        answer, reasoning, status = await self._generate_response(user_input)
        if status == "failed":
            return

        self.messages.append({"role": "user", "content": user_input})
        if answer:
            self.messages.append(
                {
                    "role": "assistant",
                    "content": answer,
                    "model": self.model_name,
                    "status": status,
                }
            )

        if status == "interrupted":
            self.logger.log_interrupted(
                user_input,
                answer,
                self.model_name,
                reasoning,
            )
            console.print("[yellow]Generation interrupted.[/yellow]")
        else:
            self.logger.log_exchange(
                user_input,
                answer,
                self.model_name,
                reasoning,
            )
        self.reasoning_trace.clear()
        print()
