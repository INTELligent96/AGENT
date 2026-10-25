import os
import time
import yaml
from llm.registry import LLMRegistry
from documents.extractors import extract_text
from documents.writers import create_simple_docx
from core.prompts import SUMMARIZE_PROMPT, STRUCTURE_PROMPT, SPELLCHECK_PROMPT, CODE_PROMPT
from core.workspace import WorkspaceManager
from tools.validator import validate_python_code
from rag.qa import RAGQuestionAnswerer

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

        agent_loop = self.config.get("agent_loop", {})
        self.max_iterations = agent_loop.get("max_iterations", 10)
        self.task_timeout = agent_loop.get("task_timeout_seconds", 600)
        self.code_timeout = agent_loop.get("code_execution_timeout", 15)

        self._stop_requested = False
        self._rag = None

    @property
    def rag(self):
        if self._rag is None:
            self._rag = RAGQuestionAnswerer(self.config, self.tools, self.registry)
        return self._rag

    def index_folder(self, folder_path: str):
        return self.rag.indexer.index_folder(folder_path)

    def ask_question(self, question: str) -> str:
        return self.rag.ask(question)

    def request_stop(self):
        self._stop_requested = True

    def reset_stop_flag(self):
        self._stop_requested = False

    def _read_safe(self, file_path: str) -> str:
        safe_path = self.workspace.prepare_file(file_path)
        return extract_text(safe_path, self.tools)

    def generate_code_with_validation(self, task: str) -> str:
        self.reset_stop_flag()
        print(f"Генерация кода (лимит: {self.max_iterations} попыток)...")

        current_prompt = CODE_PROMPT.format(task=task)
        last_generated_code = ""
        start_time = time.time()

        for iteration in range(1, self.max_iterations + 1):
            if self._stop_requested:
                return f"--- РАБОТА ПРЕРВАНА ---\n\n{last_generated_code}"

            if time.time() - start_time > self.task_timeout:
                return f"--- ПРЕВЫШЕН ЛИМИТ ВРЕМЕНИ ---\n\n{last_generated_code}"

            print(f"--- Попытка {iteration} ---")

            # Вызываем через Роутер!
            code = self.registry.generate_with_fallback("code_generation", current_prompt)
            last_generated_code = code

            # Если роутер вернул ошибку, нет смысла валидировать этот текст как код
            if code.startswith("[КРИТИЧЕСКАЯ ОШИБКА]") or code.startswith("[ВНИМАНИЕ:"):
                return code

            print("Валидация кода...")
            is_valid, error_msg = validate_python_code(code, timeout_sec=self.code_timeout)
            if is_valid:
                print("✅ Код прошел валидацию!")
                return code

            print(f"❌ Ошибка в коде: {error_msg}")
            current_prompt = (
                f"Твой предыдущий код выдал ошибку:\n{error_msg}\n\n"
                f"Вот код:\n{code}\n\n"
                f"Пожалуйста, исправь его и верни только чистый рабочий код. Задача: {task}"
            )
        return f"--- ДОСТИГНУТ ЛИМИТ ПОПЫТОК ---\n\n{last_generated_code}"

    def summarize_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        prompt = SUMMARIZE_PROMPT.format(text=text[:8000])
        return self.registry.generate_with_fallback("default_model", prompt)

    def check_spelling_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        prompt = SPELLCHECK_PROMPT.format(text=text[:8000])
        return self.registry.generate_with_fallback("default_model", prompt)

    def structure_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        prompt = STRUCTURE_PROMPT.format(text=text[:8000])
        return self.registry.generate_with_fallback("complex_reasoning", prompt)

    def save_text_to_word(self, text: str, output_path: str):
        create_simple_docx(text, output_path)
        return output_path
