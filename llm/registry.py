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
        """Динамически строит цепочку из всех доступных моделей."""
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
