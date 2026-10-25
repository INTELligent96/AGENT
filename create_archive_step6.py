import os
import zipfile
import textwrap

PROJECT_NAME = "agent_rag_foundation"

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

# НОВЫЙ БЛОК RAG
rag:
  db_path: "chroma_db"                 # Папка для базы данных
  collection_name: "documents"
  chunk_size: 1000                     # Размер кусочка текста (символов)
  chunk_overlap: 200                   # Перекрытие между кусочками
  embedding_model: "paraphrase-multilingual-MiniLM-L12-v2" # Хорошая модель для RU/EN
""",

    "rag/__init__.py": "",

    "rag/indexer.py": """\
import os
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer
from documents.extractors import extract_text

class RAGIndexer:
    def __init__(self, config: dict, tools_config: dict):
        self.rag_config = config.get("rag", {})
        self.tools_config = tools_config

        self.db_path = self.rag_config.get("db_path", "chroma_db")
        self.collection_name = self.rag_config.get("collection_name", "documents")
        self.chunk_size = self.rag_config.get("chunk_size", 1000)
        self.chunk_overlap = self.rag_config.get("chunk_overlap", 200)

        print(f"Загрузка модели эмбеддингов ({self.rag_config.get('embedding_model')})...")
        self.embedder = SentenceTransformer(self.rag_config.get("embedding_model"))

        self.client = chromadb.PersistentClient(path=self.db_path)
        # Используем встроенную функцию эмбеддингов от sentence-transformers
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.rag_config.get("embedding_model")
            )
        )

    def _chunk_text(self, text: str) -> list[str]:
        \"\"\"Разбивает текст на пересекающиеся кусочки.\"\"\"
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start += self.chunk_size - self.chunk_overlap
        return chunks

    def index_folder(self, folder_path: str):
        \"\"\"Индексирует все поддерживаемые файлы в папке.\"\"\"
        folder = Path(folder_path)
        supported_exts = ['.txt', '.docx', '.doc', '.xlsx', '.xls', '.pdf', '.png', '.jpg', '.jpeg']

        files_to_index = [f for f in folder.rglob('*') if f.suffix.lower() in supported_exts]
        print(f"Найдено файлов для индексации: {len(files_to_index)}")

        doc_id_counter = 0
        for file_path in files_to_index:
            print(f"Обработка: {file_path.name}...")
            text = extract_text(str(file_path), self.tools_config)

            if text.startswith("[Ошибка]"):
                print(f"  Пропуск (ошибка чтения): {text}")
                continue

            chunks = self._chunk_text(text)
            if not chunks:
                continue

            ids = [f"{file_path.name}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{"source": str(file_path)} for _ in chunks]

            # Добавляем в базу пакетами, чтобы не вешать память
            self.collection.add(
                documents=chunks,
                metadatas=metadatas,
                ids=ids
            )
            doc_id_counter += 1

        print(f"✅ Индексация завершена! Обработано документов: {doc_id_counter}")
        return doc_id_counter

    def search(self, query: str, top_k: int = 4) -> list[dict]:
        \"\"\"Ищет самые релевантные кусочки текста по запросу.\"\"\"
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )

        found_chunks = []
        if results['documents']:
            for i in range(len(results['documents'][0])):
                found_chunks.append({
                    "text": results['documents'][0][i],
                    "source": results['metadatas'][0][i]['source']
                })
        return found_chunks
""",

    "rag/qa.py": """\
from .indexer import RAGIndexer
from llm.registry import LLMRegistry

class RAGQuestionAnswerer:
    def __init__(self, config: dict, tools_config: dict, registry: LLMRegistry):
        self.indexer = RAGIndexer(config, tools_config)
        self.registry = registry

    def ask(self, question: str) -> str:
        \"\"\"Ищет контекст и генерирует ответ через LLM.\"\"\"
        print(f"Поиск по базе для вопроса: '{question}'...")
        context_chunks = self.indexer.search(question, top_k=4)

        if not context_chunks:
            return "В базе данных не найдено информации по этому вопросу."

        # Формируем контекст для LLM
        context_text = ""
        for i, chunk in enumerate(context_chunks, 1):
            source = Path(chunk['source']).name if hasattr(chunk, 'source') else chunk['source']
            context_text += f"--- Фрагмент {i} (Источник: {source}) ---\\n"
            context_text += chunk['text'] + "\\n\\n"

        system_prompt = (
            "Ты — ассистент по работе с документами. Отвечай на вопрос пользователя, "
            "ОПИРАЯСЬ ТОЛЬКО на предоставленные фрагменты текста. "
            "Если в тексте нет ответа, честно скажи, что не знаешь. "
            "Обязательно указывай, из какого файла взята информация."
        )

        user_prompt = f"КОНТЕКСТ:\\n{context_text}\\n\\nВОПРОС: {question}"

        print("Генерация ответа (local_logic)...")
        llm = self.registry.get_model_for_task("complex_reasoning") # DeepSeek R1 8B
        return llm.generate(prompt=user_prompt, system_prompt=system_prompt)
