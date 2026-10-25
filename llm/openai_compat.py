import requests
import time
from typing import Optional
from .base import BaseLLM

class OpenAICompatLLM(BaseLLM):
    def __init__(self, base_url: str, api_key: str, model_name: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        max_tokens = kwargs.get("max_tokens", 4096)
        attempts = kwargs.get("retry_attempts", 2)
        delay = kwargs.get("retry_delay", 2)

        for attempt in range(attempts):
            data = {
                "model": self.model_name,
                "messages": messages,
                "temperature": kwargs.get("temperature", 0.3),
                "max_tokens": max_tokens,
                "stream": False
            }

            try:
                response = requests.post(url, headers=headers, json=data, timeout=300)

                # Если ошибка, проверяем, не связана ли она с памятью/контекстом
                if response.status_code in [400, 500]:
                    err_text = response.text.lower()
                    if "memory" in err_text or "context" in err_text or "exceed" in err_text or response.status_code == 500:
                        print(f"  [Fallback] {self.model_name} упала. Уменьшаю токены ({max_tokens} -> {max_tokens//2})...")
                        max_tokens = max_tokens // 2
                        if max_tokens < 256: # Если совсем мало, дальше бесполезно
                            return "[ERROR_OOM] Модель не справляется с контекстом даже на малых токенах."
                        continue # Пробуем снова с меньшим количеством

                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]

            except requests.exceptions.RequestException as e:
                print(f"  [Retry {attempt+1}/{attempts}] Ошибка сети или сервера: {e}")
                if attempt < attempts - 1:
                    time.sleep(delay)
                else:
                    return f"[ERROR_NETWORK] Не удалось подключиться к {self.model_name}."

        return "[ERROR_UNKNOWN] Все попытки исчерпаны."
