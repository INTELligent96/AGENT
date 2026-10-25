"""Persistent state for DeepSeek chat session."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class ChatState:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.chat_url: Optional[str] = None
        self.message_count: int = 0
        self.files_processed: List[str] = []
        self.last_file: Optional[str] = None
        self.created_at: Optional[datetime] = None
        self.last_used_at: Optional[datetime] = None

    @classmethod
    def load(cls, path: Path) -> "ChatState":
        state = cls(path)
        if not state.path.exists():
            return state
        try:
            data = json.loads(state.path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to load chat state from %s: %s", state.path, e)
            return state

        state.chat_url = data.get("chat_url")
        state.message_count = data.get("message_count", 0)
        state.files_processed = data.get("files_processed", [])
        state.last_file = data.get("last_file")
        try:
            if data.get("created_at"):
                state.created_at = datetime.fromisoformat(data["created_at"])
            if data.get("last_used_at"):
                state.last_used_at = datetime.fromisoformat(data["last_used_at"])
        except (ValueError, TypeError) as e:
            logger.warning("Failed to parse dates in chat state: %s", e)
        return state

    def save(self) -> None:
        now = datetime.now(timezone.utc)
        if self.created_at is None:
            self.created_at = now
        self.last_used_at = now
        data = {
            "chat_url": self.chat_url,
            "message_count": self.message_count,
            "files_processed": self.files_processed[-20:],
            "last_file": self.last_file,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            logger.error("Failed to save chat state: %s", e)

    def reset(self) -> None:
        self.chat_url = None
        self.message_count = 0
        self.files_processed = []
        self.last_file = None
        self.created_at = None
        self.last_used_at = None
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError as e:
            logger.warning("Failed to delete state file: %s", e)

    def age_hours(self) -> float:
        if self.last_used_at is None:
            return 0.0
        now = datetime.now(timezone.utc)
        return (now - self.last_used_at).total_seconds() / 3600.0

    def should_rotate(
        self,
        new_file: Optional[str],
        max_age_hours: float,
        max_messages: int,
        force_new: bool = False,
        rotate_on_file_type_change: bool = False,
    ) -> Tuple[bool, str]:
        if force_new:
            return True, "forced by --new-chat"
        if not self.chat_url:
            return False, "no existing chat, will start fresh"

        age = self.age_hours()
        if age > max_age_hours:
            return True, "chat is %.1fh old (max %.1fh)" % (age, max_age_hours)
        if self.message_count >= max_messages:
            return True, "message limit reached (%d/%d)" % (
                self.message_count, max_messages
            )

        if rotate_on_file_type_change and self.last_file and new_file:
            old_ext = Path(self.last_file).suffix.lower()
            new_ext = Path(new_file).suffix.lower()
            if old_ext and new_ext and old_ext != new_ext:
                return True, "file type changed (%s -> %s)" % (old_ext, new_ext)

        return False, "continuing chat (age=%.1fh, msgs=%d)" % (
            age, self.message_count
        )

    def record_ask(self, file: Optional[str], new_url: Optional[str]) -> None:
        if new_url:
            self.chat_url = new_url
        self.message_count += 1
        if file:
            self.last_file = file
            if file not in self.files_processed:
                self.files_processed.append(file)
        self.save()

    def summary(self) -> str:
        if not self.chat_url:
            return "No active chat."
        return (
            "Chat URL: %s\n"
            "Messages: %d\n"
            "Files: %s\n"
            "Last file: %s\n"
            "Age: %.1fh"
            % (
                self.chat_url,
                self.message_count,
                ", ".join(self.files_processed[-5:]) or "(none)",
                self.last_file or "(none)",
                self.age_hours(),
            )
        )