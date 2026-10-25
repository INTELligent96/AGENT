import os
import zipfile
import textwrap

PROJECT_NAME = "agent_dynamic_routing"

FILES = {
    "config.yaml": """\
llm_profiles:
  local_coder:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen-qwen2.5-coder-14b-instruct"
    is_local: true

  local_logic:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "deepseek-r1-0528-qwen3-8b-abliterated"
    is_local: true

  local_fast:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen2.5-7b-instruct-uncensored"
    is_local: true

  # ПРИМЕР: API-модель (раскомментируй, когда появятся ключи)
  # deepseek_api:
  #   type: "openai_compat"
  #   base_url: "https://api.deepseek.com/v1"
  #   api_key: "sk-твой-ключ"
  #   model_name: "deepseek-coder"
  #   is_local: false

  manual_bridge:
    type: "manual_bridge"

# Теперь здесь указываются только ПРЕДПОЧТИТЕЛЬНЫЕ модели для старта
routing:
  default_model: "local_fast"
  code_generation: "local_coder"
  complex_reasoning: "local_logic"

tools:
  tesseract_path: "K:/Program Files/Tesseract-OCR/tesseract.exe"
  use_ms_office: true 

safety:
  read_only_originals: true 
  workspace_dir: "workspace" 

agent_loop:
  max_iterations: 10
  task_timeout_seconds: 600
  code_execution_timeout: 15
  max_tokens_default: 4096
  retry_attempts: 2
  retry_delay_seconds: 2

rag:
  db_path: "chroma_db"
  collection_name: "documents"
  chunk_size: 1000
  chunk_overlap: 200
  embedding_model: "paraphrase-multilingual-MiniLM-L12-v2"
  separators: ["\\n\\n", "\\n", ". ", "! ", "? ", " ", ""]
""",

    "llm/registry.py": """\
import yaml
import time
from typing import Dict, Any, List
from .openai_compat import OpenAICompatLLM
from .manual_bridge import ManualBridgeLLM
from .base import BaseLLM

class LLMRegistry:
    def __init__(self, config_path: str = "config.yaml"):
        self.instances: Dict[str, BaseLLM] = {}
        self.config = {}
        self.loop_settings = {}
        self.load_config(config_path)

    def load_config(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.loop_settings = self.config.get("agent_loop", {})

        profiles = self.config.get("llm_profiles", {})
        for name, params in profiles.items():
            if params.get("type") == "openai_compat":
                self.instances[name] = OpenAICompatLLM(
                    base_url=params["base_url"],
                    api_key=params["api_key"],
                    model_name=params["model_name"]
                )
            elif params.get("type") == "manual_bridge":
                self.instances[name] = ManualBridgeLLM()

    def _build_fallback_chain(self, task_type: str) -> List[str]:
        \"\"\"Динамически строит цепочку из всех доступных моделей.\"\"\"
        # 1. Берем предпочтительную модель из конфига
        preferred = self.config.get("routing", {}).get(task_type)
        chain = [preferred] if preferred else []

        # 2. Добавляем все API-модели (is_local = False)
        profiles = self.config.get("llm_profiles", {})
        for name, params in profiles.items():
            if params.get("is_local") is False and name not in chain:
                chain.append(name)

        # 3. Добавляем все локальные модели (кроме manual_bridge)
        for name, params in profiles.items():
            if params.get("is_local") is True and name not in chain:
                chain.append(name)

        # 4. В самом конце всегда manual_bridge
        if "manual_bridge" in self.instances and "manual_bridge" not in chain:
            chain.append("manual_bridge")

        return chain

    def generate_with_fallback(self, task_type: str, prompt: str, system_prompt: str = None) -> str:
        model_chain = self._build_fallback_chain(task_type)
        if not model_chain:
            return f"[Ошибка] Нет доступных моделей для задачи '{task_type}'."

        max_tokens = self.loop_settings.get("max_tokens_default", 4096)
        retries = self.loop_settings.get("retry_attempts", 2)
        delay = self.loop_settings.get("retry_delay_seconds", 2)

        last_error = ""

        for model_name in model_chain:
            if model_name not in self.instances:
                continue

            model = self.instances[model_name]

            # Если это ручной мост, возвращаем промпт
            if isinstance(model, ManualBridgeLLM):
                print("--> ВСЕ МОДЕЛИ ИСЧЕРПАНЫ. Переход на ручной мост.")
                return model.generate(prompt, system_prompt)

            print(f"--> Пробуем модель: {model_name}")

            result = model.generate(
                prompt, 
                system_prompt, 
                max_tokens=max_tokens, 
                retry_attempts=retries, 
                retry_delay=delay
            )

            # Проверяем на ошибки
            if result.startswith("[ERROR_") or result.startswith("[CRASH_"):
                print(f"--> Модель {model_name} упала: {result}")
                last_error = result
                continue # Идем к следующей модели

            return result # Успех!

        return f"[КРИТИЧЕСКАЯ ОШИБКА] Все модели исчерпаны. Последняя ошибка: {last_error}"
""",

    # Показываем, как легко подключить API в будущем (просто раскомментировав конфиг)
    "test_dynamic_routing.py": """\
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

    print("\\nЦепочка для задачи 'code_generation':")
    chain = registry._build_fallback_chain("code_generation")
    for i, m in enumerate(chain):
        print(f"  {i+1}. {m}")

    print("\\nЦепочка для задачи 'complex_reasoning':")
    chain2 = registry._build_fallback_chain("complex_reasoning")
    for i, m in enumerate(chain2):
        print(f"  {i+1}. {m}")

    print("\\n=== Имитация сбоя локальной модели ===")
    # Отправляем задачу. Если R1 (local_logic) жива, она ответит.
    # Если она упадет, роутер пойдет по цепочке дальше.
    response = registry.generate_with_fallback(
        "complex_reasoning", 
        "Скажи 'Привет, я работаю!' и укажи свою модель."
    )
    print("\\nОТВЕТ:\\n", response)

if __name__ == "__main__":
    main()
"""
}


def create_project():
    print(f"Применение патча {PROJECT_NAME}...")
    for filepath, content in FILES.items():
        clean_content = textwrap.dedent(content)
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(clean_content)
        print(f"  Обновлен: {filepath}")

    zip_name = f"{PROJECT_NAME}.zip"
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filepath in FILES.keys():
            zipf.write(filepath)
    print(f"\\nГотово! Архив {zip_name} создан.")


if __name__ == "__main__":
    create_project()