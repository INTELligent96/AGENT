import os
import shutil
from pathlib import Path

class WorkspaceManager:
    def __init__(self, workspace_dir="workspace", read_only_originals=True):
        self.workspace_dir = Path(workspace_dir)
        self.read_only_originals = read_only_originals
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def prepare_file(self, original_path: str) -> str:
        if not self.read_only_originals:
            return original_path

        original_path = Path(original_path)
        if not original_path.exists():
            raise FileNotFoundError(f"Файл {original_path} не найден.")

        copy_name = f"safe_{original_path.name}"
        copy_path = self.workspace_dir / copy_name
        shutil.copy2(original_path, copy_path)
        print(f"[Безопасность] Создана копия: {copy_path}")
        return str(copy_path)
