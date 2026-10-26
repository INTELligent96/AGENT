#НЕРАБОЧИЙ


import os
import zipfile
import textwrap

PROJECT_NAME = "agent_step10_fix_and_tests"

FILES = {
    # Исправленный agent.py — исправлен regex в _extract_path_from_text
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

    def run_task(self, user_text: str, log_callback=None) -> str:
        def log(msg):
            print(msg)
            if log_callback: log_callback(msg)

        log(f"[Роутер] Анализирую запрос...")
        routing = self.router.classify(user_text)
        tools = routing.get("tools", ["ask_question"])
        log(f"[Роутер] -> {tools} ({routing.get('reasoning', '')})")

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
        \"\"\"Ищет путь в тексте. Используем \\\\x22 (") и \\\\x27 (') чтобы не сломать regex.\"\"\"
        import re
        # Поиск в кавычках: ищем "path.ext" или 'path.ext'
        quoted = re.findall(r'[\\x22\\x27]([^\\x22\\x27]+\\.[a-z]{2,4})[\\x22\\x27]', text)
        if quoted:
            return quoted[0]
        # Поиск по расширениям без кавычек
        paths = re.findall(r'([A-Za-z]:[^\\s]+|\\S+\\.[a-z]{2,4})', text)
        return paths[0] if paths else None

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

    # Комплексный тест всех функций
    "test_full_system.py": """\
\"\"\"
ПОЛНЫЙ ТЕСТ ВСЕХ ФУНКЦИЙ АГЕНТА.
Запускается в неинтерактивном режиме. Создаёт тестовые файлы, прогоняет
все инструменты и выводит статус по каждому пункту.
\"\"\"
import os
import sys
import shutil
import traceback
from pathlib import Path

# Блокируем возможные всплывающие окна
import tkinter.messagebox as _mb
_mb.showinfo = lambda *a, **kw: None
_mb.showerror = lambda *a, **kw: None
_mb.askyesno = lambda *a, **kw: True

from core.agent import Agent
from documents.writers import create_simple_docx

RESULTS = []

def report(name, ok, details=""):
    status = "OK  " if ok else "FAIL"
    print(f"[{status}] {name}" + (f" | {details}" if details else ""))
    RESULTS.append((name, ok, details))

def run_test(name, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        if result is None:
            report(name, False, "вернул None")
            return None
        if isinstance(result, str) and (not result.strip() or result.startswith("[КРИТИЧЕСКАЯ")):
            report(name, False, result[:150])
            return result
        report(name, True)
        return result
    except Exception as e:
        report(name, False, f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return None

def setup_test_env():
    test_dir = Path("TEST_FULL")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    (test_dir / "story.txt").write_text(
        "Компания Рога и Копыта основана в 1995 году в Москве. "
        "Генеральный директор — Иван Петров. Телефон: 8-800-555-35-35.",
        encoding="utf-8"
    )
    (test_dir / "bad.txt").write_text(
        "Привет, как дила? Вчира была харашая погода.", encoding="utf-8"
    )
    create_simple_docx("Это договор аренды помещения. Сумма 50 000 рублей.", str(test_dir / "contract.docx"))

    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Месяц", "Продажи"])
    ws.append(["Январь", 100])
    ws.append(["Февраль", 150])
    ws.append(["Март", 200])
    wb.save(test_dir / "sales.xlsx")

    big_text = " ".join(["Это длинный текст для проверки чекпоинтов."] * 200)
    (test_dir / "big.txt").write_text(big_text, encoding="utf-8")
    return test_dir

def main():
    print("=" * 70)
    print("  ПОЛНЫЙ ТЕСТ АГЕНТА (все функции)")
    print("=" * 70)
    print("ВНИМАНИЕ: тест делает запросы к LLM. Убедитесь, что LM Studio работает.\\n")

    test_dir = setup_test_env()
    print(f"Тестовая папка: {test_dir.absolute()}\\n")

    try:
        agent = Agent("config.yaml")
    except Exception as e:
        print(f"[FATAL] Не удалось инициализировать агента: {e}")
        return

    # ============ БЛОК 1: БЕЗ LLM ============
    print("\\n--- БЛОК 1: Базовые проверки (без LLM) ---")

    # 1.1. Извлечение пути (ранее ломавшийся regex)
    def test_path():
        r1 = agent._extract_path_from_text('сделай резюме "D:/file.txt"')
        r2 = agent._extract_path_from_text("сделай резюме 'D:/file.txt'")
        r3 = agent._extract_path_from_text("проверь D:/file.docx пожалуйста")
        assert r1 == "D:/file.txt", f"Одинарные кавычки в двойных: получили {r1}"
        assert r2 == "D:/file.txt", f"Двойные кавычки в одинарных: получили {r2}"
        assert r3 == "D:/file.docx", f"Без кавычек: получили {r3}"
        return "все 3 варианта ок"
    run_test("1.1. Извлечение пути из текста", test_path)

    # 1.2. Роутер по ключевым словам
    def test_router_kw():
        cases = {
            "напиши код на питоне": "generate_code",
            "проверь ошибки в файле": "check_spelling",
            "сделай резюме документа": "summarize_file",
            "построй график в excel": "make_excel_chart",
            "найди в интернете погоду": "web_search",
            "переведи текст": "translate",
            "список файлов": "make_file_list",
        }
        for text, expected in cases.items():
            r = agent.router.classify(text)
            tools = r.get("tools", [])
            assert expected in tools, f"'{text}' -> {tools}, ждали '{expected}'"
        return f"проверено {len(cases)} кейсов"
    run_test("1.2. Роутер: ключевые слова", test_router_kw)

    # 1.3. Настройки критика
    def test_critic_cfg():
        # По умолчанию enabled=true, force_always=false
        orig_enabled = agent.critic.enabled
        orig_force = agent.critic.force_always

        agent.critic.enabled = True; agent.critic.force_always = False
        assert agent.critic.should_check("code") == False, "code без force должен быть False"
        assert agent.critic.should_check("rag") == True, "rag должен быть True"

        agent.critic.force_always = True
        assert agent.critic.should_check("code") == True, "code с force должен быть True"

        agent.critic.enabled = False
        assert agent.critic.should_check("rag") == False, "disabled должен быть False"

        agent.critic.enabled = orig_enabled
        agent.critic.force_always = orig_force
        return "логика should_check корректна"
    run_test("1.3. Настройки критика (should_check)", test_critic_cfg)

    # ============ БЛОК 2: LLM-ФУНКЦИИ ============
    print("\\n--- БЛОК 2: LLM-функции ---")

    run_test("2.1. Проверка орфографии",
             lambda: agent.check_spelling_file(str(test_dir / "bad.txt")))

    run_test("2.2. Резюме файла",
             lambda: agent.summarize_file(str(test_dir / "story.txt")))

    run_test("2.3. Структурирование",
             lambda: agent.structure_file(str(test_dir / "story.txt")))

    run_test("2.4. Генерация кода",
             lambda: agent.generate_code_with_validation("Напиши функцию суммы двух чисел"))

    # ============ БЛОК 3: RAG ============
    print("\\n--- БЛОК 3: RAG (индексация и вопросы) ---")
    run_test("3.1. Индексация папки",
             lambda: agent.index_folder(str(test_dir)))
    run_test("3.2. Вопрос по документам (RAG)",
             lambda: agent.ask_question("В каком году основана компания?"))

    # ============ БЛОК 4: ИНСТРУМЕНТЫ ============
    print("\\n--- БЛОК 4: Инструменты (файлы, Excel, поиск) ---")
    run_test("4.1. Список файлов CSV",
             lambda: agent.make_file_list(str(test_dir), recursive=True))
    run_test("4.2. График в Excel",
             lambda: agent.make_excel_chart(str(test_dir / "sales.xlsx")))
    run_test("4.3. Веб-поиск",
             lambda: agent.web_search("Python язык программирования"))

    # ============ БЛОК 5: ПРОДВИНУТЫЕ ============
    print("\\n--- БЛОК 5: Продвинутые (чекпоинты, пакет, сортировка) ---")
    run_test("5.1. Разбор длинного документа (checkpoints)",
             lambda: agent.process_long_document(str(test_dir / "big.txt")))
    run_test("5.2. Пакетное резюме папки",
             lambda: agent.batch_summarize(str(test_dir)))
    run_test("5.3. Сортировка файлов",
             lambda: agent.classify_files(str(test_dir)))

    # ============ БЛОК 6: END-TO-END ЧЕРЕЗ РОУТЕР ============
    print("\\n--- БЛОК 6: Сквозной тест (чат -> роутер -> инструмент) ---")
    run_test("6.1. Запрос: 'сделай резюме story.txt'",
             lambda: agent.run_task(f"сделай резюме '{test_dir / 'story.txt'}'"))
    run_test("6.2. Запрос: 'в каком году основана компания?' (RAG)",
             lambda: agent.run_task("в каком году основана компания?"))

    # ============ ИТОГ ============
    print("\\n" + "=" * 70)
    print("  ИТОГИ")
    print("=" * 70)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    for name, ok, details in RESULTS:
        marker = "✓" if ok else "✗"
        line = f"  {marker} {name}"
        if not ok and details:
            line += f"  ← {details}"
        print(line)
    print(f"\\n  Итого: {passed}/{total} ({passed*100//max(total,1)}%)")
    print(f"  Все результаты сохранены в '{os.path.abspath('output')}'")
    print("=" * 70)

if __name__ == "__main__":
    main()
""",

    # Краткая справка
    "README.md": """\
# AI Document Agent PRO

Локальный ИИ-агент для работы с документами (Word, Excel, PDF, изображения) на русском языке. Использует LM Studio для локальных моделей и поддерживает любые OpenAI-совместимые API.

## Установка

1. **Python 3.10+**
2. **LM Studio** — загрузите модели и включите Local Server (порт 1235)
3. **Tesseract OCR** (для картинок): установите с языками `rus` и `eng`
4. **Microsoft Office** (или LibreOffice) для старых `.doc`/`.xls`

```bash
pip install -r requirements.txt
python main.py
 
 '''\ ,
}