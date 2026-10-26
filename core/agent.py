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
from plugins.loader import load_plugins


class Agent:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.tools = self.config.get("tools", {})
        self.registry = LLMRegistry(config_path)
        self.router = IntentRouter(self.registry, self.config)
        self.critic = Critic(self.registry, self.config)

        plugins_dir = self.config.get("plugins", {}).get("dir", "plugins")
        self.plugins = load_plugins(plugins_dir)
        self.router.attach_plugins(self.plugins)

        safety = self.config.get("safety", {})
        self.workspace = WorkspaceManager(
            workspace_dir=safety.get("workspace_dir", "workspace"),
            read_only_originals=safety.get("read_only_originals", True)
        )

        self.allowed_paths = [p.strip() for p in safety.get("allowed_paths", []) if str(p).strip()]
        self._indexed_folders = set()

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

    # ============ SANDBOX ============
    def _is_path_allowed(self, path):
        if not self.allowed_paths:
            return True
        try:
            target = os.path.abspath(path).lower()
        except Exception:
            return False
        for allowed in self.allowed_paths:
            try:
                a = os.path.abspath(allowed).lower()
            except Exception:
                continue
            if target == a or target.startswith(a + os.sep):
                return True
        return False

    def _require_allowed(self, path):
        if self._is_path_allowed(path):
            return None
        return "[Ошибка] Путь вне разрешённых директорий: " + str(path)

    def set_allowed_paths(self, paths):
        self.allowed_paths = [p.strip() for p in paths if str(p).strip()]
        if "safety" not in self.config:
            self.config["safety"] = {}
        self.config["safety"]["allowed_paths"] = self.allowed_paths
        with open("config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, allow_unicode=True, sort_keys=False)

    def _extract_folder_from_text(self, text):
        bad = ("\"", "'", "`", "(", ")", "[", "]", "{", "}", "<", ">", ",", ";", "!", "?")
        for raw in text.split():
            t = raw
            ch = True
            while ch and t:
                ch = False
                if t[0] in bad:
                    t = t[1:]
                    ch = True
                if t and t[-1] in bad:
                    t = t[:-1]
                    ch = True
            if not t:
                continue
            if os.path.isdir(t):
                return t
        return None

    def ask_about_folder(self, user_text):
        folder = self._extract_folder_from_text(user_text)
        if not folder:
            return "Укажите существующую папку. Пример: что в папке D:/Docs? кто директор?"
        err = self._require_allowed(folder)
        if err:
            return err
        abs_folder = os.path.abspath(folder)
        if abs_folder not in self._indexed_folders:
            print("[Auto-Index] Индексирую папку: " + folder)
            self.rag.indexer.index_folder(folder)
            self._indexed_folders.add(abs_folder)
        question = user_text.replace(folder, "").strip()
        # Убираем общие слова про папку, чтобы понять, есть ли специфичный вопрос
        generic = ["расскажи", "кратко", "обзор", "покажи", "о папке", "про папку", "что в", "что находится", "проанализируй", "опиши", "дай обзор", "перескажи", "папке", "папки", "папку", "каталоге", "каталог"]
        specific = question
        for gw in generic:
            specific = specific.replace(gw, " ")
        specific = specific.strip(" ?!.,;:\t\n")
        if len(specific) < 5:
            question = "Сделай краткий обзор содержимого этих документов. Какие темы/вопросы они освещают?"
        return self.ask_question(question)

    # ============ ГЛАВНЫЙ ОРКЕСТРАТОР ============
    def run_task(self, user_text, log_callback=None):
        def log(msg):
            print(msg)
            if log_callback:
                log_callback(msg)

        log("[Роутер] Анализирую запрос...")
        routing = self.router.classify(user_text)
        tools = routing.get("tools", ["ask_question"])
        log("[Роутер] -> " + str(tools) + " (" + routing.get("reasoning", "") + ")")

        results = []
        for tool_name in tools:
            log("\n[Инструмент] " + tool_name)
            try:
                result = self._execute_tool(tool_name, user_text, log)
                results.append("=== " + tool_name + " ===\n" + str(result))
            except Exception as e:
                log("[Ошибка] " + tool_name + ": " + str(e))
                results.append("=== " + tool_name + " (ОШИБКА) ===\n" + str(e))

        return "\n\n".join(results) if len(results) > 1 else results[0]

    def _execute_tool(self, tool_name, user_text, log):
        if tool_name in self.plugins:
            plugin = self.plugins[tool_name]
            log("[Плагин] Выполняю: " + plugin.name)
            try:
                return plugin.execute(user_text, self)
            except Exception as e:
                return "[Ошибка плагина " + plugin.name + "]: " + str(e)

        if tool_name == "ask_about_folder":
            return self.ask_about_folder(user_text)

        if tool_name == "ask_question":
            def gen(feedback):
                base = user_text if not feedback else (user_text + "\n\n" + feedback)
                return self.ask_question(base)
            return self.critic.run_with_retry(gen, task=user_text, task_type="rag")

        if tool_name == "summarize_file":
            fp = self._extract_path_from_text(user_text)
            if not fp:
                return "Укажите файл: 'сделай резюме путь/к/файлу'"
            def gen(feedback):
                text = self._read_safe(fp)
                prompt = SUMMARIZE_PROMPT.format(text=text[:8000])
                if feedback:
                    prompt = prompt + "\n\n" + feedback
                return self.registry.generate_with_fallback("default_model", prompt)
            return self.critic.run_with_retry(gen, task=user_text, task_type="summarize")

        if tool_name == "check_spelling":
            fp = self._extract_path_from_text(user_text)
            if not fp:
                return "Укажите файл: 'проверь ошибки путь/к/файлу'"
            return self.check_spelling_file(fp)

        if tool_name == "generate_code":
            return self.generate_code_with_validation(user_text)

        if tool_name == "batch_summarize":
            f = self._extract_folder_from_text(user_text) or self._extract_path_from_text(user_text)
            if not f: return "Укажите папку."
            return self.batch_summarize(f)

        if tool_name == "classify_files":
            f = self._extract_folder_from_text(user_text)
            if not f: return "Укажите папку."
            return self.classify_files(f)

        if tool_name == "make_file_list":
            f = self._extract_folder_from_text(user_text)
            if not f: return "Укажите папку."
            return self.make_file_list(f, recursive=True)

        if tool_name == "make_excel_chart":
            fp = self._extract_path_from_text(user_text)
            if not fp: return "Укажите Excel-файл."
            return self.make_excel_chart(fp)

        if tool_name == "web_search":
            return self.web_search(user_text)

        if tool_name == "process_long_doc":
            fp = self._extract_path_from_text(user_text)
            if not fp: return "Укажите файл."
            return self.process_long_document(fp)

        if tool_name == "index_folder":
            f = self._extract_folder_from_text(user_text)
            if not f: return "Укажите папку."
            return self.index_folder(f)

        if tool_name == "open_style_studio":
            return "[Откройте вкладку 'Студия стилей Word' в левой панели интерфейса]"

        return "[Неизвестный инструмент: " + tool_name + "]"

    def _extract_path_from_text(self, text):
        exts = ('.txt', '.docx', '.doc', '.pdf', '.xlsx', '.xls', '.csv', '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.py', '.json', '.md', '.html', '.xml', '.yaml', '.yml', '.ini', '.log', '.bat', '.ps1', '.sh', '.rtf', '.odt')
        bad = ("\"", "'", "`", "(", ")", "[", "]", "{", "}", "<", ">", ",", ";", ":", "!", "?")
        for raw in text.split():
            t = raw
            ch = True
            while ch and t:
                ch = False
                if t[0] in bad:
                    t = t[1:]
                    ch = True
                if t and t[-1] in bad:
                    t = t[:-1]
                    ch = True
            if not t:
                continue
            if t.lower().endswith(exts):
                return t
        return None

    # ============ ИНСТРУМЕНТЫ ============
    def ask_question(self, question):
        return self.rag.ask(question)

    def check_spelling_file(self, file_path):
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        prompt = SPELLCHECK_PROMPT.format(text=text[:8000])
        return self.registry.generate_with_fallback("default_model", prompt)

    def generate_code_with_validation(self, task):
        self.reset_stop_flag()
        current_prompt = CODE_PROMPT.format(task=task)
        last_code = ""
        start_time = time.time()
        for iteration in range(1, self.max_iterations + 1):
            if self._stop_requested: return "--- ПРЕРВАНО ---\n\n" + last_code
            if time.time() - start_time > self.task_timeout: return "--- ТАЙМАУТ ---\n\n" + last_code
            code = self.registry.generate_with_fallback("code_generation", current_prompt)
            last_code = code
            if code.startswith("[КРИТИЧЕСКАЯ") or code.startswith("[ВНИМАНИЕ:"): return code
            is_valid, error_msg = validate_python_code(code, timeout_sec=self.code_timeout)
            if is_valid:
                if self.critic.enabled and self.critic.force_always:
                    verdict = self.critic.check_general(task, code, "code")
                    print("  [Критик-код] score=" + str(verdict.get("score")))
                    if verdict.get("verdict") != "accept" or verdict.get("score", 0) < self.critic.min_score:
                        current_prompt = "Критик нашёл проблемы: " + str(verdict.get("issues")) + "\nЗадача: " + task + "\nКод:\n" + code
                        continue
                return code
            current_prompt = "Код упал: " + error_msg + "\n\nКод:\n" + code + "\n\nИсправь. Задача: " + task
        return "--- ЛИМИТ ПОПЫТОК ---\n\n" + last_code

    def summarize_file(self, file_path):
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        return self.registry.generate_with_fallback("default_model", SUMMARIZE_PROMPT.format(text=text[:8000]))

    def structure_file(self, file_path):
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        return self.registry.generate_with_fallback("complex_reasoning", STRUCTURE_PROMPT.format(text=text[:8000]))

    def process_long_document(self, file_path):
        err = self._require_allowed(file_path)
        if err: return err
        processor = LongDocumentProcessor(self.config, self.tools, self.registry, self.output_dir)
        return processor.process(file_path)

    def make_file_list(self, folder_path, recursive):
        err = self._require_allowed(folder_path)
        if err: return err
        return generate_file_list(folder_path, recursive, self.output_dir)

    def make_excel_chart(self, file_path):
        err = self._require_allowed(file_path)
        if err: return err
        return create_excel_chart(file_path, self.output_dir)

    def classify_files(self, folder_path):
        err = self._require_allowed(folder_path)
        if err: return err
        folder = Path(folder_path)
        sorted_dir = Path(self.output_dir) / ("sorted_" + folder.name)
        sorted_dir.mkdir(parents=True, exist_ok=True)
        for f in [x for x in folder.iterdir() if x.is_file()]:
            text = extract_text(str(f), self.tools)[:2000]
            prompt = "Определи категорию (Договор, Счет, Отчет, Письмо, Прочее). Текст: " + text
            cat = self.registry.generate_with_fallback("default_model", prompt).strip().split()[0]
            cat = cat.replace(".", "").replace('"', "").replace("'", "")
            (sorted_dir / cat).mkdir(exist_ok=True)
            shutil.copy2(f, sorted_dir / cat / f.name)
        return str(sorted_dir)

    def batch_summarize(self, folder_path):
        err = self._require_allowed(folder_path)
        if err: return err
        folder = Path(folder_path)
        final = ""
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in ['.txt', '.docx', '.pdf']:
                text = self._read_safe(str(f))
                if text.startswith("[Ошибка]"): continue
                s = self.registry.generate_with_fallback("default_model", SUMMARIZE_PROMPT.format(text=text[:6000]))
                final += "=== " + f.name + " ===\n" + s + "\n\n"
        out = Path(self.output_dir) / ("batch_summary_" + folder.name + ".docx")
        create_simple_docx(final, str(out))
        return str(out)

    def web_search(self, query):
        return search_web(query)

    def index_folder(self, folder_path):
        err = self._require_allowed(folder_path)
        if err: return err
        result = self.rag.indexer.index_folder(folder_path)
        self._indexed_folders.add(os.path.abspath(folder_path))
        return result

    def request_stop(self):
        self._stop_requested = True

    def reset_stop_flag(self):
        self._stop_requested = False

    def _read_safe(self, file_path):
        err = self._require_allowed(file_path)
        if err: return err
        safe_path = self.workspace.prepare_file(file_path)
        return extract_text(safe_path, self.tools)