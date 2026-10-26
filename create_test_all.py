import os
import zipfile
import textwrap

PROJECT_NAME = "agent_full_test"

FILES = {
    "test_full_suite.py": """\
\"\"\"
ПОЛНЫЙ ТЕСТ ВСЕХ ФУНКЦИЙ АГЕНТА.
Запускать: python test_full_suite.py
Требования: LM Studio должен быть запущен (порт 1235).
\"\"\"
import os
import shutil
import time
from pathlib import Path

PASSED = []
FAILED = []
SKIPPED = []

def test_result(name, ok, detail=""):
    if ok:
        PASSED.append(name)
        print(f"  [OK] {name} {detail}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name} {detail}")

def test_skip(name, reason):
    SKIPPED.append(name)
    print(f"  [SKIP] {name} ({reason})")

def setup_env():
    root = Path("TEST_FULL")
    if root.exists(): shutil.rmtree(root)
    root.mkdir()

    # Текстовый файл
    (root / "doc1.txt").write_text("Компания Рога и Копыта основана в 1995 году. Директор — Иван Иванов.", encoding="utf-8")

    # Word
    from documents.writers import create_simple_docx
    create_simple_docx("Это договор аренды. Сумма: 50000 руб.", str(root / "contract.docx"))

    # Excel
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Месяц", "Продажи"]); ws.append(["Январь", 100]); ws.append(["Февраль", 150]); ws.append(["Март", 200])
    wb.save(root / "sales.xlsx")

    # Большой текст
    big = " ".join(["Это очень длинный текст для проверки чекпоинтов и разбиения."] * 80)
    (root / "big_book.txt").write_text(big, encoding="utf-8")

    return root

def main():
    print("=" * 60)
    print("ПОЛНЫЙ ТЕСТ АГЕНТА")
    print("=" * 60)
    print("ВНИМАНИЕ: LM Studio должен быть запущен на порту 1235.")
    print("Тест займёт 5-10 минут.\\n")

    # Проверка LM Studio
    import requests
    try:
        r = requests.get("http://localhost:1235/v1/models", timeout=5)
        if r.status_code != 200:
            print("[КРИТИЧНО] LM Studio не отвечает. Тест прерван.")
            return
        print(f"[LM Studio] Доступно моделей: {len(r.json().get('data', []))}")
    except Exception as e:
        print(f"[КРИТИЧНО] Не удалось связаться с LM Studio: {e}")
        return

    # Инициализация
    from core.agent import Agent
    from llm.registry import LLMRegistry

    try:
        agent = Agent("config.yaml")
        print("[Инициализация] Агент загружен.\\n")
    except Exception as e:
        print(f"[КРИТИЧНО] Ошибка загрузки агента: {e}")
        return

    # Снижаем итерации для скорости
    agent.max_iterations = 3
    agent.critic.max_retries = 1

    # --- Среда ---
    print("\\n[1] Подготовка тестовой среды...")
    try:
        root = setup_env()
        print(f"  Папка: {root.absolute()}")
        test_result("Создание тестовой среды", True)
    except Exception as e:
        test_result("Создание тестовой среды", False, str(e))
        return

    # --- Роутер ---
    print("\\n[2] Роутер намерений...")
    cases = [
        ("напиши код сортировки", "generate_code"),
        ("проверь ошибки в файле doc1.txt", "check_spelling"),
        ("сделай резюме doc1.txt", "summarize_file"),
        ("построй график в excel", "make_excel_chart"),
        ("найди в интернете погоду", "web_search"),
    ]
    for text, expected in cases:
        try:
            r = agent.router.classify(text)
            ok = expected in r["tools"]
            test_result(f"Роутер: '{text[:30]}...' → {r['tools']}", ok, f"(ожидался {expected})")
        except Exception as e:
            test_result(f"Роутер: '{text[:30]}'", False, str(e))

    # --- Орфография ---
    print("\\n[3] Проверка орфографии...")
    try:
        bad = root / "bad.txt"
        bad.write_text("Привет, как дила? Вчира харашо погуляли.", encoding="utf-8")
        result = agent.check_spelling_file(str(bad))
        ok = "дела" in result.lower() or "вчера" in result.lower()
        test_result("Орфография", ok, f"(ответ: {result[:80]}...)")
    except Exception as e:
        test_result("Орфография", False, str(e))

    # --- RAG ---
    print("\\n[4] RAG (индексация + вопрос)...")
    try:
        agent.index_folder(str(root))
        answer = agent.ask_question("В каком году основана компания?")
        ok = "1995" in answer
        test_result("RAG-индексация", True)
        test_result("RAG-вопрос", ok, f"(ответ: {answer[:80]}...)")
    except Exception as e:
        test_result("RAG", False, str(e))

    # --- Код ---
    print("\\n[5] Генерация кода...")
    try:
        code = agent.generate_code_with_validation("Напиши функцию сложения двух чисел")
        ok = "def " in code and "+" in code
        test_result("Генерация кода", ok)
    except Exception as e:
        test_result("Генерация кода", False, str(e))

    # --- Критик ---
    print("\\n[6] Самопроверка (Критик)...")
    try:
        should_rag = agent.critic.should_check("rag")
        should_code = agent.critic.should_check("code")
        test_result("Критик: RAG должен проверяться", should_rag)
        test_result("Критик: код НЕ должен (без force_always)", not should_code)
    except Exception as e:
        test_result("Критик", False, str(e))

    # --- Список файлов ---
    print("\\n[7] Список файлов...")
    try:
        csv = agent.make_file_list(str(root), recursive=False)
        ok = os.path.exists(csv)
        test_result("Список файлов (CSV)", ok, f"→ {csv}")
    except Exception as e:
        test_result("Список файлов", False, str(e))

    # --- График Excel ---
    print("\\n[8] График в Excel...")
    try:
        chart = agent.make_excel_chart(str(root / "sales.xlsx"))
        ok = os.path.exists(chart) and "Ошибка" not in chart
        test_result("График Excel", ok, f"→ {chart}")
    except Exception as e:
        test_result("График Excel", False, str(e))

    # --- Длинный документ ---
    print("\\n[9] Чекпоинты (длинные документы)...")
    try:
        r = agent.process_long_document(str(root / "big_book.txt"))
        ok = "FINAL" in r or os.path.exists("output/checkpoints/FINAL_big_book.txt")
        test_result("Длинный документ (checkpoints)", ok, r[:100])
    except Exception as e:
        test_result("Длинный документ", False, str(e))

    # --- Сортировка ---
    print("\\n[10] Сортировка файлов...")
    try:
        sorted_dir = agent.classify_files(str(root))
        ok = os.path.exists(sorted_dir)
        subdirs = os.listdir(sorted_dir) if ok else []
        test_result("Сортировка файлов", ok, f"(категории: {subdirs})")
    except Exception as e:
        test_result("Сортировка файлов", False, str(e))

    # --- Веб-поиск ---
    print("\\n[11] Веб-поиск...")
    try:
        r = agent.web_search("Python язык программирования")
        ok = "http" in r
        test_result("Веб-поиск", ok, f"(длина ответа: {len(r)})")
    except Exception as e:
        test_result("Веб-поиск", False, str(e))

    # --- Word Стили ---
    print("\\n[12] Word Студия (стили)...")
    try:
        from documents.style_engine import WordStyleEngine
        from documents.writers import create_simple_docx
        # Создадим "шаблон" и "документ"
        create_simple_docx("Тестовый документ для стилей", str(root / "styled_doc.docx"))
        engine = WordStyleEngine(str(root / "styled_doc.docx"))
        styles = engine.get_document_styles(str(root / "contract.docx"))
        test_result("Word: чтение стилей", len(styles) > 0, f"(стили: {styles})")

        # Применение mapping
        out = engine.apply_mapping(str(root / "contract.docx"), {"Normal": styles[0] if styles else "Normal"}, "TEST_STYLED.docx")
        test_result("Word: применение стилей", os.path.exists(out))
    except Exception as e:
        test_result("Word Стили", False, str(e))

    # --- GUI импорт ---
    print("\\n[13] Проверка GUI (импорт)...")
    try:
        from gui.app import AgentApp
        from gui.style_manager import StyleManagerWindow
        from gui.tooltip import ToolTip
        from gui.config_manager import load_config, save_config, add_llm_profile
        test_result("Импорт GUI-модулей", True)
    except Exception as e:
        test_result("Импорт GUI", False, str(e))

    # --- Итоги ---
    print("\\n" + "=" * 60)
    print("ИТОГИ")
    print("=" * 60)
    print(f"Пройдено: {len(PASSED)}")
    print(f"Провалено: {len(FAILED)}")
    print(f"Пропущено: {len(SKIPPED)}")

    if FAILED:
        print("\\nПроваленные тесты:")
        for f in FAILED: print(f"  - {f}")

    if not FAILED:
        print("\\nВСЁ РАБОТАЕТ! Агент готов к использованию.")
    else:
        print("\\nЕсть проблемы. Проверь логи выше.")

if __name__ == "__main__":
    main()
"""
}


def create_project():
    print(f"Создание {PROJECT_NAME}...")
    for filepath, content in FILES.items():
        clean_content = textwrap.dedent(content)
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(clean_content)
        print(f"  Создан: {filepath}")

    zip_name = f"{PROJECT_NAME}.zip"
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filepath in FILES.keys():
            zipf.write(filepath)
    print(f"\\nГотово! Архив {zip_name} создан. Распакуй поверх проекта.")
    print("Запускай test_full_suite.py — он проверит всё.")


if __name__ == "__main__":
    create_project()