# Полный тест агента v2 - все нюансы
import os
import time
import shutil
import requests
from pathlib import Path

PASSED = 0
FAILED = 0
SKIPPED = 0
FAIL_NAMES = []


def test(name, fn, skip_if=None):
    global PASSED, FAILED, SKIPPED
    if skip_if and skip_if():
        print("  [SKIP] " + name)
        SKIPPED += 1
        return
    try:
        result = fn()
        if result is True or result is None:
            print("  [OK] " + name)
            PASSED += 1
        else:
            print("  [FAIL] " + name + " -> " + str(result)[:100])
            FAILED += 1
            FAIL_NAMES.append(name)
    except Exception as e:
        print("  [FAIL] " + name + " (exception) -> " + str(e)[:100])
        FAILED += 1
        FAIL_NAMES.append(name)


def lm_alive():
    try:
        return requests.get("http://localhost:1235/v1/models", timeout=5).status_code == 200
    except Exception:
        return False


def setup_env():
    root = Path("TEST_V2")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    (root / "doc1.txt").write_text("Компания Рога и Копыта основана в 1995 году. Директор - Иван Иванов. Адрес: Москва.", encoding="utf-8")
    (root / "doc2.txt").write_text("Телефон компании: 8-800-555-35-35. Сайт: example.com.", encoding="utf-8")
    (root / "bad.txt").write_text("Привет как дила? Харашо выглядиш.", encoding="utf-8")
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Месяц", "Продажи"])
    ws.append(["Январь", 100])
    ws.append(["Февраль", 150])
    wb.save(root / "sales.xlsx")
    from documents.writers import create_simple_docx
    create_simple_docx("Договор аренды. Сумма 50000 рублей.", str(root / "contract.docx"))
    return root


