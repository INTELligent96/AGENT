import os
import zipfile
import textwrap

PROJECT_NAME = "agent_rag_smart_chunking"

FILES = {
    # Обновляем конфиг (добавили настройки разделителей)
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

rag:
  db_path: "chroma_db"
  collection_name: "documents"
  chunk_size: 1000                     # Желаемый размер
  chunk_overlap: 200                   # Перекрытие
  embedding_model: "paraphrase-multilingual-MiniLM-L12-v2"
  # Иерархия разделителей: от крупных структур к мелким
  separators: ["\\n\\n", "\\n", ". ", "! ", "? ", " ", ""]
""",

    "rag/__init__.py": "",

    # НОВЫЙ УМНЫЙ ИНДЕКСАТОР
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
        self.separators = self.rag_config.get("separators", ["\\n\\n", "\\n", ". ", " ", ""])

        print(f"Загрузка модели эмбеддингов ({self.rag_config.get('embedding_model')})...")
        self.embedder = SentenceTransformer(self.rag_config.get("embedding_model"))

        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.rag_config.get("embedding_model")
            )
        )

    def _recursive_split(self, text: str, separators: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
        \"\"\"Умный рекурсивный сплиттер, который не рвет предложения и абзацы.\"\"\"
        final_chunks = []

        # Базовый случай: текст уже меньше нужного размера
        if len(text) <= chunk_size:
            return [text] if text.strip() else []

        # Если разделителей больше нет, режем принудительно по символам
        if not separators:
            for i in range(0, len(text), chunk_size - chunk_overlap):
                final_chunks.append(text[i:i + chunk_size])
            return final_chunks

        separator = separators[0]
        next_separators = separators[1:]

        if separator == "":
            splits = list(text)
        else:
            splits = text.split(separator)

        current_chunk = []
        current_length = 0

        for split in splits:
            split_len = len(split)

            # Если один кусок больше chunk_size, рекурсивно дробим его дальше
            if split_len > chunk_size:
                if current_chunk:
                    final_chunks.append(separator.join(current_chunk))
                    current_chunk = []
                    current_length = 0

                sub_chunks = self._recursive_split(split, next_separators, chunk_size, chunk_overlap)
                final_chunks.extend(sub_chunks)
                continue

            # Если добавление куска превышает лимит, закрываем текущий чанк
            if current_length + split_len + len(separator) > chunk_size:
                if current_chunk:
                    final_chunks.append(separator.join(current_chunk))

                # Формируем перекрытие (берем конец предыдущего чанка)
                overlap_chunk = []
                overlap_len = 0
                for prev_split in reversed(current_chunk):
                    if overlap_len + len(prev_split) > chunk_overlap:
                        break
                    overlap_chunk.insert(0, prev_split)
                    overlap_len += len(prev_split) + len(separator)

                current_chunk = overlap_chunk
                current_length = overlap_len

            current_chunk.append(split)
            current_length += split_len + len(separator)

        if current_chunk:
            final_chunks.append(separator.join(current_chunk))

        return final_chunks

    def _chunk_text(self, text: str) -> list[str]:
        \"\"\"Обертка для умного чанкинга.\"\"\"
        return self._recursive_split(text, self.separators, self.chunk_size, self.chunk_overlap)

    def index_folder(self, folder_path: str):
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

            # Формируем ID для базы
            ids = [f"{file_path.name}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{"source": str(file_path), "page_chunk": i} for i in range(len(chunks))]

            self.collection.add(
                documents=chunks,
                metadatas=metadatas,
                ids=ids
            )
            doc_id_counter += 1

        print(f"✅ Индексация завершена! Обработано документов: {doc_id_counter}")
        return doc_id_counter

    def search(self, query: str, top_k: int = 4) -> list[dict]:
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )

        found_chunks = []
        if results['documents']:
            for i in range(len(results['documents'][0])):
                found_chunks.append({
                    "text": results['documents'][0][i],
                    "source": results['metadatas'][0][i]['source'],
                    "chunk_id": results['metadatas'][0][i]['page_chunk']
                })
        return found_chunks
""",

    # Обновленный qa.py, чтобы в ответе указывал номер чанка (косвенно - место в книге)
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
        context_chunks = self.indexer.search(question, top_k=5) # Увеличили до 5 для лучшего контекста

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
            "Обязательно указывай, из какого файла и какой части (фрагмента) взята информация."
        )

        user_prompt = f"КОНТЕКСТ:\\n{context_text}\\n\\nВОПРОС: {question}"

        print("Генерация ответа (local_logic)...")
        llm = self.registry.get_model_for_task("complex_reasoning")
        return llm.generate(prompt=user_prompt, system_prompt=system_prompt)
""",

    "test_rag.py": """\
import os
from core.agent import Agent

def main():
    test_dir = "test_rag_folder"
    os.makedirs(test_dir, exist_ok=True)

    # Создадим файл с абзацами, чтобы проверить чанкинг
    with open(os.path.join(test_dir, "book_chapter.txt"), "w", encoding="utf-8") as f:
        f.write("ГЛАВА 1. НАЧАЛО.\\n\\n"
                "Это был темный и штормовой вечер. Ветер завывал за окном, а дождь барабанил по крыше. "
                "Никто не ожидал, что именно сегодня произойдет нечто важное.\\n\\n"
                "Главный герой, Иван, сидел у камина и читал книгу. Он не подозревал, что судьба готовит ему испытание.\\n\\n"
                "ГЛАВА 2. ПОВОРОТ.\\n\\n"
                "Внезапно в дверь постучали. Иван оторвался от книги и пошел открывать. "
                "На пороге стоял незнакомец в черном плаще.\\n\\n"
                "Незнакомец сказал: 'Иван, у нас мало времени. Нам нужно поговорить о твоем прошлом.'")

    print("Инициализация агента...")
    agent = Agent("config.yaml")

    print("\\n=== ТЕСТ: Умная индексация ===")
    agent.index_folder(test_dir)

    print("\\n=== ТЕСТ: Вопрос по книге ===")
    q = "Что сказал незнакомец в черном плаще?"
    print(f"--- ВОПРОС: {q} ---")
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