import os
import zipfile
import textwrap

PROJECT_NAME = "agent_safety_and_validation"

FILES = {
    # Обновленный конфиг (добавили блоки безопасности)
    "config.yaml": """\
llm_profiles:
  local_coder:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen-qwen2.5-coder-14b-instruct"
  local_logic:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "deepseek-r1-0528-qwen3-8b-abliterated"
  local_fast:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen2.5-7b-instruct-uncensored"

routing:
  default_model: "local_fast"
  code_generation: "local_coder"
  complex_reasoning: "local_logic"

tools:
  tesseract_path: "K:/Program Files/Tesseract-OCR/tesseract.exe"
  use_ms_office: true 

# НОВЫЕ БЛОКИ НАСТРОЕК
safety:
  read_only_originals: true # Запрет на изменение оригиналов
  workspace_dir: "workspace" # Куда копировать файлы для работы

agent_loop:
  max_iterations: 3 # Сколько раз пытаться исправить код/текст
""",

    "core/__init__.py": "",

    # Модуль безопасной работы с файлами
    "core/workspace.py": """\
import os
import shutil
from pathlib import Path

class WorkspaceManager:
    def __init__(self, workspace_dir="workspace", read_only_originals=True):
        self.workspace_dir = Path(workspace_dir)
        self.read_only_originals = read_only_originals
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def prepare_file(self, original_path: str) -> str:
        \"\"\"
        Берет исходный файл, делает копию в workspace и возвращает путь к копии.
        Если read_only_originals выключен, возвращает оригинал (не рекомендуется).
        \"\"\"
        if not self.read_only_originals:
            return original_path

        original_path = Path(original_path)
        if not original_path.exists():
            raise FileNotFoundError(f"Файл {original_path} не найден.")

        # Создаем копию с префиксом, чтобы не перезаписать существующую
        copy_name = f"safe_{original_path.name}"
        copy_path = self.workspace_dir / copy_name

        # Копируем файл
        shutil.copy2(original_path, copy_path)
        print(f"[Безопасность] Создана копия: {copy_path}")
        return str(copy_path)
""",

    # Валидатор (проверяет код на ошибки)
    "tools/__init__.py": "",
    "tools/validator.py": """\
import subprocess
import sys
import os

def validate_python_code(code: str) -> tuple[bool, str]:
    \"\"\"
    Проверяет Python код, запуская его в изолированном процессе.
    Возвращает (успех, сообщение_об_ошибке).
    \"\"\"
    # Очищаем код от markdown-разметки, если она есть
    clean_code = code.replace("```python", "").replace("```", "").strip()

    test_file = "temp_validation_test.py"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(clean_code)

    try:
        # Запускаем код. Если есть синтаксические ошибки, они вылезут в stderr
        result = subprocess.run([sys.executable, test_file], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return False, result.stderr
        return True, "OK"
    except subprocess.TimeoutExpired:
        return False, "Ошибка: Время выполнения кода истекло (бесконечный цикл?)"
    except Exception as e:
        return False, str(e)
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
""",

    # Обновленный оркестратор
    "core/agent.py": """\
import os
import yaml
from llm.registry import LLMRegistry
from documents.extractors import extract_text
from documents.writers import create_simple_docx
from core.prompts import SUMMARIZE_PROMPT, STRUCTURE_PROMPT, SPELLCHECK_PROMPT, CODE_PROMPT
from core.workspace import WorkspaceManager
from tools.validator import validate_python_code

class Agent:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.tools = self.config.get("tools", {})
        self.registry = LLMRegistry(config_path)

        # Инициализируем безопасность и циклы
        safety = self.config.get("safety", {})
        self.workspace = WorkspaceManager(
            workspace_dir=safety.get("workspace_dir", "workspace"),
            read_only_originals=safety.get("read_only_originals", True)
        )
        self.max_iterations = self.config.get("agent_loop", {}).get("max_iterations", 3)

    def _read_safe(self, file_path: str) -> str:
        \"\"\"Безопасно читает файл, делая копию.\"\"\"
        safe_path = self.workspace.prepare_file(file_path)
        return extract_text(safe_path, self.tools)

    def summarize_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        llm = self.registry.get_model_for_task("default_model")
        return llm.generate(SUMMARIZE_PROMPT.format(text=text[:8000]))

    def check_spelling_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        llm = self.registry.get_model_for_task("default_model")
        return llm.generate(SPELLCHECK_PROMPT.format(text=text[:8000]))

    def structure_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        llm = self.registry.get_model_for_task("complex_reasoning")
        return llm.generate(STRUCTURE_PROMPT.format(text=text[:8000]))

    def generate_code_with_validation(self, task: str) -> str:
        \"\"\"Пишет код и итеративно исправляет его, если есть ошибки.\"\"\"
        print(f"Генерация кода (максимум {self.max_iterations} попыток)...")
        llm = self.registry.get_model_for_task("code_generation")

        current_prompt = CODE_PROMPT.format(task=task)
        code = ""

        for iteration in range(1, self.max_iterations + 1):
            print(f"--- Попытка {iteration} ---")
            code = llm.generate(current_prompt)

            print("Валидация кода...")
            is_valid, error_msg = validate_python_code(code)

            if is_valid:
                print("✅ Код прошел валидацию!")
                return code

            print(f"❌ Ошибка в коде: {error_msg}")
            # Если код не прошел, добавляем ошибку в промпт для следующей итерации
            current_prompt = (
                f"Твой предыдущий код выдал ошибку:\\n{error_msg}\\n\\n"
                f"Вот код, который ты написал:\\n{code}\\n\\n"
                f"Пожалуйста, исправь его и верни только чистый рабочий код. Задача: {task}"
            )

        print("⚠️ Достигнут лимит попыток. Возвращаю последний вариант.")
        return code

    def save_text_to_word(self, text: str, output_path: str):
        create_simple_docx(text, output_path)
        return output_path
""",

    "test_safety_and_validation.py": """\
import os
from core.agent import Agent

def main():
    agent = Agent("config.yaml")

    # --- ТЕСТ 1: Безопасность исходников ---
    print("=== ТЕСТ 1: Защита оригиналов (Workspace) ===")
    # Создаем файл в корне
    orig_file = "my_precious_data.txt"
    with open(orig_file, "w", encoding="utf-8") as f:
        f.write("Этот текст нельзя менять!")

    print("Отправляем файл агенту на проверку...")
    # Агент должен создать копию в workspace и работать с ней
    result = agent.check_spelling_file(orig_file)
    print("Результат агента:", result)

    # Проверяем, изменился ли оригинал
    with open(orig_file, "r", encoding="utf-8") as f:
        content = f.read()
    print(f"Содержимое оригинала: '{content}'")
    if content == "Этот текст нельзя менять!":
        print("✅ Оригинал не тронут!")
    else:
        print("❌ ОРИГИНАЛ БЫЛ ИЗМЕНЕН!")

    # --- ТЕСТ 2: Итеративная валидация кода ---
    print("\\n=== ТЕСТ 2: Итерации и валидация кода ===")
    # Специально даем задачу, где легко ошибиться (например, деление на ноль)
    # или просто сложную задачу, чтобы посмотреть, как работает цикл
    task = "Напиши функцию, которая принимает список чисел и возвращает среднее арифметическое. Обработай случай пустого списка."
    print(f"Задача: {task}")

    final_code = agent.generate_code_with_validation(task)
    print("\\nФинальный код:\\n", final_code)

if __name__ == "__main__":
    main()
"""
}


def create_project():
    print(f"Создание проекта {PROJECT_NAME}...")
    for filepath, content in FILES.items():
        clean_content = textwrap.dedent(content)
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(clean_content)
        print(f"  Создан/обновлен: {filepath}")

    zip_name = f"{PROJECT_NAME}.zip"
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filepath in FILES.keys():
            zipf.write(filepath)
    print(f"\\nГотово! Архив {zip_name} создан. Распакуй его в папку проекта.")


if __name__ == "__main__":
    create_project()