import os
import zipfile
import textwrap

PROJECT_NAME = "agent_router_critic"

FILES = {
    "config.yaml": """\
llm_profiles:
  local_coder:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen-qwen2.5-coder-14b-instruct"
    is_local: true
  local_logic:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "deepseek-r1-0528-qwen3-8b-abliterated"
    is_local: true
  local_fast:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen2.5-7b-instruct-uncensored"
    is_local: true

  manual_bridge:
    type: "manual_bridge"

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
  max_iterations: 10
  task_timeout_seconds: 600
  code_execution_timeout: 15
  max_tokens_default: 4096
  retry_attempts: 2
  retry_delay_seconds: 2

rag:
  db_path: "chroma_db"
  collection_name: "documents"
  chunk_size: 1000
  chunk_overlap: 200
  embedding_model: "paraphrase-multilingual-MiniLM-L12-v2"
  separators: ["\\n\\n", "\\n", ". ", "! ", "? ", " ", ""]

# НОВЫЙ БЛОК: Самопроверка (критик)
self_check:
  enabled: true
  force_always: false       # ТУМБЛЕР: если true — критик запускается для ВСЕХ задач
  max_retries: 2
  min_score: 8
  critic_model: "local_logic"    # Смешанный вариант: критик = R1 (умнее)
  default_model_for_check: "local_fast"  # Для простых задач критик = 7B

# НОВЫЙ БЛОК: Роутер намерений
router:
  use_llm_for_ambiguous: true    # Если true — неоднозначные запросы уточняются через LLM
  dangerous_tools: ["classify_files", "batch_summarize", "index_folder", "make_file_list"]
""",

    # 1. Гибридный роутер
    "core/router.py": """\
import json
from llm.registry import LLMRegistry

KEYWORD_RULES = {
    "generate_code": ["напиши код", "напиши функцию", "напиши скрипт", "сгенерируй код", "python код", "код на питоне", "напиши программу"],
    "check_spelling": ["проверь ошибки", "орфография", "исправь ошибки", "пунктуация", "опечатки"],
    "summarize_file": ["сделай резюме", "краткое содержание", "о чём документ", "о чем документ", "перескажи"],
    "batch_summarize": ["резюме папки", "резюме всех файлов", "резюме всей папки"],
    "classify_files": ["отсортируй файлы", "разложи по папкам", "классифицируй"],
    "make_file_list": ["список файлов", "перечень файлов"],
    "make_excel_chart": ["построй график", "сделай график", "график в excel", "диаграмма"],
    "web_search": ["найди в интернете", "погугли", "поищи в сети", "поиск в интернете"],
    "process_long_doc": ["полный разбор", "разбери книгу", "разбери документ целиком"],
    "index_folder": ["проиндексируй", "индексируй папку"],
    "translate": ["переведи", "перевод на", "translate"],
    "open_style_studio": ["студия стилей", "замени стили", "сопоставь стили", "стили word"],
}

class IntentRouter:
    def __init__(self, registry: LLMRegistry, config: dict):
        self.registry = registry
        self.router_config = config.get("router", {})
        self.dangerous_tools = self.router_config.get("dangerous_tools", [])
        self.use_llm = self.router_config.get("use_llm_for_ambiguous", True)

    def classify(self, user_text: str) -> dict:
        \"\"\"Возвращает {tools: [...], reasoning: str, ambiguous: bool}\"\"\"
        text = user_text.lower()

        # 1. Быстрая проверка по ключевым словам
        matched = []
        for tool, keywords in KEYWORD_RULES.items():
            if any(kw in text for kw in keywords):
                matched.append(tool)

        if matched:
            return {
                "tools": matched,
                "reasoning": f"Совпадение по ключевым словам: {matched}",
                "ambiguous": False
            }

        # 2. Если ничего не нашли — спрашиваем LLM (если включено)
        if self.use_llm:
            return self._classify_with_llm(user_text)

        # 3. По умолчанию — RAG
        return {
            "tools": ["ask_question"],
            "reasoning": "По умолчанию: RAG-поиск по документам",
            "ambiguous": True
        }

    def _classify_with_llm(self, user_text: str) -> dict:
        tools_desc = "\\n".join([f"- {t}: {', '.join(kw[:2])}" for t, kw in KEYWORD_RULES.items()])
        prompt = f\"\"\"Ты — классификатор намерений пользователя в системе документооборота.
Доступные инструменты:
{tools_desc}
- ask_question: вопросы по проиндексированным документам (RAG)

Запрос пользователя: "{user_text}"

Верни ТОЛЬКО валидный JSON без markdown:
{{"tools": ["имя_инструмента"], "reasoning": "кратко почему"}}

Если запрос — вопрос по документам, верни ["ask_question"].
Если хочешь вызвать несколько инструментов — перечисли их в списке.
\"\"\"
        raw = self.registry.generate_with_fallback("default_model", prompt)
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            data["ambiguous"] = False
            return data
        except Exception:
            return {
                "tools": ["ask_question"],
                "reasoning": f"LLM не дал валидный JSON, fallback на RAG. Сырой ответ: {raw[:100]}",
                "ambiguous": True
            }
""",

    # 2. Критик (самопроверка)
    "core/self_check.py": """\
import json
from llm.registry import LLMRegistry

class Critic:
    def __init__(self, registry: LLMRegistry, config: dict):
        self.registry = registry
        cfg = config.get("self_check", {})
        self.enabled = cfg.get("enabled", True)
        self.force_always = cfg.get("force_always", False)
        self.max_retries = cfg.get("max_retries", 2)
        self.min_score = cfg.get("min_score", 8)
        self.critic_model_key = cfg.get("critic_model", "local_logic")
        self.default_critic_key = cfg.get("default_model_for_check", "local_fast")

    def should_check(self, task_type: str) -> bool:
        \"\"\"Определяет, нужна ли проверка для этого типа задачи.\"\"\"
        if not self.enabled:
            return False
        if self.force_always:
            return True
        # По умолчанию проверяем только «смысловые» задачи
        return task_type in ["rag", "summarize", "translate", "structure"]

    def check_general(self, task: str, answer: str, task_type: str) -> dict:
        \"\"\"Универсальная оценка ответа.\"\"\"
        # Для RAG выбираем умную модель, для остального — быструю
        model_key = self.critic_model_key if task_type == "rag" else self.default_critic_key

        prompt = f\"\"\"Ты — строгий критик ответов ИИ.
Задача: {task}
Ответ агента: {answer}

Оцени ответ по трём критериям:
1. Отвечает ли он на задачу? (да/нет)
2. Есть ли галлюцинации / выдуманные факты? (да/нет)
3. Достаточно ли он полон? (да/нет)

Верни ТОЛЬКО JSON без markdown:
{{"score": 1-10, "issues": ["проблема1", "проблема2"], "verdict": "accept" или "retry"}}
\"\"\"
        raw = self.registry.generate_with_fallback(model_key, prompt)
        return self._parse(raw)

    def check_factual(self, context: str, answer: str) -> dict:
        \"\"\"Строгая проверка для RAG: все ли факты подтверждаются контекстом.\"\"\"
        prompt = f\"\"\"Ты — фактчекер. Проверь, все ли утверждения в ответе подтверждаются контекстом.

КОНТЕКСТ:
{context[:6000]}

ОТВЕТ:
{answer}

Верни ТОЛЬКО JSON без markdown:
{{"score": 1-10, "unverified_claims": ["утверждение1"], "verdict": "accept" или "retry"}}
\"\"\"
        raw = self.registry.generate_with_fallback(self.critic_model_key, prompt)
        return self._parse(raw)

    def _parse(self, raw: str) -> dict:
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            data.setdefault("score", 5)
            data.setdefault("verdict", "retry")
            data.setdefault("issues", [])
            return data
        except Exception:
            return {"score": 5, "issues": ["Критик вернул невалидный JSON"], "verdict": "retry"}

    def run_with_retry(self, generate_fn, task: str, task_type: str, context: str = None) -> str:
        \"\"\"Основной цикл: генерирует → проверяет → при провале переделывает.\"\"\"
        if not self.should_check(task_type):
            return generate_fn("")

        best_answer = None
        best_score = 0
        last_issues = []

        for attempt in range(self.max_retries + 1):
            if attempt == 0:
                answer = generate_fn("")
            else:
                feedback = (
                    f"Твой предыдущий ответ был забракован критиком.\\n"
                    f"Проблемы: {last_issues}\\n"
                    f"Предыдущий ответ:\\n{best_answer}\\n\\n"
                    f"Пожалуйста, перепиши, устранив эти проблемы."
                )
                answer = generate_fn(feedback)

            # Выбираем метод проверки
            if task_type == "rag" and context:
                verdict = self.check_factual(context, answer)
            else:
                verdict = self.check_general(task, answer, task_type)

            score = verdict.get("score", 0)
            print(f"  [Критик] Попытка {attempt+1}: score={score}, verdict={verdict.get('verdict')}")

            if score > best_score:
                best_score = score
                best_answer = answer

            if verdict.get("verdict") == "accept" and score >= self.min_score:
                return answer

            last_issues = verdict.get("issues") or verdict.get("unverified_claims") or ["не указаны"]

        print(f"  [Критик] Лимит попыток исчерпан. Возвращаю лучший вариант (score={best_score}).")
        return f"[ВНИМАНИЕ: критик не подтвердил качество, лучший score={best_score}. Замечания: {last_issues}]\\n\\n{best_answer}"
""",

    # 3. Оркестратор в агенте
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
        \"\"\"Роутит запрос, выполняет инструменты, возвращает итог.\"\"\"
        def log(msg):
            print(msg)
            if log_callback: log_callback(msg)

        log(f"[Роутер] Анализирую запрос...")
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
        \"\"\"Выполняет конкретный инструмент с опциональной проверкой критиком.\"\"\"

        if tool_name == "ask_question":
            def gen(feedback):
                base = user_text if not feedback else f"{user_text}\\n\\n{feedback}"
                return self.ask_question(base)
            # Для RAG критик использует factual check — но нам нужен context.
            # Упростим: используем general check для RAG
            return self.critic.run_with_retry(gen, task=user_text, task_type="rag")

        if tool_name == "summarize_file":
            # Извлекаем путь из текста (пользователь мог написать "резюме doc1.txt")
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
            task = user_text
            return self.generate_code_with_validation(task)

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
        \"\"\"Ищет путь в тексте. Простая эвристика по кавычкам и расширениям.\"\"\"
        import re
        # Ищем в кавычках
        quoted = re.findall(r'[\\"\']([^\\"\']+\\.[a-z]{2,4})[\\"\']', text)
        if quoted: return quoted[0]
        # Ищем по расширениям
        paths = re.findall(r'([A-Za-z]:\\\\[^\\s]+|\\S+\\.[a-z]{2,4})', text)
        return paths[0] if paths else None

    # ============ ИНСТРУМЕНТЫ (старые методы, теперь с критиком там, где надо) ============
    def ask_question(self, question: str) -> str:
        return self.rag.ask(question)

    def check_spelling_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        prompt = SPELLCHECK_PROMPT.format(text=text[:8000])
        return self.registry.generate_with_fallback("default_model", prompt)

    def generate_code_with_validation(self, task: str) -> str:
        \"\"\"Код проверяется Python-валидатором. Если self_check.force_always=true — ещё и критиком.\"\"\"
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
                # Дополнительная проверка критиком, если включен force_always
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

    # --- ОСТАЛЬНЫЕ ИНСТРУМЕНТЫ (без изменений) ---
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
""",

    # 4. Обновленный GUI (тумблер + маршрутизация)
    "gui/app.py": """\
import customtkinter as ctk
import threading
import os
from tkinter import filedialog, messagebox
from core.agent import Agent
from gui.config_manager import add_llm_profile, load_config, save_config
from gui.tooltip import ToolTip
from gui.style_manager import StyleManagerWindow

class AgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI Document Agent PRO")
        self.geometry("1200x800")
        self.agent = Agent("config.yaml")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkScrollableFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="AGENT PANEL", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.pack(padx=20, pady=(20, 10))

        # --- ТУМБЛЕРЫ ПРОВЕРКИ ---
        ctk.CTkLabel(self.sidebar, text="Проверка ответов:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(10, 0), anchor="w", padx=20)

        cfg = load_config()
        self.var_enabled = ctk.BooleanVar(value=cfg.get("self_check", {}).get("enabled", True))
        self.var_force = ctk.BooleanVar(value=cfg.get("self_check", {}).get("force_always", False))

        chk_enabled = ctk.CTkCheckBox(self.sidebar, text="Включить критика", variable=self.var_enabled, command=self._on_critic_toggle)
        chk_enabled.pack(padx=20, pady=5, anchor="w")
        ToolTip(chk_enabled, "Главный выключатель: включена ли проверка ответов ИИ.")

        chk_force = ctk.CTkCheckBox(self.sidebar, text="Всегда (даже для кода)", variable=self.var_force, command=self._on_critic_toggle)
        chk_force.pack(padx=20, pady=5, anchor="w")
        ToolTip(chk_force, "Проверять даже те задачи, где обычно хватает Python-валидатора. Медленнее, но строже.")

        # --- КНОПКИ ---
        ctk.CTkLabel(self.sidebar, text="Базовые функции:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Индексировать папку", self.index_folder, "Прочитать файлы для RAG")
        self._add_btn("Проверить орфографию", self.check_spell, "Найти ошибки")
        self._add_btn("Написать код", self.write_code, "Сгенерировать Python-код")
        self._add_btn("Полный разбор документа", self.process_long_doc, "Резюме больших книг", color="#8A2BE2")

        ctk.CTkLabel(self.sidebar, text="Word Студия:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Студия стилей Word", self.open_style_studio, "Замена стилей, нумерация", color="#B8860B")

        ctk.CTkLabel(self.sidebar, text="Данные:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Список файлов (CSV)", self.make_file_list_ui, "Создать CSV со списком")
        self._add_btn("График в Excel", self.make_excel_chart_ui, "Построить график")
        self._add_btn("Пакетное резюме", self.batch_summary_ui, "Резюме папки в Word")
        self._add_btn("Сортировка файлов", self.classify_ui, "Разложить по категориям")
        self._add_btn("Веб-поиск", self.web_search_ui, "Поиск в интернете")

        ctk.CTkLabel(self.sidebar, text="Настройки:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Добавить LLM (API)", self.open_add_llm_window, "Подключить API", color="green")

        self.btn_stop = ctk.CTkButton(self, text="ЭКСТРЕННЫЙ СТОП", fg_color="red", hover_color="darkred", command=self.stop_agent)
        self.btn_stop.grid(row=0, column=0, sticky="sw", padx=20, pady=20)

        # --- ЧАТ ---
        self.chat_frame = ctk.CTkFrame(self)
        self.chat_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.chat_frame.grid_rowconfigure(0, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(self.chat_frame, state="disabled", wrap="word", font=("Consolas", 14))
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        self.input_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.user_input = ctk.CTkEntry(self.input_frame, placeholder_text="Спросите или дайте команду (например, 'сделай резюме D:/file.txt')")
        self.user_input.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.user_input.bind("<Return>", lambda e: self.send_message())

        self.btn_send = ctk.CTkButton(self.input_frame, text="Отправить", width=100, command=self.send_message)
        self.btn_send.grid(row=0, column=1)

    def _on_critic_toggle(self):
        cfg = load_config()
        if "self_check" not in cfg: cfg["self_check"] = {}
        cfg["self_check"]["enabled"] = self.var_enabled.get()
        cfg["self_check"]["force_always"] = self.var_force.get()
        save_config(cfg)
        # Применяем на лету (без перезапуска)
        self.agent.critic.enabled = self.var_enabled.get()
        self.agent.critic.force_always = self.var_force.get()
        self.log(f"[Настройки] Критик: {'ВКЛ' if self.var_enabled.get() else 'ВЫКЛ'}, force_always={self.var_force.get()}")

    def _add_btn(self, text, command, hint, color=None):
        btn = ctk.CTkButton(self.sidebar, text=text, command=command)
        if color: btn.configure(fg_color=color, hover_color="darkgreen" if color=="green" else "#4B0082")
        btn.pack(padx=20, pady=5, fill="x")
        ToolTip(btn, hint)

    def log(self, text):
        def _update():
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", text + "\\n")
            self.chat_display.see("end")
            self.chat_display.configure(state="disabled")
        self.after(0, _update)

    def run_in_thread(self, func, *args):
        def wrapper():
            try: func(*args)
            except Exception as e: self.log(f"\\n[ОШИБКА]: {str(e)}\\n")
        threading.Thread(target=wrapper, daemon=True).start()

    # --- ОТПРАВКА ЧЕРЕЗ РОУТЕР ---
    def send_message(self):
        text = self.user_input.get()
        if not text.strip(): return
        self.user_input.delete(0, "end")
        self.log(f"\\nВы: {text}")

        # Опасные действия — подтверждение
        routing_preview = self.agent.router.classify(text)
        dangerous_hit = [t for t in routing_preview["tools"] if t in self.agent.router.dangerous_tools]
        if dangerous_hit:
            ok = messagebox.askyesno("Подтверждение", f"Агент хочет выполнить: {dangerous_hit}. Это может создать/изменить файлы. Разрешить?")
            if not ok:
                self.log("[Отменено пользователем]")
                return

        def task():
            result = self.agent.run_task(text, log_callback=self.log)
            self.log(f"\\nАгент: {result}")
        threading.Thread(target=task, daemon=True).start()

    # --- КНОПКИ (остались как были) ---
    def open_style_studio(self): StyleManagerWindow(self, self.agent)
    def index_folder(self):
        f = filedialog.askdirectory()
        if f: self.run_in_thread(lambda: self.log("[ИНДЕКСАЦИЯ] " + str(self.agent.index_folder(f))))
    def check_spell(self):
        f = filedialog.askopenfilename()
        if f: self.run_in_thread(lambda: self.log(f"РЕЗУЛЬТАТ:\\n{self.agent.check_spelling_file(f)}"))
    def write_code(self):
        t = ctk.CTkInputDialog(text="Задача:", title="Код").get_input()
        if t: self.run_in_thread(lambda: self.log(self.agent.generate_code_with_validation(t)))
    def process_long_doc(self):
        f = filedialog.askopenfilename()
        if f: self.run_in_thread(lambda: self.log(self.agent.process_long_document(f)))
    def make_file_list_ui(self):
        f = filedialog.askdirectory()
        if not f: return
        r = messagebox.askyesno("Вложенность", "Включать подпапки?")
        self.run_in_thread(lambda: self.log(f"[СПИСОК]: {self.agent.make_file_list(f, r)}"))
    def make_excel_chart_ui(self):
        f = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls")])
        if f: self.run_in_thread(lambda: self.log(f"[ГРАФИК]: {self.agent.make_excel_chart(f)}"))
    def batch_summary_ui(self):
        f = filedialog.askdirectory()
        if f: self.run_in_thread(lambda: self.log(f"[РЕЗЮМЕ]: {self.agent.batch_summarize(f)}"))
    def classify_ui(self):
        f = filedialog.askdirectory()
        if f: self.run_in_thread(lambda: self.log(f"[СОРТИРОВКА]: {self.agent.classify_files(f)}"))
    def web_search_ui(self):
        q = ctk.CTkInputDialog(text="Запрос:", title="Поиск").get_input()
        if q: self.run_in_thread(lambda: self.log(self.agent.web_search(q)))
    def stop_agent(self):
        self.agent.request_stop()
        self.log("\\n[СИСТЕМА] Стоп!")

    def open_add_llm_window(self):
        win = ctk.CTkToplevel(self); win.title("Добавить LLM"); win.geometry("450x400"); win.attributes("-topmost", True)
        ctk.CTkLabel(win, text="Название профиля:").pack(pady=(10,0)); e1 = ctk.CTkEntry(win, width=350); e1.pack()
        ctk.CTkLabel(win, text="Base URL:").pack(pady=(10,0)); e2 = ctk.CTkEntry(win, width=350); e2.pack()
        ctk.CTkLabel(win, text="API Key:").pack(pady=(10,0)); e3 = ctk.CTkEntry(win, width=350, show="*"); e3.pack()
        ctk.CTkLabel(win, text="Имя модели:").pack(pady=(10,0)); e4 = ctk.CTkEntry(win, width=350); e4.pack()
        v = ctk.BooleanVar(value=False); ctk.CTkCheckBox(win, text="Локальная?", variable=v).pack(pady=10)
        def save():
            n, u, k, m = e1.get(), e2.get(), e3.get(), e4.get()
            if not n or not u or not m: messagebox.showerror("Ошибка", "Заполните поля!"); return
            add_llm_profile(n, u, k, m, v.get())
            messagebox.showinfo("Успех", f"Модель {n} добавлена!"); win.destroy()
        ctk.CTkButton(win, text="Сохранить", command=save).pack(pady=20)
"""
}


def create_project():
    print(f"Создание Router+Critic {PROJECT_NAME}...")
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