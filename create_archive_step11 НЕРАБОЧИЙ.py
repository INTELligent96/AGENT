import os
import zipfile
import textwrap

PROJECT_NAME = "agent_final_pack"

FILES = {
    # ═══════════════════════════════════════════════════════════
    # 1. ИСПРАВЛЕННЫЙ AGENT.PY (без ошибки экранирования)
    # ═══════════════════════════════════════════════════════════
    "core/agent.py": """\
import os
import time
import yaml
import shutil
import re
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
                if text.startswith("[Ошибка]"): return text
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
            return "[Откройте вкладку 'Студия стилей Word' в левой панели]"

        return f"[Неизвестный инструмент: {tool_name}]"

    # ═══════════════════════════════════════════════════════════
    # ИСПРАВЛЕННЫЙ метод извлечения пути (без бага экранирования)
    # ═══════════════════════════════════════════════════════════
    def _extract_path_from_text(self, text: str) -> str:
        \"\"\"Ищет существующий файл или папку в тексте пользователя.\"\"\"
        # 1. Сначала ищем в кавычках (могут содержать пробелы)
        quoted = re.findall(r'''["'«»]([^"'«»]+)["'«»]''', text)
        for q in quoted:
            if os.path.exists(q):
                return q
        # 2. Ищем любой токен, который существует на диске
        for token in re.findall(r'\\S+', text):
            clean = token.strip('"\\'«».,;:()[]')
            if clean and os.path.exists(clean):
                return clean
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
""",

    # ═══════════════════════════════════════════════════════════
    # 2. Исправленный web_search (совместимость с ddgs и duckduckgo_search)
    # ═══════════════════════════════════════════════════════════
    "tools/web_search.py": """\
def search_web(query: str, max_results: int = 3) -> str:
    \"\"\"Ищет информацию в интернете. Работает с ddgs или duckduckgo_search.\"\"\"
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        return "[Ошибка] Не установлена библиотека поиска. Выполните: pip install ddgs"

    try:
        results = DDGS().text(query, max_results=max_results)
        if not results:
            return "Ничего не найдено в интернете."
        output = ""
        for r in results:
            output += f"Источник: {r.get('title', '')}\\nСсылка: {r.get('href', '')}\\nТекст: {r.get('body', '')}\\n\\n"
        return output
    except Exception as e:
        return f"Ошибка поиска: {e}"
""",

    # ═══════════════════════════════════════════════════════════
    # 3. МЕГА-ТЕСТ ВСЕХ ФУНКЦИЙ
    # ═══════════════════════════════════════════════════════════
    "test_all_features_v2.py": """\
import os
import shutil
import time
from pathlib import Path

PASS = "✅ PASS"
FAIL = "❌ FAIL"
SKIP = "⏭️ SKIP"

results = []

def report(name, status, info=""):
    results.append((name, status, info))
    print(f"  {status}  {name}  {info}")

def section(title):
    print(f"\\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def setup_env():
    test_dir = Path("TEST_ENV_V2")
    if test_dir.exists(): shutil.rmtree(test_dir)
    test_dir.mkdir()
    (test_dir / "doc1.txt").write_text("Компания Ромашка основана в 2001 году в Казани.", encoding="utf-8")
    (test_dir / "bad.txt").write_text("Привет как дила? Вчира харашо погуляли.", encoding="utf-8")
    (test_dir / "doc2.docx").write_text("dummy") if False else None
    # Word через python-docx
    from documents.writers import create_simple_docx
    create_simple_docx("Договор аренды. Сумма 50000 руб.", str(test_dir / "doc2.docx"))
    # Excel с данными
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Месяц", "Значение"])
    for m, v in [("Янв", 10), ("Фев", 20), ("Мар", 30)]:
        ws.append([m, v])
    wb.save(test_dir / "data.xlsx")
    # Большой текст для чекпоинтов
    big = " ".join(["Проверка длинного документа."] * 50)
    (test_dir / "big.txt").write_text(big, encoding="utf-8")
    return test_dir

def main():
    print("╔" + "═"*58 + "╗")
    print("║  ПОЛНЫЙ ТЕСТ АГЕНТА v2                                   ║")
    print("╚" + "═"*58 + "╝")
    print("\\n⚠️  Убедитесь, что LM Studio запущен и модели загружены!\\n")

    t0 = time.time()
    test_dir = setup_env()
    print(f"Тестовая папка: {test_dir.absolute()}")

    # ============ ТЕСТ 0: Импорты ============
    section("ТЕСТ 0: Импорт модулей")
    try:
        from core.agent import Agent
        from core.router import IntentRouter
        from core.self_check import Critic
        from documents.style_engine import WordStyleEngine
        report("Импорт всех модулей", PASS)
    except Exception as e:
        report("Импорт всех модулей", FAIL, str(e))
        print("\\n❌ КРИТИЧЕСКАЯ ОШИБКА ИМПОРТА. Дальше тестировать нет смысла.")
        return

    agent = Agent("config.yaml")

    # ============ ТЕСТ 1: Роутер ============
    section("ТЕСТ 1: Роутер намерений")
    test_cases = [
        ("напиши функцию сложения", "generate_code"),
        ("проверь ошибки в файле bad.txt", "check_spelling"),
        ("сделай резюме " + str(test_dir / "doc1.txt"), "summarize_file"),
        ("построй график " + str(test_dir / "data.xlsx"), "make_excel_chart"),
        ("отсортируй файлы в " + str(test_dir), "classify_files"),
        ("найди в интернете кто такой Пушкин", "web_search"),
    ]
    for query, expected in test_cases:
        try:
            result = agent.router.classify(query)
            tools = result.get("tools", [])
            if expected in tools:
                report(f"Роутер: '{query[:40]}...'", PASS, f"→ {tools}")
            else:
                report(f"Роутер: '{query[:40]}...'", FAIL, f"ожидали {expected}, получили {tools}")
        except Exception as e:
            report(f"Роутер: '{query[:40]}...'", FAIL, str(e))

    # ============ ТЕСТ 2: Критик ============
    section("ТЕСТ 2: Критик (конфигурация)")
    try:
        assert agent.critic.enabled in [True, False]
        assert agent.critic.force_always in [True, False]
        report("Критик инициализирован", PASS, f"enabled={agent.critic.enabled}, force={agent.critic.force_always}")

        if agent.critic.should_check("code"):
            report("Критик: код (force=false)", FAIL, "не должен проверять код при force_always=false")
        else:
            report("Критик: код (force=false)", PASS, "корректно пропускает")

        if agent.critic.should_check("rag"):
            report("Критик: RAG", PASS, "будет проверять")
        else:
            report("Критик: RAG", FAIL, "должен проверять RAG")
    except Exception as e:
        report("Критик", FAIL, str(e))

    # ============ ТЕСТ 3: Workspace (безопасность) ============
    section("ТЕСТ 3: Безопасность исходников")
    try:
        orig = test_dir / "original.txt"
        orig.write_text("Не трогать!", encoding="utf-8")
        safe = agent.workspace.prepare_file(str(orig))
        if "workspace" in safe and os.path.exists(safe):
            report("Workspace: копия создана", PASS, safe)
        else:
            report("Workspace: копия создана", FAIL, safe)
        if orig.read_text(encoding="utf-8") == "Не трогать!":
            report("Workspace: оригинал цел", PASS)
        else:
            report("Workspace: оригинал цел", FAIL)
    except Exception as e:
        report("Workspace", FAIL, str(e))

    # ============ ТЕСТ 4: Извлечение пути ============
    section("ТЕСТ 4: Извлечение пути из текста")
    try:
        test_path = str(test_dir / "doc1.txt")
        extracted = agent._extract_path_from_text(f"сделай резюме {test_path}")
        if extracted and os.path.exists(extracted):
            report("Извлечение пути", PASS, extracted)
        else:
            report("Извлечение пути", FAIL, f"получили: {extracted}")

        quoted = agent._extract_path_from_text(f"резюме файла '{test_path}'")
        if quoted and os.path.exists(quoted):
            report("Извлечение пути (в кавычках)", PASS, quoted)
        else:
            report("Извлечение пути (в кавычках)", FAIL, f"получили: {quoted}")
    except Exception as e:
        report("Извлечение пути", FAIL, str(e))

    # ============ ТЕСТ 5: Простые инструменты (без LLM) ============
    section("ТЕСТ 5: Инструменты без LLM")

    try:
        csv = agent.make_file_list(str(test_dir), recursive=True)
        if os.path.exists(csv):
            report("Список файлов CSV", PASS, csv)
        else:
            report("Список файлов CSV", FAIL, csv)
    except Exception as e:
        report("Список файлов CSV", FAIL, str(e))

    try:
        chart = agent.make_excel_chart(str(test_dir / "data.xlsx"))
        if os.path.exists(chart):
            report("Excel график", PASS, chart)
        else:
            report("Excel график", FAIL, chart)
    except Exception as e:
        report("Excel график", FAIL, str(e))

    # ============ ТЕСТ 6: Орфография (LLM) ============
    section("ТЕСТ 6: Орфография (LLM)")
    try:
        res = agent.check_spelling_file(str(test_dir / "bad.txt"))
        if "Ошибка" not in res[:50] and len(res) > 5:
            report("Проверка орфографии", PASS, res[:80])
        else:
            report("Проверка орфографии", FAIL, res[:100])
    except Exception as e:
        report("Проверка орфографии", FAIL, str(e))

    # ============ ТЕСТ 7: Генерация кода (LLM + валидатор) ============
    section("ТЕСТ 7: Генерация кода")
    try:
        code = agent.generate_code_with_validation("Напиши функцию умножения двух чисел")
        if "def " in code and "return" in code:
            report("Генерация кода", PASS, f"получено {len(code)} символов")
        else:
            report("Генерация кода", FAIL, code[:100])
    except Exception as e:
        report("Генерация кода", FAIL, str(e))

    # ============ ТЕСТ 8: RAG ============
    section("ТЕСТ 8: RAG (индексация + вопрос)")
    try:
        n = agent.index_folder(str(test_dir))
        report("Индексация", PASS, f"файлов: {n}")
        answer = agent.ask_question("В каком году основана компания Ромашка?")
        if "2001" in answer:
            report("RAG ответ", PASS, answer[:80])
        else:
            report("RAG ответ", FAIL, f"ожидали '2001', получили: {answer[:150]}")
    except Exception as e:
        report("RAG", FAIL, str(e))

    # ============ ТЕСТ 9: Чекпоинты (Long Document) ============
    section("ТЕСТ 9: Длинный документ (чекпоинты)")
    try:
        res = agent.process_long_document(str(test_dir / "big.txt"))
        cp_dir = Path("output/checkpoints/big")
        if cp_dir.exists() and len(list(cp_dir.glob("part_*.txt"))) > 0:
            report("Чекпоинты созданы", PASS, f"частей: {len(list(cp_dir.glob('part_*.txt')))}")
        else:
            report("Чекпоинты созданы", FAIL, res)
        final_file = Path("output/checkpoints/FINAL_big.txt")
        if final_file.exists():
            report("Финальное резюме", PASS)
        else:
            report("Финальное резюме", FAIL)
    except Exception as e:
        report("Длинный документ", FAIL, str(e))

    # ============ ТЕСТ 10: Word Студия ============
    section("ТЕСТ 10: Word Студия Стилей")
    try:
        from documents.style_engine import WordStyleEngine
        # Используем doc2.docx как шаблон и как документ для простоты
        engine = WordStyleEngine(str(test_dir / "doc2.docx"))
        styles = engine.get_document_styles(str(test_dir / "doc2.docx"))
        report("Стили документа извлечены", PASS, f"найдено: {len(styles)}")

        out = engine.apply_mapping(str(test_dir / "doc2.docx"), {}, "test_empty_mapping.docx")
        if os.path.exists(out):
            report("Применение стилей (пустой маппинг)", PASS, out)
        else:
            report("Применение стилей", FAIL)

        cap_out = engine.add_captions(str(test_dir / "doc2.docx"), "test_captioned.docx")
        if os.path.exists(cap_out):
            report("Добавление подписей", PASS, cap_out)
        else:
            report("Добавление подписей", FAIL)
    except Exception as e:
        report("Word Студия", FAIL, str(e))

    # ============ ТЕСТ 11: Веб-поиск ============
    section("ТЕСТ 11: Веб-поиск")
    try:
        res = agent.web_search("Python programming language")
        if "http" in res.lower() or "ничего не найдено" in res.lower():
            report("Веб-поиск", PASS, res[:80])
        else:
            report("Веб-поиск", FAIL, res[:100])
    except Exception as e:
        report("Веб-поиск", FAIL, str(e))

    # ============ ТЕСТ 12: End-to-end через run_task ============
    section("ТЕСТ 12: End-to-end (чат → роутер → инструмент)")
    try:
        result = agent.run_task(f"проверь ошибки в {test_dir / 'bad.txt'}")
        if len(result) > 10 and not result.startswith("[Неизвестный"):
            report("End-to-end (орфография)", PASS, result[:80])
        else:
            report("End-to-end (орфография)", FAIL, result[:100])
    except Exception as e:
        report("End-to-end", FAIL, str(e))

    # ═══════════ ИТОГИ ═══════════
    section("ИТОГИ")
    passed = sum(1 for _, s, _ in results if s == PASS)
    failed = sum(1 for _, s, _ in results if s == FAIL)
    total = len(results)
    duration = time.time() - t0

    print(f"\\nВсего тестов: {total}")
    print(f"  {PASS}: {passed}")
    print(f"  {FAIL}: {failed}")
    print(f"Время: {duration:.1f} сек")

    if failed > 0:
        print(f"\\n⚠️ Проваленные тесты:")
        for name, status, info in results:
            if status == FAIL:
                print(f"  • {name}: {info}")
    else:
        print(f"\\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")

if __name__ == "__main__":
    main()
""",

    # ═══════════════════════════════════════════════════════════
    # 4. ИНСТРУКЦИЯ (README)
    # ═══════════════════════════════════════════════════════════
    "README.md": """\
# 🤖 AI Document Agent — Руководство пользователя

Полноценный локальный ИИ-ассистент для работы с документами Word, Excel, PDF, картинками.
Работает офлайн через LM Studio, умеет подключаться к внешним API (DeepSeek, Qwen и др.).

---

## 📋 Содержание
1. [Что умеет агент](#что-умеет-агент)
2. [Установка](#установка)
3. [Настройка config.yaml](#настройка-configyaml)
4. [Работа через кнопки (левая панель)](#работа-через-кнопки)
5. [Работа через чат (авто-роутер)](#работа-через-чат)
6. [Критик (самопроверка)](#критик)
7. [Подключение внешних API](#подключение-внешних-api)
8. [Word Студия Стилей](#word-студия-стилей)
9. [Файловая структура](#файловая-структура)
10. [Решение проблем](#решение-проблем)

---

## 🎯 Что умеет агент

| Функция | Описание |
|---|---|
| **RAG** | Отвечает на вопросы по твоим документам (с цитатами и ссылками) |
| **Орфография** | Находит и исправляет ошибки в RU/EN текстах |
| **Генерация кода** | Пишет Python-код и проверяет его через интерпретатор |
| **Длинные документы** | Резюмирует книги по частям с чекпоинтами (можно прервать и продолжить) |
| **Резюме папок** | Делает резюме всех файлов в папке → собирает в один Word |
| **Сортировка** | Раскладывает файлы по категориям (Договор, Счет, Отчет...) |
| **OCR** | Читает текст с картинок и сканов PDF (Tesseract) |
| **Excel графики** | Строит графики по данным из таблиц |
| **Word Студия** | Заменяет стили, нумерует таблицы/рисунки по твоему шаблону |
| **Веб-поиск** | Ищет в интернете через DuckDuckGo |
| **Роутер** | Понимает команды из чата и сам выбирает нужный инструмент |
| **Критик** | Проверяет ответы ИИ и заставляет переделывать плохие |

---

## 💾 Установка

### 1. Python и библиотеки
Нужен **Python 3.10+**. Установи зависимости:
```bash
pip install python-docx openpyxl PyMuPDF pytesseract Pillow docxtpl xlrd pandas pywin32 customtkinter chromadb sentence-transformers xlsxwriter ddgs lxml
2. Tesseract OCR (для картинок и сканов)
Скачай: https://github.com/UB-Mannheim/tesseract/wiki

Важно: при установке отметь язык Russian и English.

После установки пропиши путь в config.yaml (строка tesseract_path).

3. Microsoft Office или LibreOffice
Нужен для конвертации старых .doc/.xls.

Если стоит Office — укажи use_ms_office: true в конфиге.

Если LibreOffice — скачай и пропиши путь к soffice.exe.

4. LM Studio
Скачай: https://lmstudio.ai/

Загрузи модели (например: Qwen 2.5 Coder 14B, DeepSeek R1 8B, Qwen 2.5 7B).

Запусти Local Server (по умолчанию порт 1234, но у тебя 1235 — проверь!).

Context Length: для R1 поставь минимум 4096, иначе модель будет падать с 500.

⚙️ Настройка config.yaml
Основные блоки
yaml
llm_profiles:
  local_fast:        # Имя профиля (любое)
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen2.5-7b-instruct-uncensored"   # ТОЧНОЕ имя из LM Studio
    is_local: true

routing:
  default_model: "local_fast"           # Куда идут простые задачи
  code_generation: "local_coder"        # Куда идёт код
  complex_reasoning: "local_logic"      # Куда идут сложные рассуждения

agent_loop:
  max_iterations: 10                    # Сколько раз пробовать исправить код
  task_timeout_seconds: 600             # Максимум на одну задачу (10 мин)
  max_tokens_default: 4096              # Лимит токенов для ответа

self_check:
  enabled: true                         # Включен ли критик
  force_always: false                   # Проверять ли даже код (true = строго)
  max_retries: 2                        # Сколько раз критик может отправить на переделку
  min_score: 8                          # Минимальная оценка (из 10)
  critic_model: "local_logic"           # Какая модель проверяет RAG
  default_model_for_check: "local_fast" # Какая модель проверяет остальное

router:
  use_llm_for_ambiguous: true           # Непонятные запросы уточнять через LLM
  dangerous_tools:                      # Какие действия требуют подтверждения
    - "classify_files"
    - "batch_summarize"
    - "index_folder"
Как узнать точное имя модели в LM Studio
Открой LM Studio → вкладка Local Server.

Нажми Select a model для каждой модели.

Скопируй ID (не название в библиотеке!). Обычно оно выглядит как qwen2.5-7b-instruct (без .gguf и без папок).

🎛 Работа через кнопки (левая панель)
Чекбоксы сверху
"Включить критика" — главный выключатель проверки. Сними галочку → агент работает быстрее, но менее строго.

"Всегда (даже для кода)" — критик проверяет ВСЁ, включая код. Работает в 2 раза медленнее, но качественнее.

Кнопки
Кнопка	Что делает
Индексировать папку	Прочитать все файлы в папке и запомнить в RAG. Делай один раз после добавления новых документов.
Проверить орфографию	Выбираешь файл → получаешь исправленный текст. Оригинал не трогается.
Написать код	Вводишь задачу → агент пишет код, запускает и исправляет ошибки.
Полный разбор документа	Для больших книг/PDF. Разбивает на части, сохраняет чекпоинты. Если прервать — при повторном запуске продолжит с того же места.
Студия стилей Word	Открывает отдельное окно для работы со стилями (см. ниже).
Список файлов (CSV)	Генерирует CSV со списком всех файлов в папке (можно с вложенными).
График в Excel	Выбираешь Excel-файл → агент строит столбчатую диаграмму по первым двум колонкам.
Пакетное резюме	Делает резюме всех файлов в папке → собирает в один Word в output/.
Сортировка файлов	Читает первые 2000 символов каждого файла и копирует в подпапки (output/sorted_.../Договор/, .../Счет/ и т.д.). Исходники не трогаются.
Веб-поиск	Задаёшь вопрос → получаешь топ-3 результата из DuckDuckGo.
Добавить LLM (API)	Откроет окно для ввода данных внешней модели (URL, ключ, имя).
ЭКСТРЕННЫЙ СТОП	Прерывает текущую задачу, сохраняя последний результат.
💬 Работа через чат (авто-роутер)
В чат можно писать по-русски, и агент сам поймёт, что делать. Примеры:

text
Ты: проверь ошибки в D:/docs/report.docx
Агент: [Роутер] → check_spelling → ...

Ты: напиши функцию для сортировки списка
Агент: [Роутер] → generate_code → ... (код + валидация)

Ты: сделай резюме D:/docs/dogovor.docx
Агент: [Роутер] → summarize_file → ... (критик проверит)

Ты: построй график D:/data.xlsx
Агент: [Роутер] → make_excel_chart → ...

Ты: отсортируй файлы в D:/downloads
Агент: [Подтверждение] Агент хочет classify_files. Разрешить? [Да/Нет]

Ты: о чём договор аренды?
Агент: [Роутер] → ask_question (RAG) → ... (ответ с ссылкой на файл)
Логи в чате
Агент показывает каждый шаг:

[Роутер] → [...] — что он решил вызвать.

[Инструмент] ... — что выполняет.

[Критик] Попытка 1: score=6, verdict=retry — качество ответа.

Опасные действия
classify_files, batch_summarize, index_folder — спрашивают разрешения через всплывающее окно, потому что могут создать/изменить много файлов.

🧠 Критик (самопроверка)
Что это: после того, как ИИ сгенерировал ответ, вторая LLM оценивает его по 3 критериям:

Отвечает ли на задачу?

Есть ли галлюцинации?

Достаточно ли полон?

Оценка 1-10. Если < 8 — критик отправляет ответ обратно на переделку с описанием проблем. До 2-3 попыток (настраивается).

Смешанный режим (по умолчанию)
Генерация — быстрая 7B модель.

Критик для RAG — умная R1 (проверяет факты строго).

Критик для остального — быстрая 7B.

Режимы работы
enabled	force_always	Поведение
false	любое	Скорость: критика нет вообще
true	false	Баланс: критик только для RAG/резюме/структурирования (код проверяется Python-валидатором)
true	true	Максимум качества: критик после каждого шага, включая код
Менять можно на лету через чекбоксы в интерфейсе (сохраняются в config.yaml).

🌐 Подключение внешних API
Когда появятся ключи DeepSeek / Qwen / OpenAI:

Через интерфейс
Нажми "Добавить LLM (API)" в левой панели.

Заполни:

Название профиля: deepseek_api

Base URL: https://api.deepseek.com/v1

API Key: твой ключ

Имя модели: deepseek-chat

Локальная? — сними галочку

Нажми Сохранить. Модель появится в config.yaml.

Через config.yaml (вручную)
yaml
llm_profiles:
  deepseek_api:
    type: "openai_compat"
    base_url: "https://api.deepseek.com/v1"
    api_key: "sk-твойключ"
    model_name: "deepseek-chat"
    is_local: false
С этого момента агент будет использовать API-модель автоматически как fallback, если локальные падают. Ничего больше прописывать не надо — динамический роутер сам её подхватит.

🎨 Word Студия Стилей
Что это
Отдельное окно для работы со стилями Word по твоему шаблону .docx.

Как открыть
Левая панель → "Студия стилей Word".

4 режима (вкладки)
1. 🤖 ИИ Соответствие
Агент читает список стилей в документе, отправляет LLM + список стилей шаблона, получает JSON-словарь соответствий и применяет.
Пример: Heading 1 → ЗАГОЛОВОК 1 УРОВЕНЬ, Normal → Обычный.
Скорость: ~30 сек (1 запрос к LLM).

2. 🛡️ Безопасная замена
Заменяет только очевидные стили (Заголовки 1/2, Обычный текст). Ничего лишнего не трогает.
Скорость: мгновенно.

3. ⚙️ Ручное сопоставление
Показывает список стилей документа. Для каждого — выпадающий список стилей шаблона. Ты сам выбираешь соответствие.
Скорость: мгновенно после выбора.

4. 🔢 Нумерация таблиц и рисунков
Находит все таблицы и рисунки без подписи.

Добавляет "Таблица 1.", "Рисунок 1." с SEQ-полем (Word сам будет пересчитывать номера при добавлении новых).

Стиль подписи берётся из твоего шаблона (Caption или Название объекта).

Как пользоваться
Нажми "1. Выбрать шаблон (.docx)" → укажи свой файл со стилями.

Нажми "2. Выбрать документ" → укажи файл, который надо преобразовать.

Выбери вкладку и нажми кнопку.

Результат появится в output/ с префиксом (AI_, SAFE_, MANUAL_, CAPTIONED_).

Важно: твой шаблон и исходный документ никогда не изменяются — создаётся новый файл.

📁 Файловая структура
text
AGENT/
├── main.py                    # Запуск GUI
├── config.yaml                # Вся конфигурация
├── README.md                  # Этот файл
│
├── core/                      # Ядро агента
│   ├── agent.py               # Оркестратор + все инструменты
│   ├── router.py              # Роутер намерений
│   ├── self_check.py          # Критик
│   ├── workspace.py           # Безопасная работа с файлами
│   └── prompts.py             # Все промпты
│
├── llm/                       # Работа с моделями
│   ├── registry.py            # Реестр + fallback
│   ├── openai_compat.py       # Универсальный клиент API
│   ├── manual_bridge.py       # Ручной мост (последний резерв)
│   └── base.py
│
├── documents/                 # Парсинг и запись
│   ├── extractors.py          # Чтение Word/Excel/PDF/картинок
│   ├── writers.py             # Запись Word
│   ├── legacy.py              # Конвертация .doc/.xls
│   └── style_engine.py        # Работа со стилями
│
├── rag/                       # Поиск по документам
│   ├── indexer.py             # Умный чанкинг
│   └── qa.py                  # Вопрос-ответ
│
├── tools/                     # Инструменты
│   ├── validator.py           # Валидатор Python
│   ├── file_manager.py        # Список файлов
│   ├── excel_tools.py         # Графики
│   ├── web_search.py          # Веб-поиск
│   └── long_doc.py            # Чекпоинты для книг
│
├── gui/                       # Интерфейс
│   ├── app.py                 # Главное окно
│   ├── style_manager.py       # Word Студия
│   ├── config_manager.py      # Управление конфигом
│   └── tooltip.py             # Подсказки
│
├── output/                    # Результаты работы (создаётся автоматически)
│   ├── checkpoints/           # Промежуточные резюме книг
│   ├── sorted_*/              # Отсортированные файлы
│   └── *.docx, *.csv, *.xlsx  # Прочие результаты
│
├── workspace/                 # Копии файлов для безопасной работы
├── chroma_db/                 # Векторная база RAG
└── TEST_ENV/                  # Тестовые файлы (можно удалить)
🆘 Решение проблем
"500 Server Error" от LM Studio
Причина: не хватает контекста или памяти.

Решение: в LM Studio → Local Server → ползунок Context Length поставь ≥4096.

"Model not found"
Имя модели в config.yaml не совпадает с LM Studio.

Открой LM Studio → Local Server → Select a model → скопируй ID → вставь в model_name.

"ModuleNotFoundError"
Не установлена библиотека. Смотри раздел Установка.

Медленно работает
Сними галочку "Всегда (даже для кода)" в чекбоксах критика.

Или полностью отключи критика (Включить критика → выкл).

Критик постоянно возвращает "retry"
Понизь min_score в config.yaml (например, 6 вместо 8).

Или используй более умную модель для критика: critic_model: "local_logic".

Word Студия не находит стили
Убедись, что в шаблоне есть нужные стили (проверь через Word → Главная → Стили).

Если в шаблоне стили названы по-своему — используй "Ручное сопоставление".

OCR не работает
Проверь путь tesseract_path в config.yaml.

Убедись, что при установке Tesseract были отмечены языки Russian и English.

📝 Лицензия и приватность
Всё работает локально. Никакие документы не уходят в интернет (кроме случаев, когда ты сам подключаешь внешнее API). Модели LM Studio работают на твоём компьютере.

Веб-поиск отправляет только поисковый запрос в DuckDuckGo (не содержимое файлов).

Версия: 2.0
Дата: 2026
"""
}


def create_project():
    print(f"Создание финального пакета {PROJECT_NAME}...")


for filepath, content in FILES.items():
    clean_content = textwrap.dedent(content)
os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(clean_content)
print(f" Обновлен: {filepath}")

zip_name = f"{PROJECT_NAME}.zip"
with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for filepath in FILES.keys():
        zipf.write(filepath)
print(f"\nГотово! Архив {zip_name} создан.")
print(f"\nЧто внутри:")
print(f" • core/agent.py — исправлен баг с регэкспом")
print(f" • tools/web_search.py — совместимость с ddgs и duckduckgo_search")
print(f" • test_all_features_v2.py — полный тест (12 разделов)")
print(f" • README.md — полное руководство пользователя")

if name == "main":
    create_project()