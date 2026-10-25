from llm.registry import LLMRegistry
import yaml

def main():
    print("=== ТЕСТ: Динамический роутинг ===")

    # 1. Смотрим, как строится цепочка
    registry = LLMRegistry("config.yaml")

    print("Текущие модели в конфиге:")
    for name, params in registry.config.get('llm_profiles', {}).items():
        loc = "API" if params.get('is_local') is False else ("Local" if params.get('is_local') else "Special")
        print(f"  - {name} ({loc})")

    print("\nЦепочка для задачи 'code_generation':")
    chain = registry._build_fallback_chain("code_generation")
    for i, m in enumerate(chain):
        print(f"  {i+1}. {m}")

    print("\nЦепочка для задачи 'complex_reasoning':")
    chain2 = registry._build_fallback_chain("complex_reasoning")
    for i, m in enumerate(chain2):
        print(f"  {i+1}. {m}")

    print("\n=== Имитация сбоя локальной модели ===")
    # Отправляем задачу. Если R1 (local_logic) жива, она ответит.
    # Если она упадет, роутер пойдет по цепочке дальше.
    response = registry.generate_with_fallback(
        "complex_reasoning", 
        "Скажи 'Привет, я работаю!' и укажи свою модель."
    )
    print("\nОТВЕТ:\n", response)

if __name__ == "__main__":
    main()
