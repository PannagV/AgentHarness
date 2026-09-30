import asyncio
import contextlib
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from logger import ChatLogger
from mcp_manager import MCPManager
from skills_manager import Skill, SkillsManager


console = Console()


class LiveResponseText:
    """Switch from the live wait indicator to direct, incremental output."""

    def __init__(self, live: Live) -> None:
        self.live = live
        self.has_output = False

    def write_delta(self, delta: str) -> None:
        if not self.has_output:
            self.live.stop()
            self.has_output = True
        console.print(delta, end="", markup=False, highlight=False)

    def finish(self) -> None:
        if self.has_output:
            console.print()


class InputHandler:
    def __init__(
        self,
        client: Any,
        dots_renderer: type,
        model_name: str,
        logger: ChatLogger,
        skills_manager: SkillsManager | None = None,
        mcp_manager: MCPManager | None = None,
    ) -> None:
        self.client = client
        self.dots_renderer = dots_renderer
        self.model_name = model_name
        self.logger = logger
        self.skills_manager = skills_manager or SkillsManager(
            Path(__file__).parent / "skills"
        )
        self.active_skill: Skill | None = None
        self.mcp_manager = mcp_manager
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
            "/skills": self.list_skills,
            "/list-skills": self.list_skills,
            "/mcp": self.list_mcp_servers,
            "/mcp-tools": self.list_mcp_tools,
        }

    def list_skills(self) -> None:
        skills = self.skills_manager.list_skills()
        if not skills:
            console.print("[yellow]No valid skills discovered.[/yellow]")
            return

        console.print("[bold cyan]Available skills[/bold cyan]\n")
        for skill in skills:
            console.print(
                f"- [cyan]{skill.metadata.name}[/cyan] — "
                f"{skill.metadata.description}\n\n"
            )
        if self.skills_manager.errors:
            console.print(
                f"[yellow]{len(self.skills_manager.errors)} skill(s) skipped "
                "because they are invalid.[/yellow]"
            )

    def list_mcp_servers(self) -> None:
        if self.mcp_manager is None:
            console.print("[yellow]MCP is not configured.[/yellow]")
            return
        summaries = self.mcp_manager.server_summaries()
        if not summaries:
            console.print("[yellow]No MCP servers configured.[/yellow]")
            return
        console.print("[bold cyan]MCP servers[/bold cyan]")
        for name, transport, state in summaries:
            console.print(f"- [cyan]{name}[/cyan] ({transport}): {state}")

    def list_mcp_tools(self) -> None:
        tools = self.mcp_manager.tool_summaries() if self.mcp_manager else []
        if not tools:
            console.print("[yellow]No MCP tools available.[/yellow]")
            return
        console.print("[bold cyan]MCP tools[/bold cyan]")
        for name, description in tools:
            console.print(f"- [cyan]{name}[/cyan] — {description}")

    def select_skill(self, argument: str = "") -> None:
        argument = argument.strip()
        if not argument:
            if self.active_skill is None:
                console.print("[yellow]No active skill.[/yellow]")
            else:
                console.print(
                    f"Active skill: [cyan]{self.active_skill.metadata.name}[/cyan]"
                )
            return

        if argument.casefold() == "clear":
            previous = self.active_skill.metadata.name if self.active_skill else None
            self.active_skill = None
            self.logger.log_event("skill_cleared", previous_skill=previous)
            console.print("[green]Active skill cleared.[/green]")
            return

        skill = self.skills_manager.get(argument)
        if skill is None:
            console.print(f"[red]Unknown skill:[/red] {argument}")
            return

        self.active_skill = skill
        self.logger.log_event("skill_activated", skill=skill.metadata.name)
        console.print(f"[green]Using skill:[/green] {skill.metadata.name}")

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
/skills         List available skills
/mcp            List MCP servers and connection status
/mcp-tools      List available MCP tools
/skill          Show the active skill
/skill <name>   Activate a skill
/skill clear    Clear the active skill
/exit, /quit    Exit the program

Multiline input:
Enter            Insert a new line
Ctrl+Enter/Ctrl+J Submit the prompt
Ctrl+Q           Cancel input or interrupt generation
"""
        )

    def exit_program(self) -> None:
        self.logger.log_event("exit")
        console.print("Exiting...")
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
        input_items: list[Any] = [{"role": "user", "content": user_input}]
        tool_rounds = 0

        try:
            with Live(
                Group(self.dots_renderer(), response_panel),
                console=console,
                refresh_per_second=10,
                transient=True,
            ) as live:
                display = LiveResponseText(live)
                while True:
                    request: dict[str, Any] = {
                        "model": self.model_name,
                        "input": input_items,
                        "stream": True,
                    }
                    if self.active_skill is not None:
                        request["instructions"] = self.skills_manager.format_instructions(
                            self.active_skill
                        )
                    if self.mcp_manager is not None:
                        tools = self.mcp_manager.responses_tools()
                        if tools:
                            request["tools"] = tools

                    try:
                        stream = await self.client.responses.create(**request)
                    except Exception as error:
                        self.logger.log_error(user_input, str(error), self.model_name)
                        display.finish()
                        if live.is_started:
                            live.stop()
                        console.print(Panel(f"[bold red]Request failed:[/bold red] {error}", border_style="red"))
                        return "", [], "failed"

                    completed_response = None
                    async for event in stream:
                        if cancel_event.is_set():
                            status = "interrupted"
                            break
                        if event.type == "response.reasoning_text.delta":
                            reasoning.append(event.delta)
                        elif event.type == "response.output_text.delta":
                            answer += event.delta
                            display.write_delta(event.delta)
                        elif event.type == "response.completed":
                            completed_response = event.response

                    if cancel_event.is_set():
                        status = "interrupted"
                        if not display.has_output:
                            live.stop()
                            console.print(Panel(Markdown(answer or "[No output received]"), title="Generation interrupted", border_style="yellow"))
                        break
                    if completed_response is None:
                        break

                    output_items = completed_response.output
                    calls = [item for item in output_items if getattr(item, "type", None) == "function_call"]
                    if not calls:
                        break
                    if self.mcp_manager is None:
                        break
                    tool_rounds += 1
                    if tool_rounds > 8:
                        answer += "\n\n[Stopped: maximum MCP tool-call rounds reached.]"
                        break

                    input_items.extend(item.model_dump(exclude_none=True) for item in output_items)
                    for call in calls:
                        try:
                            arguments = json.loads(call.arguments or "{}")
                            if not isinstance(arguments, dict):
                                raise ValueError("Tool arguments must be a JSON object")
                            result = await asyncio.wait_for(
                                self.mcp_manager.call_tool(call.name, arguments), timeout=60
                            )
                        except Exception as error:
                            result = f"MCP tool error: {error}"
                        input_items.append({
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": result,
                        })

                display.finish()
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
        if command == "/skill" or command.startswith("/skill "):
            self.select_skill(user_input.strip()[len("/skill") :])
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
                self.active_skill.metadata.name if self.active_skill else None,
            )
            console.print("[yellow]Generation interrupted.[/yellow]")
        else:
            self.logger.log_exchange(
                user_input,
                answer,
                self.model_name,
                reasoning,
                skill_name=self.active_skill.metadata.name if self.active_skill else None,
            )
        self.reasoning_trace.clear()
        print()
