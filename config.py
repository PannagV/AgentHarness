from rich.console import Console

console = Console()

def help():
    console.log(""" Available commands:
    /help , /h - Show this help message
    /exit , /quit - Exit the program
    /reset - Reset the conversation
    /model - Change the model
    /id - Show the current conversation ID
    /history - Show the conversation history
    /clear - Clear the conversation history
    """)