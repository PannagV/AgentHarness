"""Command-line entry point for Icebreaker."""

import asyncio

from main import run


def main() -> None:
    """Start the interactive Icebreaker session."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
