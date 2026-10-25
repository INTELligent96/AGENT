import os
from core.agent import Agent

def main():
    agent = Agent("config.yaml")

    # 1. Создадим тестовый файл (ИСПРАВЛЕНО: используем \n вместо тройных кавычек)
    test_file = "test_article.txt"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("Вчера в Москве прошла международная конференция по искусственному интеллекту.\n"
                "На ней выступили ведущие разработчики из России и Китая.\n"
                "Главной темой стало внедрение локальных LLM в корпоративный сектор.\n"
                "Ученые отметили, что количество параметров моделей растет, но требования к железу тоже.\n"
                "По итогам конференции было решено создать открытый репозиторий с лучшими практиками.\n")

    print("=== ТЕСТ 1: Резюме текста (fast) ===")
    summary = agent.summarize_file(test_file)
    print("Результат:\n", summary)

    print("\n=== ТЕСТ 2: Структурирование (logic) ===")
    struct = agent.structure_file(test_file)
    print("Результат:\n", struct)

    print("\n=== ТЕСТ 3: Проверка орфографии (fast) ===")
    bad_text_file = "test_bad.txt"
    with open(bad_text_file, "w", encoding="utf-8") as f:
        f.write("Привет, как дила? Вчира была харашая погода, но мы ни пошли гулять.")
    fixed = agent.check_spelling_file(bad_text_file)
    print("Исправленный текст:\n", fixed)

    print("\n=== ТЕСТ 4: Генерация кода (coder) ===")
    code = agent.generate_code("Напиши функцию на Python, которая считает факториал числа рекурсивно.")
    print("Код:\n", code)

if __name__ == "__main__":
    main()
