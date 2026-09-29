"""Terminal input handling for multiline prompts and cancellation."""

from dataclasses import dataclass

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


@dataclass
class InputResult:
    text: str = ""
    cancelled: bool = False
    exited: bool = False


class MultilineInput:
    """Prompt-toolkit based multiline input session."""

    def __init__(self) -> None:
        self.session = PromptSession()
        self.key_bindings = KeyBindings()

        @self.key_bindings.add("enter")
        def insert_newline(event) -> None:
            event.current_buffer.insert_text("\n")

        @self.key_bindings.add("c-j")
        def submit_with_ctrl_enter(event) -> None:
            event.app.exit(result=InputResult(text=event.current_buffer.text))

        @self.key_bindings.add("escape", "enter")
        def submit_with_escape_enter(event) -> None:
            event.app.exit(result=InputResult(text=event.current_buffer.text))

        @self.key_bindings.add("c-q")
        def cancel_input(event) -> None:
            event.app.exit(result=InputResult(cancelled=True))

    async def prompt(self) -> InputResult:
        result = await self.session.prompt_async(
            "User > ",
            multiline=True,
            key_bindings=self.key_bindings,
            prompt_continuation="... ",
            bottom_toolbar="Enter: newline | Ctrl+Enter/Ctrl+J: submit | Ctrl+Q: cancel",
        )
        return result if isinstance(result, InputResult) else InputResult(text=result)
