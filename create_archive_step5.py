import os
import zipfile
import textwrap

PROJECT_NAME = "agent_timeout_and_stop"

FILES = {
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

safety:
  read_only_originals: true 
  workspace_dir: "workspace" 

agent_loop:
  max_iterations: 10               # Теперь можно ставить сколько угодно (хоть 50)
  task_timeout_seconds: 600        # Максимальное время на ОДНУ задачу (в секундах). 600 = 10 минут.
  code_execution_timeout: 15       # Сколько секунд ждать выполнения тестового кода, прежде чем убить
""",

    "core/__init__.py": "",

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
""",

    "tools/__init__.py": "",

    "tools/validator.py": """\
import subprocess
import sys
import os

def validate_python_code(code: str, timeout_sec: int = 15) -> tuple[bool, str]:
    clean_code = code.replace("```python", "").replace("```", "").strip()
    test_file = "temp_validation_test.py"

    with open(test_file, "w", encoding="utf-8") as f:
        f.write(clean_code)

    try:
        # Передаем таймаут, чтобы бесконечные циклы не вешали агента
        result = subprocess.run(
            [sys.executable, test_file], 
            capture_output=True, 
            text=True, 
            timeout=timeout_sec
        )
        if result.returncode != 0:
            return False, result.stderr
        return True, "OK"
    except subprocess.TimeoutExpired:
        return False, f"Ошибка: Превышено время выполнения кода ({timeout_sec} сек). Возможно, бесконечный цикл."
    except Exception as e:
        return False, str(e)
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
""",

    "core/agent.py": """\
import os
import time
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

        safety = self.config.get("safety", {})
        self.workspace = WorkspaceManager(
            workspace_dir=safety.get("workspace_dir", "workspace"),
            read_only_originals=safety.get("read_only_originals", True)
        )

        # Настройки цикла
        agent_loop = self.config.get("agent_loop", {})
        self.max_iterations = agent_loop.get("max_iterations", 10)
        self.task_timeout = agent_loop.get("task_timeout_seconds", 600)
        self.code_timeout = agent_loop.get("code_execution_timeout", 15)

        # Флаг экстренной остановки
        self._stop_requested = False

    def request_stop(self):
        \"\"\"Вызывается из интерфейса (кнопка 'Стоп'), чтобы прервать работу.\"\"\"
        print("\\n[СИГНАЛ] Получен запрос на экстренную остановку агента!")
        self._stop_requested = True

    def reset_stop_flag(self):
        \"\"\"Сбрасывает флаг перед новой задачей.\"\"\"
        self._stop_requested = False

    def _read_safe(self, file_path: str) -> str:
        safe_path = self.workspace.prepare_file(file_path)
        return extract_text(safe_path, self.tools)

    def generate_code_with_validation(self, task: str) -> str:
        self.reset_stop_flag() # Сбрасываем кнопку стоп перед стартом
        print(f"Генерация кода (лимит: {self.max_iterations} попыток, таймаут: {self.task_timeout} сек)...")

        llm = self.registry.get_model_for_task("code_generation")
        current_prompt = CODE_PROMPT.format(task=task)

        last_generated_code = ""
        start_time = time.time()

        for iteration in range(1, self.max_iterations + 1):
            # 1. Проверка экстренной остановки
            if self._stop_requested:
                print("\\n[ОСТАНОВКА] Агент прерван пользователем. Возвращаю последний результат.")
                return f"--- РАБОТА ПРЕРВАНА ПОЛЬЗОВАТЕЛЕМ ---\\n\\n{last_generated_code}"

            # 2. Проверка таймаута
            elapsed_time = time.time() - start_time
            if elapsed_time > self.task_timeout:
                print(f"\\n[ТАЙМАУТ] Истекло время ({self.task_timeout} сек). Прерываю работу.")
                return f"--- ПРЕВЫШЕН ЛИМИТ ВРЕМЕНИ ({self.task_timeout} сек) ---\\n\\n{last_generated_code}"

            print(f"--- Попытка {iteration} (прошло {int(elapsed_time)} сек) ---")

            # Генерируем код
            code = llm.generate(current_prompt)
            last_generated_code = code # Сохраняем на случай экстренного выхода

            print("Валидация кода...")
            is_valid, error_msg = validate_python_code(code, timeout_sec=self.code_timeout)

            if is_valid:
                print("✅ Код прошел валидацию!")
                return code

            print(f"❌ Ошибка в коде: {error_msg}")
            current_prompt = (
                f"Твой предыдущий код выдал ошибку:\\n{error_msg}\\n\\n"
                f"Вот код, который ты написал:\\n{code}\\n\\n"
                f"Пожалуйста, исправь его и верни только чистый рабочий код. Задача: {task}"
            )

        print("⚠️ Достигнут лимит попыток.")
        return f"--- ДОСТИГНУТ ЛИМИТ ПОПЫТОК ({self.max_iterations}) ---\\n\\n{last_generated_code}"

    # Остальные методы (summarize, check_spelling, structure) оставляем без изменений
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

    def save_text_to_word(self, text: str, output_path: str):
        create_simple_docx(text, output_path)
        return output_path
""",

    "test_stop_and_timeout.py": """\
import threading
import time
from core.agent import Agent

def main():
    agent = Agent("config.yaml")

    print("=== ТЕСТ: Итерации, Таймаут и Экстренная остановка ===")

    # Мы запустим агента в отдельном потоке (как это будет в интерфейсе),
    # чтобы иметь возможность нажать "Стоп" во время его работы.

    task = "Напиши сложную функцию с кучей условий, чтобы модель думала подольше."

    # Функция-обертка для запуска в потоке
    def run_agent():
        print("Агент начал работу...")
        result = agent.generate_code_with_validation(task)
        print("\\nРезультат агента:\\n", result)

    agent_thread = threading.Thread(target=run_agent)
    agent_thread.start()

    # Симулируем нажатие кнопки "Стоп" через 3 секунды
    print("Ждем 3 секунды и нажимаем 'Стоп' (симуляция)...")
    time.sleep(3)
    agent.request_stop()

    # Ждем завершения потока
    agent_thread.join()
    print("Тест завершен.")

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
    print(f"\\nГотово! Архив {zip_name} создан.")


if __name__ == "__main__":
    create_project()