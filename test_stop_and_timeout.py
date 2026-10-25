import threading
import time
from core.agent import Agent

def main():
    agent = Agent("config.yaml")

    print("=== ТЕСТ: Итерации, Таймаут и Экстренная остановка ===")

    # Мы запустим агента в отдельном потоке (как это будет в интерфейсе),
    # чтобы иметь возможность нажать "Стоп" во время его работы.

    task = "Напиши сложную функцию с кучей условий, чтобы модель думала подольше."

    # Функция-обертка для запуска в потоке
    def run_agent():
        print("Агент начал работу...")
        result = agent.generate_code_with_validation(task)
        print("\nРезультат агента:\n", result)

    agent_thread = threading.Thread(target=run_agent)
    agent_thread.start()

    # Симулируем нажатие кнопки "Стоп" через 3 секунды
    print("Ждем 3 секунды и нажимаем 'Стоп' (симуляция)...")
    time.sleep(3)
    agent.request_stop()

    # Ждем завершения потока
    agent_thread.join()
    print("Тест завершен.")

if __name__ == "__main__":
    main()
