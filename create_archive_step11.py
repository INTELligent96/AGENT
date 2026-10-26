import os
import zipfile
import textwrap

PROJECT_NAME = "agent_fix_path_extraction"

FILES = {
    # Патчим ТОЛЬКО метод _extract_path_from_text в core/agent.py
    # Для этого проще заменить весь файл, чтобы не рисковать с частичными заменами
    "core/agent.py": """\
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
from core.router import IntentRouter
from core.self_check import Critic
from tools.validator import validate_python_code
from tools.file_manager import generate_file_list
from tools.excel_tools import create_excel_chart
from tools.web_search import search_web
from tools.long_doc import LongDocumentProcessor
from rag.qa import RAGQuestionAnswerer

class Agent:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.tools = self.config.get("tools", {})
        self.registry = LLMRegistry(config_path)
        self.router = IntentRouter(self.registry, self.config)
        self.critic = Critic(self.registry, self.config)

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
        self.last_generated_code = ""

    @property
    def rag(self):
        if self._rag is None:
            self._rag = RAGQuestionAnswerer(self.config, self.tools, self.registry)
        return self._rag

    # ============ ГЛАВНЫЙ ОРКЕСТРАТОР ============
    def run_task(self, user_text: str, log_callback=None) -> str:
        def log(msg):
            print(msg)
            if log_callback: log_callback(msg)

        log("[Роутер] Анализирую запрос...")
        routing = self.router.classify(user_text)
        tools = routing.get("tools", ["ask_question"])
        log(f"[Роутер] → {tools} ({routing.get('reasoning', '')})")

        results = []
        for tool_name in tools:
            log(f"\\n[Инструмент] {tool_name}")
            try:
                result = self._execute_tool(tool_name, user_text, log)
                results.append(f"=== {tool_name} ===\\n{result}")
            except Exception as e:
                log(f"[Ошибка] {tool_name}: {e}")
                results.append(f"=== {tool_name} (ОШИБКА) ===\\n{e}")

        return "\\n\\n".join(results) if len(results) > 1 else results[0]

    def _execute_tool(self, tool_name: str, user_text: str, log) -> str:
        if tool_name == "ask_question":
            def gen(feedback):
                base = user_text if not feedback else f"{user_text}\\n\\n{feedback}"
                return self.ask_question(base)
            return self.critic.run_with_retry(gen, task=user_text, task_type="rag")

        if tool_name == "summarize_file":
            file_path = self._extract_path_from_text(user_text)
            if not file_path:
                return "Укажите файл: 'сделай резюме путь/к/файлу'"
            def gen(feedback):
                text = self._read_safe(file_path)
                prompt = SUMMARIZE_PROMPT.format(text=text[:8000])
                if feedback: prompt = f"{prompt}\\n\\n{feedback}"
                return self.registry.generate_with_fallback("default_model", prompt)
            return self.critic.run_with_retry(gen, task=user_text, task_type="summarize")

        if tool_name == "check_spelling":
            file_path = self._extract_path_from_text(user_text)
            if not file_path:
                return "Укажите файл: 'проверь ошибки путь/к/файлу'"
            return self.check_spelling_file(file_path)

        if tool_name == "generate_code":
            return self.generate_code_with_validation(user_text)

        if tool_name == "batch_summarize":
            folder = self._extract_path_from_text(user_text)
            if not folder: return "Укажите папку."
            return self.batch_summarize(folder)

        if tool_name == "classify_files":
            folder = self._extract_path_from_text(user_text)
            if not folder: return "Укажите папку."
            return self.classify_files(folder)

        if tool_name == "make_file_list":
            folder = self._extract_path_from_text(user_text)
            if not folder: return "Укажите папку."
            return self.make_file_list(folder, recursive=True)

        if tool_name == "make_excel_chart":
            file_path = self._extract_path_from_text(user_text)
            if not file_path: return "Укажите Excel-файл."
            return self.make_excel_chart(file_path)

        if tool_name == "web_search":
            return self.web_search(user_text)

        if tool_name == "process_long_doc":
            file_path = self._extract_path_from_text(user_text)
            if not file_path: return "Укажите файл."
            return self.process_long_document(file_path)

        if tool_name == "index_folder":
            folder = self._extract_path_from_text(user_text)
            if not folder: return "Укажите папку."
            return self.index_folder(folder)

        if tool_name == "open_style_studio":
            return "[Откройте вкладку 'Студия стилей Word' в левой панели интерфейса]"

        return f"[Неизвестный инструмент: {tool_name}]"

    def _extract_path_from_text(self, text: str) -> str:
        \"\"\"Ищет путь в тексте. Без regex — просто по токенам с известными расширениями.\"\"\"
        exts = (
            '.txt', '.docx', '.doc', '.pdf', '.xlsx', '.xls', '.csv',
            '.png', '.jpg', '.jpeg', '.bmp', '.tiff'
        )
        # Символы, которые нужно убрать с краёв токена
        bad_chars = ('"', "'", '`', '(', ')', '[', ']', '{', '}', '<', '>', ',', ';', ':', '!', '?')
        for raw_token in text.split():
            token = raw_token
            # Убираем обрамляющие кавычки и скобки
            changed = True
            while changed and token:
                changed = False
                if token[0] in bad_chars:
                    token = token[1:]
                    changed = True
                if token and token[-1] in bad_chars:
                    token = token[:-1]
                    changed = True
            if not token:
                continue
            if token.lower().endswith(exts):
                return token
        return None

    # ============ ИНСТРУМЕНТЫ ============
    def ask_question(self, question: str) -> str:
        return self.rag.ask(question)

    def check_spelling_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        prompt = SPELLCHECK_PROMPT.format(text=text[:8000])
        return self.registry.generate_with_fallback("default_model", prompt)

    def generate_code_with_validation(self, task: str) -> str:
        self.reset_stop_flag()
        current_prompt = CODE_PROMPT.format(task=task)
        last_code = ""
        start_time = time.time()

        for iteration in range(1, self.max_iterations + 1):
            if self._stop_requested: return f"--- ПРЕРВАНО ---\\n\\n{last_code}"
            if time.time() - start_time > self.task_timeout: return f"--- ТАЙМАУТ ---\\n\\n{last_code}"

            code = self.registry.generate_with_fallback("code_generation", current_prompt)
            last_code = code

            if code.startswith("[КРИТИЧЕСКАЯ") or code.startswith("[ВНИМАНИЕ:"): return code

            is_valid, error_msg = validate_python_code(code, timeout_sec=self.code_timeout)
            if is_valid:
                if self.critic.enabled and self.critic.force_always:
                    verdict = self.critic.check_general(task, code, "code")
                    print(f"  [Критик-код] score={verdict.get('score')}")
                    if verdict.get("verdict") != "accept" or verdict.get("score", 0) < self.critic.min_score:
                        current_prompt = (
                            f"Код работает, но критик нашёл проблемы: {verdict.get('issues')}\\n"
                            f"Перепиши, устранив их. Задача: {task}\\nКод:\\n{code}"
                        )
                        continue
                return code

            current_prompt = f"Твой предыдущий код упал: {error_msg}\\n\\nКод:\\n{code}\\n\\nИсправь. Задача: {task}"
        return f"--- ЛИМИТ ПОПЫТОК ---\\n\\n{last_code}"

    def summarize_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        return self.registry.generate_with_fallback("default_model", SUMMARIZE_PROMPT.format(text=text[:8000]))

    def structure_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        return self.registry.generate_with_fallback("complex_reasoning", STRUCTURE_PROMPT.format(text=text[:8000]))

    def process_long_document(self, file_path: str) -> str:
        processor = LongDocumentProcessor(self.config, self.tools, self.registry, self.output_dir)
        return processor.process(file_path)

    def make_file_list(self, folder_path: str, recursive: bool) -> str:
        return generate_file_list(folder_path, recursive, self.output_dir)

    def make_excel_chart(self, file_path: str) -> str:
        return create_excel_chart(file_path, self.output_dir)

    def classify_files(self, folder_path: str) -> str:
        folder = Path(folder_path)
        sorted_dir = Path(self.output_dir) / f"sorted_{folder.name}"
        sorted_dir.mkdir(parents=True, exist_ok=True)
        for f in [x for x in folder.iterdir() if x.is_file()]:
            text = extract_text(str(f), self.tools)[:2000]
            prompt = f"Определи категорию (одним словом: Договор, Счет, Отчет, Письмо, Прочее). Текст: {text}"
            cat = self.registry.generate_with_fallback("default_model", prompt).strip().split()[0]
            cat = cat.replace('.', '').replace('"', '').replace("'", "")
            (sorted_dir / cat).mkdir(exist_ok=True)
            shutil.copy2(f, sorted_dir / cat / f.name)
        return str(sorted_dir)

    def batch_summarize(self, folder_path: str) -> str:
        folder = Path(folder_path)
        final = ""
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in ['.txt', '.docx', '.pdf']:
                text = self._read_safe(str(f))
                if text.startswith("[Ошибка]"): continue
                s = self.registry.generate_with_fallback("default_model", SUMMARIZE_PROMPT.format(text=text[:6000]))
                final += f"=== {f.name} ===\\n{s}\\n\\n"
        out = Path(self.output_dir) / f"batch_summary_{folder.name}.docx"
        create_simple_docx(final, str(out))
        return str(out)

    def web_search(self, query: str) -> str:
        return search_web(query)

    def index_folder(self, folder_path: str):
        return self.rag.indexer.index_folder(folder_path)

    def request_stop(self):
        self._stop_requested = True

    def reset_stop_flag(self):
        self._stop_requested = False

    def _read_safe(self, file_path: str) -> str:
        safe_path = self.workspace.prepare_file(file_path)
        return extract_text(safe_path, self.tools)
"""
}


def create_project():
    print(f"Применение патча {PROJECT_NAME}...")
    for filepath, content in FILES.items():
        clean_content = textwrap.dedent(content)
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(clean_content)
        print(f"  Обновлен: {filepath}")

    zip_name = f"{PROJECT_NAME}.zip"
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filepath in FILES.keys():
            zipf.write(filepath)
    print(f"\\nГотово! Архив {zip_name} создан.")


if __name__ == "__main__":
    create_project()