def main():
    print("=" * 60)
    print("ПОЛНЫЙ ТЕСТ v2")
    print("=" * 60)

    lm_ok = lm_alive()
    print("[LM Studio] " + ("OK (порт 1235)" if lm_ok else "НЕДОСТУПЕН"))

    from core.agent import Agent
    agent = Agent("config.yaml")
    agent.max_iterations = 3
    agent.critic.max_retries = 1

    root = setup_env()

    # ============ БЛОК 1: УТИЛИТЫ (без LLM) ============
    print("")
    print("=== Блок 1: Утилиты (без LLM) ===")

    def t_imports():
        from core.router import IntentRouter
        from core.self_check import Critic
        from rag.qa import RAGQuestionAnswerer
        from gui.app import AgentApp
        return True
    test("Импорт всех модулей", t_imports)

    def t_router_basic():
        cases = [
            ("напиши код сортировки", "generate_code"),
            ("проверь ошибки в файле", "check_spelling"),
            ("сделай резюме файла", "summarize_file"),
            ("построй график", "make_excel_chart"),
            ("найди в интернете", "web_search"),
        ]
        for text, expected in cases:
            r = agent.router.classify(text)
            if expected not in r["tools"]:
                return "router не распознал: " + text + " -> " + str(r["tools"])
        return True
    test("Роутер: 5 базовых намерений", t_router_basic)

    def t_router_pending():
        r = agent.router.classify("сделай список файлов")
        return "make_file_list" in r["tools"] or "это не make_file_list: " + str(r["tools"])
    test("Роутер: 'сделай список файлов'", t_router_pending)

    def t_sandbox_allow():
        agent.set_allowed_paths([])
        return agent._is_path_allowed("D:/any/path/file.txt") is True
    test("Sandbox: пустой = всё разрешено", t_sandbox_allow)

    def t_sandbox_block():
        agent.set_allowed_paths(["D:/DEEPSEEK/AGENT/TEST_V2"])
        r = agent._is_path_allowed("C:/Windows/file.txt")
        agent.set_allowed_paths([])
        return r is False
    test("Sandbox: блокировка чужого пути", t_sandbox_block)

    def t_sandbox_inside():
        agent.set_allowed_paths(["D:/DEEPSEEK/AGENT/TEST_V2"])
        r = agent._is_path_allowed("D:/DEEPSEEK/AGENT/TEST_V2/doc1.txt")
        agent.set_allowed_paths([])
        return r is True
    test("Sandbox: путь внутри разрешён", t_sandbox_inside)

    def t_history_trim():
        agent.chat_history = []
        for i in range(10):
            agent._append_history("q" + str(i), "a" + str(i))
        # max_history=5 => 10 элементов
        return len(agent.chat_history) == 10 or "len=" + str(len(agent.chat_history))
    test("История: обрезка до max_history", t_history_trim)

    def t_plugins():
        return "word_count" in agent.plugins
    test("Плагины: word_count загружен", t_plugins)

    def t_plugin_execute():
        result = agent.plugins["word_count"].execute("посчитай слова в " + str(root / "doc1.txt"), agent)
        return "Слов:" in result or "не сработал: " + str(result)[:100]
    test("Плагин word_count: выполнение", t_plugin_execute)

    # ============ БЛОК 2: ДОКУМЕНТЫ (без LLM) ============
    print("")
    print("=== Блок 2: Документы (без LLM) ===")

    def t_extract_txt():
        from documents.extractors import extract_text
        text = extract_text(str(root / "doc1.txt"), agent.tools)
        return "1995" in text
    test("Extract: txt", t_extract_txt)

    def t_extract_docx():
        from documents.extractors import extract_text
        text = extract_text(str(root / "contract.docx"), agent.tools)
        return "Договор" in text or "аренды" in text
    test("Extract: docx", t_extract_docx)

    def t_extract_xlsx():
        from documents.extractors import extract_text
        text = extract_text(str(root / "sales.xlsx"), agent.tools)
        return "Месяц" in text and "100" in text
    test("Extract: xlsx", t_extract_xlsx)

    def t_create_docx():
        from documents.writers import create_simple_docx
        f = root / "created.docx"
        create_simple_docx("Проверка", str(f))
        return f.exists()
    test("Create: docx", t_create_docx)

    def t_file_list():
        r = agent.make_file_list(str(root), recursive=False)
        return os.path.exists(r)
    test("Инструмент: файл-список CSV", t_file_list)

    def t_excel_chart():
        r = agent.make_excel_chart(str(root / "sales.xlsx"))
        return os.path.exists(r) and "Ошибка" not in r
    test("Инструмент: график Excel", t_excel_chart)

    def t_word_styles():
        from documents.style_engine import WordStyleEngine
        eng = WordStyleEngine(str(root / "contract.docx"))
        styles = eng.get_document_styles(str(root / "contract.docx"))
        return isinstance(styles, list)
    test("Word: чтение стилей", t_word_styles)

    # ============ БЛОК 3: LLM-фУНКЦИИ ============
    print("")
    print("=== Блок 3: LLM-функции (медленные) ===")

    def t_spelling():
        if not lm_ok:
            return "LM Studio недоступен"
        result = agent.check_spelling_file(str(root / "bad.txt"))
        return "дела" in result.lower() or "хорошо" in result.lower() or "не исправил: " + result[:100]
    test("Орфография: исправление", t_spelling, skip_if=lambda: not lm_ok)

    def t_summarize():
        if not lm_ok:
            return "LM Studio недоступен"
        result = agent.summarize_file(str(root / "doc1.txt"))
        return len(result) > 10 and "1995" in result
    test("Резюме файла", t_summarize, skip_if=lambda: not lm_ok)

    def t_rag_index():
        if not lm_ok:
            return "LM Studio недоступен"
        agent.index_folder(str(root))
        return True
    test("RAG: индексация папки", t_rag_index, skip_if=lambda: not lm_ok)

    def t_rag_question():
        if not lm_ok:
            return "LM Studio недоступен"
        ans = agent.ask_question("В каком году основана компания?")
        return "1995" in ans or "не нашёл: " + ans[:100]
    test("RAG: вопрос по году", t_rag_question, skip_if=lambda: not lm_ok)

    def t_rag_history():
        if not lm_ok:
            return "LM Studio недоступен"
        ans = agent.ask_question("а кто директор?")
        return "Иван" in ans or "не нашёл: " + ans[:100]
    test("RAG: вопрос с историей (директор)", t_rag_history, skip_if=lambda: not lm_ok)

    def t_code():
        if not lm_ok:
            return "LM Studio недоступен"
        result = agent.generate_code_with_validation("Напиши функцию сложения двух чисел")
        return "def " in result or "не сгенерировал: " + result[:100]
    test("Код: генерация + валидация", t_code, skip_if=lambda: not lm_ok)

    def t_web():
        if not lm_ok:
            return "LM Studio недоступен"
        r = agent.web_search("Python язык")
        return "http" in r
    test("Веб-поиск", t_web)

    # ============ БЛОК 4: КРИТИК И ТАЙМАУТ ============
    print("")
    print("=== Блок 4: Критик и таймаут ===")

    def t_critic_modes():
        if not lm_ok:
            return "LM Studio недоступен"
        original_enabled = agent.critic.enabled
        original_force = agent.critic.force_always
        try:
            agent.critic.enabled = False
            if agent.critic.should_check("rag") is not False:
                return "disabled не отключает"
            agent.critic.enabled = True
            agent.critic.force_always = False
            if agent.critic.should_check("rag") is not True:
                return "rag должен проверяться"
            if agent.critic.should_check("code") is not False:
                return "code не должен (без force)"
            agent.critic.force_always = True
            if agent.critic.should_check("code") is not True:
                return "force_always не работает"
            return True
        finally:
            agent.critic.enabled = original_enabled
            agent.critic.force_always = original_force
    test("Критик: тумблеры enabled/force_always", t_critic_modes, skip_if=lambda: not lm_ok)

    def t_timeout_set():
        old = agent.task_timeout
        r = agent.set_task_timeout(120)
        if agent.task_timeout != 120:
            agent.set_task_timeout(old)
            return "set не сработал: " + str(r)
        agent.set_task_timeout(old)
        return True
    test("Таймаут: установка через метод", t_timeout_set)

    # ============ ФИНАЛ ============
    print("")
    print("=" * 60)
    print("ИТОГИ")
    print("=" * 60)
    print("Пройдено: " + str(PASSED))
    print("Провалено: " + str(FAILED))
    print("Пропущено: " + str(SKIPPED))
    if FAIL_NAMES:
        print("")
        print("Провалы:")
        for name in FAIL_NAMES:
            print("  - " + name)


if __name__ == "__main__":
    main()