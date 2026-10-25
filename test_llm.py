from llm.registry import LLMRegistry

def main():
    print("Инициализация реестра LLM...")
    registry = LLMRegistry("config.yaml")

    # Тест 1: Быстрый ассистент (Орфография)
    print("\n--- Тест 1: Быстрый ассистент (local_fast) ---")
    print("Ждем ответа от модели (это может занять 10-20 секунд)...")
    fast_llm = registry.get_model_for_task("default_model")
    response = fast_llm.generate(
        prompt="Проверь на ошибки: 'Привет, как дила? Харашо выглядишь.'",
        system_prompt="Ты — корректор русского языка. Исправь ошибки и верни только исправленный текст."
    )
    print(f"Ответ: {response}")

    # Тест 2: Написание кода (Coder)
    print("\n--- Тест 2: Кодер (local_coder) ---")
    print("Ждем ответа от модели (это может занять 10-20 секунд)...")
    coder_llm = registry.get_model_for_task("code_generation")
    code_response = coder_llm.generate(
        prompt="Напиши функцию на Python, которая проверяет, является ли число палиндромом.",
        system_prompt="Ты — опытный Python-разработчик. Отвечай только кодом."
    )
    print(f"Ответ:\n{code_response}")

    # Тест 3: Ручной мост
    print("\n--- Тест 3: Ручной мост (manual_bridge) ---")
    from llm.manual_bridge import ManualBridgeLLM
    bridge = ManualBridgeLLM()
    print(bridge.generate("Реши сложное дифференциальное уравнение..."))

if __name__ == "__main__":
    main()
