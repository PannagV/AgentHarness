from pyexpat.errors import messages
from main import console, client, ThreeDots
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.live import Live
from rich.text import Text
from datetime import datetime
import json
from pathlib import Path

chatDIR = Path("logs/chatlog")
traceDIR = Path("logs/reasoning_trace")
chatDIR.mkdir(exist_ok=True)
traceDIR.mkdir(exist_ok=True)

log_file = f"{chatDIR}/chatlog_{datetime.now().strftime('%Y-%m-%d')}.json"
resoning_trace = f"{traceDIR}/reasoning_trace_{datetime.now().strftime('%Y-%m-%d')}.json"
console = Console()
messages = []
reasoning_trace = []

class InputHandler():
    
    def __init__(self):
        self.commands = {
            "/help": self.help,
            "/h": self.help,
            "/exit": self.exit_program,
            "/quit": self.exit_program,
            "/reset": self.reset_conversation,
            "/clear": self.reset_conversation,
            #"/model": self.change_model,
            "/id": self.show_conversation_id,
            #"/history": self.show_history
        }

    def show_conversation_id(self):
        console.print(f'Current conversation ID: [cyan]{log_file}[/cyan]')
    """
    def show_history(self):
        if messages:
            console.print("[bold cyan]Conversation History:[/bold cyan]")
            for msg in messages:
                console.print(f'[{msg[0]["role"]}]: {msg[0]["content"]}')
                
        else:
            console.print("[yellow]No conversation history available.[/yellow]")
    """
    def help(self):
            console.print(""" 
            Available commands:
            -----------------------------------------
            /help , /h - Show this help message
            /exit , /quit - Exit the program
            /reset - Reset the conversation
            /model - Change the model (Under Progress)
            /id - Show the current conversation ID
            /history - Show the conversation history
            /clear - Clear the conversation history
            """)

    def checkpoint(self, log_file, reasoning_trace):
        with open(f"{log_file}.json", "a") as f:
            json.dump(messages, f, indent=4)

        with open(f"{resoning_trace}.json", "a") as f:
            json.dump(reasoning_trace, f, indent=4)

        console.log(f'Chat history and reasoning trace saved to {log_file}.json')

    def exit_program(self):
        console.log(f'Exiting...')
        self.checkpoint(log_file, reasoning_trace)
        exit()

    def reset_conversation(self):
        # Logic to reset conversation goes here
        console.print("[green]Conversation history cleared.[/green]")
        self.checkpoint(log_file, reasoning_trace)
        messages.clear()
        pass

    def handle_input(self, user_input, model_name):
        command = user_input.lower()
        if command in self.commands:
            self.commands[command]()
            pass 
        else:

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
                        model=model_name,
                        input=user_input,
                        stream=True
                    )
                except Exception as error:
                    live.update(Panel(f"[bold red]Request failed:[/bold red] {error}", border_style="red"))
                    pass

                for event in stream:
                    if event.type == "response.reasoning_text.delta":
                        reasoning_trace.append([event.delta])
                    if event.type == "response.output_text.delta":
                        answer += event.delta
                        response_panel = Panel(Markdown(answer), border_style="green")
                        live.update(Group(status, response_panel))

                live.update(response_panel)

            messages.append([{
                "role": "user",
                "content": user_input
            }, {    
                "role": "assistant",
                "content": answer
            }])

            print()

    



    