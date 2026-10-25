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
        self.separators = self.rag_config.get("separators", ["\n\n", "\n", ". ", " ", ""])

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
        final_chunks = []
        if len(text) <= chunk_size:
            return [text] if text.strip() else []

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
            if split_len > chunk_size:
                if current_chunk:
                    final_chunks.append(separator.join(current_chunk))
                    current_chunk = []
                    current_length = 0
                sub_chunks = self._recursive_split(split, next_separators, chunk_size, chunk_overlap)
                final_chunks.extend(sub_chunks)
                continue

            if current_length + split_len + len(separator) > chunk_size:
                if current_chunk:
                    final_chunks.append(separator.join(current_chunk))

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

            # ИСПРАВЛЕНИЕ: Удаляем старые чанки этого файла, чтобы не было дублей и старых метаданных
            try:
                self.collection.delete(where={"source": str(file_path)})
            except Exception:
                pass # Если база пустая, игнорируем

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
                # ИСПРАВЛЕНИЕ: Безопасное чтение метаданных через .get()
                meta = results['metadatas'][0][i]
                found_chunks.append({
                    "text": results['documents'][0][i],
                    "source": meta.get('source', 'unknown'),
                    "chunk_id": meta.get('page_chunk', 'unknown')
                })
        return found_chunks
