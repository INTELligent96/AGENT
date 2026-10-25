import os
import time
import yaml
import shutil
from pathlib import Path
from llm.registry import LLMRegistry
from documents.extractors import extract_text
from documents.writers import create_simple_docx
from core.prompts import SUMMARIZE_PROMPT, STRUCTURE_PROMPT, SPELLCHECK_PROMPT, CODE_PROMPT
from core.workspace import WorkspaceManager
from tools.validator import validate_python_code
from tools.file_manager import generate_file_list
from tools.excel_tools import create_excel_chart
from tools.web_search import search_web
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
        self.output_dir = "output"
        Path(self.output_dir).mkdir(exist_ok=True)

    @property
    def rag(self):
        if self._rag is None:
            self._rag = RAGQuestionAnswerer(self.config, self.tools, self.registry)
        return self._rag

    # --- НОВЫЕ ИНСТРУМЕНТЫ ---
    def make_file_list(self, folder_path: str, recursive: bool) -> str:
        print(f"Генерация списка файлов: {folder_path}")
        return generate_file_list(folder_path, recursive, self.output_dir)

    def make_excel_chart(self, file_path: str) -> str:
        print(f"Создание графика для: {file_path}")
        return create_excel_chart(file_path, self.output_dir)

    def classify_files(self, folder_path: str) -> str:
        """Сортирует файлы по категориям (копирует, не двигает)."""
        folder = Path(folder_path)
        sorted_dir = Path(self.output_dir) / f"sorted_{folder.name}"
        sorted_dir.mkdir(parents=True, exist_ok=True)

        files = [f for f in folder.iterdir() if f.is_file()]
        for f in files:
            text = extract_text(str(f), self.tools)[:2000] # Берем кусок для анализа
            prompt = f"Определи категорию документа (одним словом: Договор, Счет, Отчет, Письмо, Прочее). Текст: {text}"
            category = self.registry.generate_with_fallback("default_model", prompt).strip()
            # Очищаем от мусора
            category = category.split()[0].replace('.', '').replace('"', '').replace("'", "")

            cat_dir = sorted_dir / category
            cat_dir.mkdir(exist_ok=True)
            shutil.copy2(f, cat_dir / f.name)

        return str(sorted_dir)

    def batch_summarize(self, folder_path: str) -> str:
        """Делает резюме для всех файлов и собирает в один Word."""
        folder = Path(folder_path)
        files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in ['.txt', '.docx', '.pdf']]

        final_text = ""
        for f in files:
            text = self._read_safe(str(f))
            if text.startswith("[Ошибка]"): continue

            prompt = SUMMARIZE_PROMPT.format(text=text[:6000])
            summary = self.registry.generate_with_fallback("default_model", prompt)
            final_text += f"=== РЕЗЮМЕ ФАЙЛА: {f.name} ===\n{summary}\n\n"

        out_file = Path(self.output_dir) / f"batch_summary_{folder.name}.docx"
        create_simple_docx(final_text, str(out_file))
        return str(out_file)

    def web_search(self, query: str) -> str:
        print(f"Поиск в интернете: {query}")
        return search_web(query)

    # --- БАЗОВЫЕ МЕТОДЫ ---
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
        current_prompt = CODE_PROMPT.format(task=task)
        last_generated_code = ""
        start_time = time.time()

        for iteration in range(1, self.max_iterations + 1):
            if self._stop_requested: return f"--- ПРЕРВАНО ---\n\n{last_generated_code}"
            if time.time() - start_time > self.task_timeout: return f"--- ТАЙМАУТ ---\n\n{last_generated_code}"

            code = self.registry.generate_with_fallback("code_generation", current_prompt)
            last_generated_code = code

            if code.startswith("[КРИТИЧЕСКАЯ ОШИБКА]") or code.startswith("[ВНИМАНИЕ:"): return code

            is_valid, error_msg = validate_python_code(code, timeout_sec=self.code_timeout)
            if is_valid: return code

            current_prompt = f"Твой предыдущий код выдал ошибку:\n{error_msg}\n\nКод:\n{code}\n\nИсправь. Задача: {task}"
        return f"--- ЛИМИТ ПОПЫТОК ---\n\n{last_generated_code}"

    def summarize_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        return self.registry.generate_with_fallback("default_model", SUMMARIZE_PROMPT.format(text=text[:8000]))

    def check_spelling_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        return self.registry.generate_with_fallback("default_model", SPELLCHECK_PROMPT.format(text=text[:8000]))

    def structure_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        return self.registry.generate_with_fallback("complex_reasoning", STRUCTURE_PROMPT.format(text=text[:8000]))
