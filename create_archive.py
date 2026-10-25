import os
import zipfile
import textwrap

PROJECT_NAME = "agent_llm_foundation"

FILES = {
    "config.yaml": """\
# Конфигурация LLM профилей (Обновлено под твой API)
llm_profiles:
  # Локальные модели из твоего LM Studio (порт 1235)
  local_coder:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen-qwen2.5-coder-14b-instruct"
    description: "Qwen2.5 Coder 14B — для написания кода на Python"

  local_logic:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "deepseek-r1-0528-qwen3-8b-abliterated"
    description: "DeepSeek R1 8B — для сложных рассуждений и структурирования"

  local_fast:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen2.5-7b-instruct-uncensored"
    description: "Qwen2.5 7B — для орфографии, перепечатывания и быстрых ответов"

  # Заготовки под внешние API (раскомментируй, когда появятся ключи)
  # deepseek_api:
  #   type: "openai_compat"
  #   base_url: "https://api.deepseek.com/v1"
  #   api_key: "ТВОЙ_КЛЮЧ_ЗДЕСЬ"
  #   model_name: "deepseek-chat"
  #   description: "Внешний API DeepSeek"

# Настройки роутинга по умолчанию
routing:
  default_model: "local_fast"
  code_generation: "local_coder"
  complex_reasoning: "local_logic"
""",

    "llm/__init__.py": "",

    "llm/base.py": """\
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class BaseLLM(ABC):
    \"\"\"Базовый интерфейс для всех LLM-провайдеров.\"\"\"

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        \"\"\"Генерирует ответ на основе промпта.\"\"\"
        pass
""",

    "llm/openai_compat.py": """\
import requests
from typing import Optional
from .base import BaseLLM

class OpenAICompatLLM(BaseLLM):
    \"\"\"
    Универсальный клиент для любого OpenAI-совместимого API.
    Отлично работает с LM Studio, DeepSeek, Qwen, OpenRouter и т.д.
    \"\"\"
    def __init__(self, base_url: str, api_key: str, model_name: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        data = {
            "model": self.model_name,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 4096),
            "stream": False
        }

        try:
            # Таймаут увеличен до 5 минут, так как локальные модели могут думать долго
            response = requests.post(url, headers=headers, json=data, timeout=300)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            return f"Ошибка при запросе к LLM ({self.model_name}): {str(e)}"
""",

    "llm/manual_bridge.py": """\
from .base import BaseLLM
from typing import Optional

class ManualBridgeLLM(BaseLLM):
    \"\"\"
    Ручной мост для сложных задач.
    Вместо отправки запроса возвращает промпт, чтобы пользователь 
    скопировал его в веб-чат (DeepSeek/Qwen) и вставил ответ.
    \"\"\"
    def __init__(self):
        self.pending_prompt = None

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        full_prompt = ""
        if system_prompt:
            full_prompt += f"СИСТЕМНАЯ ИНСТРУКЦИЯ:\\n{system_prompt}\\n\\n"
        full_prompt += f"ЗАДАЧА:\\n{prompt}"

        self.pending_prompt = full_prompt
        return (
            "[РЕЖИМ РУЧНОГО МОСТА]\\n"
            "Задача слишком сложная для локальной модели (или выбран этот режим вручную).\\n"
            "Пожалуйста, скопируйте текст ниже в DeepSeek/Qwen через браузер, "
            "а полученный ответ вставьте обратно в систему.\\n\\n"
            f"--- НАЧАЛО ПРОМПТА ---\\n{full_prompt}\\n--- КОНЕЦ ПРОМПТА ---"
        )
""",

    "llm/registry.py": """\
import yaml
import os
from typing import Dict, Any
from .openai_compat import OpenAICompatLLM
from .manual_bridge import ManualBridgeLLM
from .base import BaseLLM

class LLMRegistry:
    \"\"\"Управляет профилями моделей и роутингом задач.\"\"\"
    def __init__(self, config_path: str = "config.yaml"):
        self.instances: Dict[str, BaseLLM] = {}
        self.routing = {}
        self.load_config(config_path)

    def load_config(self, config_path: str):
        if not os.path.exists(config_path):
            print(f"Файл конфигурации {config_path} не найден!")
            return

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        profiles = config.get("llm_profiles", {})
        for name, params in profiles.items():
            if params.get("type") == "openai_compat":
                self.instances[name] = OpenAICompatLLM(
                    base_url=params["base_url"],
                    api_key=params["api_key"],
                    model_name=params["model_name"]
                )
            elif params.get("type") == "manual_bridge":
                self.instances[name] = ManualBridgeLLM()

        self.routing = config.get("routing", {})

    def get_model_for_task(self, task_type: str) -> BaseLLM:
        \"\"\"Возвращает нужную модель в зависимости от типа задачи.\"\"\"
        model_key = self.routing.get(task_type, self.routing.get("default_model"))
        if model_key not in self.instances:
            raise ValueError(f"Модель '{model_key}' для задачи '{task_type}' не найдена в конфиге.")
        return self.instances[model_key]
""",

    "test_llm.py": """\
from llm.registry import LLMRegistry

def main():
    print("Инициализация реестра LLM...")
    registry = LLMRegistry("config.yaml")

    # Тест 1: Быстрый ассистент (Орфография)
    print("\\n--- Тест 1: Быстрый ассистент (local_fast) ---")
    print("Ждем ответа от модели (это может занять 10-20 секунд)...")
    fast_llm = registry.get_model_for_task("default_model")
    response = fast_llm.generate(
        prompt="Проверь на ошибки: 'Привет, как дила? Харашо выглядишь.'",
        system_prompt="Ты — корректор русского языка. Исправь ошибки и верни только исправленный текст."
    )
    print(f"Ответ: {response}")

    # Тест 2: Написание кода (Coder)
    print("\\n--- Тест 2: Кодер (local_coder) ---")
    print("Ждем ответа от модели (это может занять 10-20 секунд)...")
    coder_llm = registry.get_model_for_task("code_generation")
    code_response = coder_llm.generate(
        prompt="Напиши функцию на Python, которая проверяет, является ли число палиндромом.",
        system_prompt="Ты — опытный Python-разработчик. Отвечай только кодом."
    )
    print(f"Ответ:\\n{code_response}")

    # Тест 3: Ручной мост
    print("\\n--- Тест 3: Ручной мост (manual_bridge) ---")
    from llm.manual_bridge import ManualBridgeLLM
    bridge = ManualBridgeLLM()
    print(bridge.generate("Реши сложное дифференциальное уравнение..."))

if __name__ == "__main__":
    main()
"""
}


def create_project():
    print(f"Создание проекта {PROJECT_NAME}...")

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

    print(f"\\nГотово! Архив {zip_name} успешно создан.")
    print(f"Распакуй его и скопируй папку 'llm', файлы 'config.yaml' и 'test_llm.py' в корень твоего проекта.")


if __name__ == "__main__":
    create_project()