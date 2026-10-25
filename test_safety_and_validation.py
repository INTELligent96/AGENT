import os
from core.agent import Agent

def main():
    agent = Agent("config.yaml")

    # --- ТЕСТ 1: Безопасность исходников ---
    print("=== ТЕСТ 1: Защита оригиналов (Workspace) ===")
    # Создаем файл в корне
    orig_file = "my_precious_data.txt"
    with open(orig_file, "w", encoding="utf-8") as f:
        f.write("Этот текст нельзя менять!")

    print("Отправляем файл агенту на проверку...")
    # Агент должен создать копию в workspace и работать с ней
    result = agent.check_spelling_file(orig_file)
    print("Результат агента:", result)

    # Проверяем, изменился ли оригинал
    with open(orig_file, "r", encoding="utf-8") as f:
        content = f.read()
    print(f"Содержимое оригинала: '{content}'")
    if content == "Этот текст нельзя менять!":
        print("✅ Оригинал не тронут!")
    else:
        print("❌ ОРИГИНАЛ БЫЛ ИЗМЕНЕН!")

    # --- ТЕСТ 2: Итеративная валидация кода ---
    print("\n=== ТЕСТ 2: Итерации и валидация кода ===")
    # Специально даем задачу, где легко ошибиться (например, деление на ноль)
    # или просто сложную задачу, чтобы посмотреть, как работает цикл
    task = "Напиши функцию, которая принимает список чисел и возвращает среднее арифметическое. Обработай случай пустого списка."
    print(f"Задача: {task}")

    final_code = agent.generate_code_with_validation(task)
    print("\nФинальный код:\n", final_code)

if __name__ == "__main__":
    main()
