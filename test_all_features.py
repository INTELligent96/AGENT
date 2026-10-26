import os
import shutil
from pathlib import Path
from core.agent import Agent
from documents.writers import create_simple_docx

def setup_test_env():
    test_dir = Path("TEST_ENV")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    # 1. Текстовый файл
    (test_dir / "doc1.txt").write_text("Компания Рога и Копыта основана в 1995 году. Директор - Иван.", encoding="utf-8")

    # 2. Word файл
    create_simple_docx("Это договор аренды помещения. Сумма: 50 000 рублей.", str(test_dir / "doc2.docx"))

    # 3. Excel файл с данными для графика
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Месяц", "Продажи"])
    ws.append(["Январь", 100])
    ws.append(["Февраль", 150])
    ws.append(["Март", 200])
    wb.save(test_dir / "sales.xlsx")

    # 4. Большой файл для чекпоинтов
    big_text = " ".join(["Это очень длинный текст для проверки чекпоинтов."] * 100)
    (test_dir / "big_book.txt").write_text(big_text, encoding="utf-8")

    return test_dir

def main():
    print("=== ЗАПУСК ПОЛНОГО ТЕСТА АГЕНТА ===")
    print("ВНИМАНИЕ: Тест делает много запросов к LLM. Убедитесь, что LM Studio работает!\n")

    test_dir = setup_test_env()
    print(f"Создана тестовая папка: {test_dir.absolute()}\n")

    agent = Agent("config.yaml")

    # 1. Тест чтения и орфографии
    print("--- 1. Проверка орфографии ---")
    res = agent.check_spelling_file(str(test_dir / "doc1.txt"))
    print(f"Результат: {res[:100]}...\n")

    # 2. Тест RAG (Индексация и Вопрос)
    print("--- 2. RAG Индексация и Вопрос ---")
    agent.index_folder(str(test_dir))
    answer = agent.ask_question("В каком году основана компания?")
    print(f"Ответ: {answer}\n")

    # 3. Тест написания кода
    print("--- 3. Генерация кода ---")
    code = agent.generate_code_with_validation("Напиши функцию сложения двух чисел.")
    print(f"Код:\n{code}\n")

    # 4. Тест длинных документов (Checkpoints)
    print("--- 4. Полный разбор длинного документа (Checkpoints) ---")
    res_long = agent.process_long_document(str(test_dir / "big_book.txt"))
    print(f"Результат: {res_long}\n")

    # 5. Тест списка файлов
    print("--- 5. Создание списка файлов ---")
    csv_file = agent.make_file_list(str(test_dir), recursive=True)
    print(f"Список сохранен: {csv_file}\n")

    # 6. Тест графика Excel
    print("--- 6. График в Excel ---")
    chart_file = agent.make_excel_chart(str(test_dir / "sales.xlsx"))
    print(f"График сохранен: {chart_file}\n")

    # 7. Тест сортировки
    print("--- 7. Сортировка файлов ---")
    sorted_dir = agent.classify_files(str(test_dir))
    print(f"Отсортировано в: {sorted_dir}\n")

    # 8. Тест веб-поиска
    print("--- 8. Веб-поиск ---")
    web_res = agent.web_search("Кто президент России?")
    print(f"Поиск: {web_res[:150]}...\n")

    print("=== ТЕСТ ЗАВЕРШЕН УСПЕШНО ===")
    print(f"Все результаты сохранены в папке 'output'. Проверь её!")

if __name__ == "__main__":
    main()
