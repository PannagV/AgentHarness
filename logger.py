"""Append-only JSONL logging for chat sessions."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


class ChatLogger:
    """Persist chat, reasoning, and lifecycle events as JSON Lines."""

    def __init__(
        self,
        log_dir: Path | str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        log_reasoning: bool = True,
    ) -> None:
        root = Path(log_dir) if log_dir is not None else Path(__file__).parent / "logs"
        self.chat_dir = root / "chatlog"
        self.reasoning_dir = root / "reasoning_trace"
        self.chat_dir.mkdir(parents=True, exist_ok=True)
        self.reasoning_dir.mkdir(parents=True, exist_ok=True)

        self.session_id = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        self.model_name = model_name
        self.base_url = base_url
        self.log_reasoning = log_reasoning

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _append_record(path: Path, record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False)
            file.write("\n")
            file.flush()

    def _metadata(self, record_type: str) -> dict[str, Any]:
        record: dict[str, Any] = {
            "timestamp": self._timestamp(),
            "type": record_type,
            "session_id": self.session_id,
        }
        if self.model_name:
            record["model"] = self.model_name
        if self.base_url:
            record["base_url"] = self.base_url
        return record

    def _path_for_today(self, directory: Path, prefix: str) -> Path:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return directory / f"{prefix}_{date}.jsonl"

    def _log_reasoning(self, reasoning: list[str] | None, record_type: str) -> None:
        if not self.log_reasoning or not reasoning:
            return

        record = self._metadata(record_type)
        record["content"] = "".join(reasoning)
        self._append_record(
            self._path_for_today(self.reasoning_dir, "reasoning_trace"),
            record,
        )

    def log_exchange(
        self,
        user_input: str,
        assistant_response: str,
        model_name: str,
        reasoning: list[str] | None = None,
        status: str = "completed",
    ) -> None:
        self.model_name = model_name
        record = self._metadata("exchange")
        record.update(
            {
                "user": user_input,
                "assistant": assistant_response,
                "status": status,
            }
        )
        self._append_record(self._path_for_today(self.chat_dir, "chatlog"), record)
        self._log_reasoning(reasoning, "reasoning")

    def log_interrupted(
        self,
        user_input: str,
        assistant_response: str,
        model_name: str,
        reasoning: list[str] | None = None,
    ) -> None:
        self.model_name = model_name
        record = self._metadata("interrupted")
        record.update(
            {
                "user": user_input,
                "assistant": assistant_response,
                "status": "interrupted",
            }
        )
        self._append_record(self._path_for_today(self.chat_dir, "chatlog"), record)
        self._log_reasoning(reasoning, "reasoning_interrupted")

    def log_error(self, user_input: str, error: str, model_name: str) -> None:
        self.model_name = model_name
        record = self._metadata("error")
        record.update({"user": user_input, "error": error})
        self._append_record(self._path_for_today(self.chat_dir, "chatlog"), record)

    def log_event(self, event_type: str, **data: Any) -> None:
        record = self._metadata(event_type)
        record.update(data)
        self._append_record(self._path_for_today(self.chat_dir, "chatlog"), record)
