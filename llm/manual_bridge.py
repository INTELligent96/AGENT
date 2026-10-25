from .base import BaseLLM
from typing import Optional

class ManualBridgeLLM(BaseLLM):
    def __init__(self):
        self.pending_prompt = None

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        full_prompt = ""
        if system_prompt:
            full_prompt += f"СИСТЕМНАЯ ИНСТРУКЦИЯ:\n{system_prompt}\n\n"
        full_prompt += f"ЗАДАЧА:\n{prompt}"

        self.pending_prompt = full_prompt
        return (
            "\n[ВНИМАНИЕ: ВСЕ ЛОКАЛЬНЫЕ МОДЕЛИ НЕДОСТУПНЫ ИЛИ УПАЛИ]\n"
            "Пожалуйста, скопируйте текст ниже в DeepSeek/Qwen через браузер, "
            "а полученный ответ вставьте обратно в систему.\n\n"
            f"--- НАЧАЛО ПРОМПТА ---\n{full_prompt}\n--- КОНЕЦ ПРОМПТА ---"
        )
