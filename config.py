"""Configuration from .env."""
import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

load_dotenv()

_SEP = ";" if os.name == "nt" else ":"


class Config:
    def __init__(self) -> None:
        self.auth_path = Path(os.getenv("DEEPSEEK_AUTH_PATH", "auth.json"))
        allowed = os.getenv("ALLOWED_DIRS", ".")
        self.allowed_dirs: List[Path] = [
            Path(p.strip()).expanduser().resolve()
            for p in allowed.split(_SEP)
            if p.strip()
        ]
        self.log_path = Path(os.getenv("AUDIT_LOG", "audit.log"))
        self.thinking = os.getenv("DEEPSEEK_THINKING", "false").lower() == "true"

    def is_allowed(self, path: Path) -> bool:
        try:
            p = path.expanduser().resolve()
        except Exception:
            return False
        for d in self.allowed_dirs:
            if p == d:
                return True
            try:
                p.relative_to(d)
                return True
            except ValueError:
                continue
        return False


config = Config()