""",

    # Добавляем методы RAG в агента
    "core/agent.py": """\
import os
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
        self._rag = None # Ленивая инициализация RAG

    @property
    def rag(self):
        if self._rag is None:
            self._rag = RAGQuestionAnswerer(self.config, self.tools, self.registry)
        return self._rag

    def index_folder(self, folder_path: str):
        \"\"\"Индексирует папку для RAG.\"\"\"
        return self.rag.indexer.index_folder(folder_path)

    def ask_question(self, question: str) -> str:
        \"\"\"Отвечает на вопрос по базе документов.\"\"\"
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
        llm = self.registry.get_model_for_task("code_generation")
        current_prompt = CODE_PROMPT.format(task=task)

        last_generated_code = ""
        start_time = time.time()

        for iteration in range(1, self.max_iterations + 1):
            if self._stop_requested:
                return f"--- РАБОТА ПРЕРВАНА ---\\n\\n{last_generated_code}"

            elapsed_time = time.time() - start_time
            if elapsed_time > self.task_timeout:
                return f"--- ПРЕВЫШЕН ЛИМИТ ВРЕМЕНИ ---\\n\\n{last_generated_code}"

            print(f"--- Попытка {iteration} ---")
            code = llm.generate(current_prompt)
            last_generated_code = code

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
        llm = self.registry.get_model_for_task("default_model")
        return llm.generate(SUMMARIZE_PROMPT.format(text=text[:8000]))

    def check_spelling_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        llm = self.registry.get_model_for_task("default_model")
        return llm.generate(SPELLCHECK_PROMPT.format(text=text[:8000]))

    def structure_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        llm = self.registry.get_model_for_task("complex_reasoning")
        return llm.generate(STRUCTURE_PROMPT.format(text=text[:8000]))

    def save_text_to_word(self, text: str, output_path: str):
        create_simple_docx(text, output_path)
        return output_path
""",

    "test_rag.py": """\
import os
from core.agent import Agent

def main():
    # Создадим тестовую папку с документами
    test_dir = "test_rag_folder"
    os.makedirs(test_dir, exist_ok=True)

    # Создадим пару файлов
    with open(os.path.join(test_dir, "doc1.txt"), "w", encoding="utf-8") as f:
        f.write("Компания Рога и Копыта была основана в 1995 году в городе Москва. "
                "Основной вид деятельности - продажа рогов и копыт. "
                "Генеральный директор - Иван Иванович Петров.")

    with open(os.path.join(test_dir, "doc2.txt"), "w", encoding="utf-8") as f:
        f.write("Филиал компании Рога и Копыта находится в Санкт-Петербурге. "
                "Адрес: Невский проспект, дом 10. "
                "Контактный телефон: 8-800-555-35-35.")

    print("Инициализация агента...")
    agent = Agent("config.yaml")

    print("\\n=== ТЕСТ 1: Индексация папки ===")
    agent.index_folder(test_dir)

    print("\\n=== ТЕСТ 2: Вопрос по документам ===")
    questions = [
        "В каком году основана компания Рога и Копыта?",
        "Какой телефон у филиала в Санкт-Петербурге?",
        "Кто генеральный директор?"
    ]

    for q in questions:
        print(f"\\n--- ВОПРОС: {q} ---")
        answer = agent.ask_question(q)
        print(f"ОТВЕТ:\\n{answer}")

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
        print(f"  Создан/обновлен: {filepath}")

    zip_name = f"{PROJECT_NAME}.zip"
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filepath in FILES.keys():
            zipf.write(filepath)
    print(f"\\nГотово! Архив {zip_name} создан.")


if __name__ == "__main__":
    create_project()
