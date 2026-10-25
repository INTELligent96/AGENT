import os
import zipfile
import textwrap

PROJECT_NAME = "agent_resilient_router"

FILES = {
    "config.yaml": """\
llm_profiles:
  local_coder:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen-qwen2.5-coder-14b-instruct"
  local_logic:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "deepseek-r1-0528-qwen3-8b-abliterated"
  local_fast:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen2.5-7b-instruct-uncensored"

  # Ручной мост (финальный fallback)
  manual_bridge:
    type: "manual_bridge"

# НОВЫЙ ФОРМАТ: Цепочки моделей (каскадный перебор)
routing:
  default_model: 
    - "local_fast"
    - "local_logic"
    - "manual_bridge"

  code_generation: 
    - "local_coder"
    - "local_logic"
    - "local_fast"
    - "manual_bridge"

  complex_reasoning: 
    - "local_logic"
    - "local_fast"
    - "local_coder"
    - "manual_bridge"

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
  max_tokens_default: 4096         # Стартовое значение токенов
  retry_attempts: 2                # Сколько раз пробуем ОДНУ модель
  retry_delay_seconds: 2           # Пауза между попытками

rag:
  db_path: "chroma_db"
  collection_name: "documents"
  chunk_size: 1000
  chunk_overlap: 200
  embedding_model: "paraphrase-multilingual-MiniLM-L12-v2"
  separators: ["\\n\\n", "\\n", ". ", "! ", "? ", " ", ""]
""",

    # Базовый класс обновлен, добавили проверку на ManualBridge
    "llm/base.py": """\
from abc import ABC, abstractmethod
from typing import Optional

class BaseLLM(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        pass
""",

    # Умный API-клиент с динамическим уменьшением токенов
    "llm/openai_compat.py": """\
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
""",

    "llm/manual_bridge.py": """\
from .base import BaseLLM
from typing import Optional

class ManualBridgeLLM(BaseLLM):
    def __init__(self):
        self.pending_prompt = None

    def generate(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        full_prompt = ""
        if system_prompt:
            full_prompt += f"СИСТЕМНАЯ ИНСТРУКЦИЯ:\\n{system_prompt}\\n\\n"
        full_prompt += f"ЗАДАЧА:\\n{prompt}"

        self.pending_prompt = full_prompt
        return (
            "\\n[ВНИМАНИЕ: ВСЕ ЛОКАЛЬНЫЕ МОДЕЛИ НЕДОСТУПНЫ ИЛИ УПАЛИ]\\n"
            "Пожалуйста, скопируйте текст ниже в DeepSeek/Qwen через браузер, "
            "а полученный ответ вставьте обратно в систему.\\n\\n"
            f"--- НАЧАЛО ПРОМПТА ---\\n{full_prompt}\\n--- КОНЕЦ ПРОМПТА ---"
        )
""",

    # Главный дирижер - Отказоустойчивый роутер
    "llm/registry.py": """\
import yaml
import os
import time
from typing import Dict, Any, List
from .openai_compat import OpenAICompatLLM
from .manual_bridge import ManualBridgeLLM
from .base import BaseLLM

class LLMRegistry:
    def __init__(self, config_path: str = "config.yaml"):
        self.instances: Dict[str, BaseLLM] = {}
        self.routing: Dict[str, List[str]] = {}
        self.loop_settings = {}
        self.load_config(config_path)

    def load_config(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        self.loop_settings = config.get("agent_loop", {})

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

    def generate_with_fallback(self, task_type: str, prompt: str, system_prompt: str = None) -> str:
        \"\"\"Главный метод: перебирает модели, пока какая-нибудь не ответит.\"\"\"
        model_chain = self.routing.get(task_type, [])
        if not model_chain:
            return f"[Ошибка] Для задачи '{task_type}' не задана цепочка моделей."

        max_tokens = self.loop_settings.get("max_tokens_default", 4096)
        retries = self.loop_settings.get("retry_attempts", 2)
        delay = self.loop_settings.get("retry_delay_seconds", 2)

        last_error = ""

        for model_name in model_chain:
            if model_name not in self.instances:
                continue

            model = self.instances[model_name]
            print(f"--> Попытка использовать модель: {model_name}")

            # Если это ручной мост, сразу возвращаем промпт (он не делает запросов)
            if isinstance(model, ManualBridgeLLM):
                print("--> Переход на ручной мост (все модели исчерпаны).")
                return model.generate(prompt, system_prompt)

            # Вызываем API с настройками retry
            result = model.generate(
                prompt, 
                system_prompt, 
                max_tokens=max_tokens, 
                retry_attempts=retries, 
                retry_delay=delay
            )

            # Если ответ начинается с [ERROR_, значит модель окончательно упала
            if result.startswith("[ERROR_"):
                print(f"--> Модель {model_name} окончательно упала: {result}")
                last_error = result
                continue # Переходим к следующей модели в цепочке

            # Если ответ успешный - возвращаем его!
            return result

        # Если прошли весь цикл и ничего не вернули
        return f"[КРИТИЧЕСКАЯ ОШИБКА] Все модели в цепочке упали. Последняя ошибка: {last_error}"
""",

    # Агент теперь использует новый роутер
    "core/agent.py": """\
import os
import time
import yaml
from llm.registry import LLMRegistry
from documents.extractors import extract_text
from documents.writers import create_simple_docx
from core.prompts import SUMMARIZE_PROMPT, STRUCTURE_PROMPT, SPELLCHECK_PROMPT, CODE_PROMPT
from core.workspace import WorkspaceManager
from tools.validator import validate_python_code
from rag.qa import RAGQuestionAnswerer

class Agent:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.tools = self.config.get("tools", {})
        self.registry = LLMRegistry(config_path)

        safety = self.config.get("safety", {})
        self.workspace = WorkspaceManager(
            workspace_dir=safety.get("workspace_dir", "workspace"),
            read_only_originals=safety.get("read_only_originals", True)
        )

        agent_loop = self.config.get("agent_loop", {})
        self.max_iterations = agent_loop.get("max_iterations", 10)
        self.task_timeout = agent_loop.get("task_timeout_seconds", 600)
        self.code_timeout = agent_loop.get("code_execution_timeout", 15)

        self._stop_requested = False
        self._rag = None

    @property
    def rag(self):
        if self._rag is None:
            self._rag = RAGQuestionAnswerer(self.config, self.tools, self.registry)
        return self._rag

    def index_folder(self, folder_path: str):
        return self.rag.indexer.index_folder(folder_path)

    def ask_question(self, question: str) -> str:
        return self.rag.ask(question)

    def request_stop(self):
        self._stop_requested = True

    def reset_stop_flag(self):
        self._stop_requested = False

    def _read_safe(self, file_path: str) -> str:
        safe_path = self.workspace.prepare_file(file_path)
        return extract_text(safe_path, self.tools)

    def generate_code_with_validation(self, task: str) -> str:
        self.reset_stop_flag()
        print(f"Генерация кода (лимит: {self.max_iterations} попыток)...")

        current_prompt = CODE_PROMPT.format(task=task)
        last_generated_code = ""
        start_time = time.time()

        for iteration in range(1, self.max_iterations + 1):
            if self._stop_requested:
                return f"--- РАБОТА ПРЕРВАНА ---\\n\\n{last_generated_code}"

            if time.time() - start_time > self.task_timeout:
                return f"--- ПРЕВЫШЕН ЛИМИТ ВРЕМЕНИ ---\\n\\n{last_generated_code}"

            print(f"--- Попытка {iteration} ---")

            # Вызываем через Роутер!
            code = self.registry.generate_with_fallback("code_generation", current_prompt)
            last_generated_code = code

            # Если роутер вернул ошибку, нет смысла валидировать этот текст как код
            if code.startswith("[КРИТИЧЕСКАЯ ОШИБКА]") or code.startswith("[ВНИМАНИЕ:"):
                return code

            print("Валидация кода...")
            is_valid, error_msg = validate_python_code(code, timeout_sec=self.code_timeout)
            if is_valid:
                print("✅ Код прошел валидацию!")
                return code

            print(f"❌ Ошибка в коде: {error_msg}")
            current_prompt = (
                f"Твой предыдущий код выдал ошибку:\\n{error_msg}\\n\\n"
                f"Вот код:\\n{code}\\n\\n"
                f"Пожалуйста, исправь его и верни только чистый рабочий код. Задача: {task}"
            )
        return f"--- ДОСТИГНУТ ЛИМИТ ПОПЫТОК ---\\n\\n{last_generated_code}"

    def summarize_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        prompt = SUMMARIZE_PROMPT.format(text=text[:8000])
        return self.registry.generate_with_fallback("default_model", prompt)

    def check_spelling_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        prompt = SPELLCHECK_PROMPT.format(text=text[:8000])
        return self.registry.generate_with_fallback("default_model", prompt)

    def structure_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        prompt = STRUCTURE_PROMPT.format(text=text[:8000])
        return self.registry.generate_with_fallback("complex_reasoning", prompt)

    def save_text_to_word(self, text: str, output_path: str):
        create_simple_docx(text, output_path)
        return output_path
""",

    # RAG тоже использует роутер!
    "rag/qa.py": """\
from pathlib import Path
from .indexer import RAGIndexer
from llm.registry import LLMRegistry

class RAGQuestionAnswerer:
    def __init__(self, config: dict, tools_config: dict, registry: LLMRegistry):
        self.indexer = RAGIndexer(config, tools_config)
        self.registry = registry

    def ask(self, question: str) -> str:
        print(f"Поиск по базе для вопроса: '{question}'...")
        context_chunks = self.indexer.search(question, top_k=5)

        if not context_chunks:
            return "В базе данных не найдено информации по этому вопросу."

        context_text = ""
        for i, chunk in enumerate(context_chunks, 1):
            source = Path(chunk['source']).name
            context_text += f"--- Фрагмент {i} (Источник: {source}, часть {chunk['chunk_id']}) ---\\n"
            context_text += chunk['text'] + "\\n\\n"

        system_prompt = (
            "Ты — ассистент по работе с документами. Отвечай на вопрос пользователя, "
            "ОПИРАЯСЬ ТОЛЬКО на предоставленные фрагменты текста. "
            "Если в тексте нет ответа, честно скажи, что не знаешь. "
            "Обязательно указывай, из какого файла взята информация. "
            "Отвечай кратко и по делу."
        )

        user_prompt = f"КОНТЕКСТ:\\n{context_text}\\n\\nВОПРОС: {question}"

        print("Запуск отказоустойчивой генерации (complex_reasoning)...")
        return self.registry.generate_with_fallback("complex_reasoning", user_prompt, system_prompt)
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