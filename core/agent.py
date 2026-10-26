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
        self.pending_tool = None   # инструмент, ожидающий аргумент (папка/файл)
        self.chat_history = []     # [{'role': 'user'/'assistant', 'content': '...'}, ...]
        self.max_history = 5       # сколько последних пар хранить
        self.last_folder = None    # папка последнего ask_about_folder

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
        self.last_folder = folder   # запоминаем для контекста следующих вопросов
        if abs_folder not in self._indexed_folders:
            print("[Auto-Index] Индексирую папку: " + folder)
            self.rag.indexer.index_folder(folder)
            self._indexed_folders.add(abs_folder)

        # === Получаем список файлов для явного перечисления ===
        file_list_text = ""
        lower_text = user_text.lower()
        wants_file_list = any(kw in lower_text for kw in [
            "что в папке", "что находится", "список файлов", "какие файлы",
            "покажи файлы", "перечень", "содержимое папки", "обзор папки"
        ])
        if wants_file_list:
            try:
                from pathlib import Path as _P
                all_files = [f for f in _P(folder).rglob('*') if f.is_file()]
                if all_files:
                    file_list_text = "Файлы в папке " + folder + ":\n"
                    for f in all_files[:30]:
                        file_list_text += "- " + f.name + "\n"
                    if len(all_files) > 30:
                        file_list_text += "... и ещё " + str(len(all_files) - 30) + " файлов\n"
            except Exception as e:
                file_list_text = "[Не удалось получить список: " + str(e) + "]\n"

        question = user_text.replace(folder, "").strip()
        generic = ["расскажи", "кратко", "обзор", "покажи", "о папке", "про папку", "что в", "что находится", "проанализируй", "опиши", "дай обзор", "перескажи", "папке", "папки", "папку", "каталоге", "каталог", "содержимое", "содержимом"]
        specific = question
        for gw in generic:
            specific = specific.replace(gw, " ")
        specific = specific.strip(" ?!.,;:\t\n")

        # Если специфичного вопроса нет - только файлы + общий обзор
        if len(specific) < 5:
            if file_list_text:
                question = "Сделай краткий обзор содержимого этих документов: какие темы, ключевые факты и вопросы они освещают?"
                rag_answer = self.ask_question(question, folder_filter=folder)
                return file_list_text + "\n--- Обзор содержимого ---\n" + rag_answer
            else:
                question = "Сделай краткий обзор содержимого этих документов. Какие темы/вопросы они освещают?"
        else:
            question = specific

        # Если есть специфичный вопрос - RAG-ответ + (опционально) список файлов сверху
        rag_answer = self.ask_question(question)
        if file_list_text:
            return file_list_text + "\n--- Ответ на вопрос ---\n" + rag_answer
        return rag_answer

    # ============ ГЛАВНЫЙ ОРКЕСТРАТОР ============
    def run_task(self, user_text, log_callback=None):
        def log(msg):
            print(msg)
            if log_callback:
                log_callback(msg)

        # === Проверка: может быть, это ответ на 'Укажите папку/файл'? ===
        if self.pending_tool:
            resolved = self._try_resolve_pending(user_text, log)
            if resolved is not None:
                self._append_history(user_text, str(resolved))
                return resolved

        log("[Роутер] Анализирую запрос...")
        routing = self.router.classify(user_text)
        tools = routing.get("tools", ["ask_question"])
        log("[Роутер] -> " + str(tools) + " (" + routing.get("reasoning", "") + ")")

        start_time = time.time()
        results = []
        for tool_name in tools:
            elapsed = time.time() - start_time
            if elapsed > self.task_timeout:
                msg = "Истекло время (" + str(int(self.task_timeout)) + " сек)"
                log("[Таймаут] " + msg + " - прерываю")
                results.append("=== ТАЙМАУТ ===\n" + msg)
                break
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
            return self.ask_question_with_critic(user_text)

        if tool_name == "summarize_file":
            fp = self._extract_path_from_text(user_text)
            if not fp:
                self.pending_tool = 'summarize_file'
                return "Укажите файл. Напишите путь следующим сообщением."
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
                self.pending_tool = 'check_spelling'
                return "Укажите файл. Напишите путь следующим сообщением."
            return self.check_spelling_file(fp)

        if tool_name == "generate_code":
            return self.generate_code_with_validation(user_text)

        if tool_name == "batch_summarize":
            f = self._extract_folder_from_text(user_text) or self._extract_path_from_text(user_text)
            if not f:
                self.pending_tool = 'batch_summarize'
                return "Укажите папку. Напишите путь следующим сообщением (например: D:/Docs) или повторите команду с путём."
            return self.batch_summarize(f)

        if tool_name == "classify_files":
            f = self._extract_folder_from_text(user_text)
            if not f:
                self.pending_tool = 'classify_files'
                return "Укажите папку. Напишите путь следующим сообщением."
            return self.classify_files(f)

        if tool_name == "make_file_list":
            f = self._extract_folder_from_text(user_text)
            if not f:
                self.pending_tool = 'make_file_list'
                return "Укажите папку. Напишите путь следующим сообщением."
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
    def ask_question_with_critic(self, question, folder_filter=None):
        # Особый путь для RAG: сначала получаем чанки, потом критик проверяет по ним
        search_query = self.rag._build_search_query(question, self.chat_history)
        where = self.rag._get_source_filter(folder_filter)
        chunks = self.rag.indexer.search(search_query, top_k=12, where=where)
        if not chunks:
            return 'В базе данных не найдено информации по этому вопросу.'
        # Собираем контекст для критика
        from pathlib import Path as _P
        context_for_critic = ''
        for c in chunks:
            context_for_critic += c['text'] + '\n\n'
        # Генерируем ответ через RAG
        def gen(feedback):
            q = question if not feedback else (question + '\n\n' + feedback)
            return self.rag.ask(q, history=self.chat_history, last_folder=self.last_folder, folder_filter=folder_filter)
        return self.critic.run_with_retry(gen, task=question, task_type='rag', context=context_for_critic)

    def ask_question(self, question, folder_filter=None):
        return self.rag.ask(question, history=self.chat_history, last_folder=self.last_folder, folder_filter=folder_filter)

    def _append_history(self, user, assistant):
        self.chat_history.append({'role': 'user', 'content': str(user)})
        self.chat_history.append({'role': 'assistant', 'content': str(assistant)})
        # Обрезаем по парам
        max_len = self.max_history * 2
        if len(self.chat_history) > max_len:
            self.chat_history = self.chat_history[-max_len:]

    def _try_resolve_pending(self, user_text, log):
        tool = self.pending_tool
        arg = user_text.strip().strip('"').strip("'")

        # Если в тексте есть команда (а не только путь) — отдаём роутеру
        lower = user_text.lower()
        command_words = ['проверь', 'сделай', 'напиши', 'построй', 'найди', 'создай', 'посчитай', 'переведи', 'отсортируй', 'разложи']
        if any(w in lower for w in command_words):
            self.pending_tool = None
            return None

        self.pending_tool = None
        log('[Диалог] Использую введённый путь: ' + arg)

        try:
            if tool == 'make_file_list':
                return self.make_file_list(arg, recursive=True)
            if tool == 'classify_files':
                return self.classify_files(arg)
            if tool == 'batch_summarize':
                return self.batch_summarize(arg)
            if tool == 'index_folder':
                return self.index_folder(arg)
            if tool == 'make_excel_chart':
                return self.make_excel_chart(arg)
            if tool == 'summarize_file':
                return self.summarize_file(arg)
            if tool == 'check_spelling':
                return self.check_spelling_file(arg)
            if tool == 'process_long_doc':
                return self.process_long_document(arg)
            if tool == 'ask_about_folder':
                return self.ask_about_folder('что в папке ' + arg + '?')
        except Exception as e:
            return '[Ошибка] ' + str(e)
        return None

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

    def reset_rag_db(self):
        try:
            import shutil
            db_path = self.config.get('rag', {}).get('db_path', 'chroma_db')
            if os.path.exists(db_path):
                shutil.rmtree(db_path)
                print('[RAG] База данных удалена: ' + db_path)
            self._rag = None
            self._indexed_folders.clear()
            return 'База RAG очищена. Проиндексируйте папку заново.'
        except Exception as e:
            return '[Ошибка очистки]: ' + str(e)

    def set_task_timeout(self, seconds):
        try:
            self.task_timeout = int(seconds)
        except (ValueError, TypeError):
            return 'Ошибка: введите целое число секунд'
        if self.task_timeout < 30:
            self.task_timeout = 30
        if 'agent_loop' not in self.config:
            self.config['agent_loop'] = {}
        self.config['agent_loop']['task_timeout_seconds'] = self.task_timeout
        try:
            with open('config.yaml', 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            return 'Ошибка сохранения: ' + str(e)
        return 'Лимит времени: ' + str(self.task_timeout) + ' сек'

    def request_stop(self):
        self._stop_requested = True

    def reset_stop_flag(self):
        self._stop_requested = False

    def _read_safe(self, file_path):
        err = self._require_allowed(file_path)
        if err: return err
        safe_path = self.workspace.prepare_file(file_path)
        return extract_text(safe_path, self.tools)