from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer
from documents.extractors import extract_pages


class RAGIndexer:
    def __init__(self, config, tools_config):
        self.rag_config = config.get('rag', {})
        self.tools_config = tools_config

        self.db_path = self.rag_config.get('db_path', 'chroma_db')
        self.collection_name = self.rag_config.get('collection_name', 'documents')
        self.chunk_size = self.rag_config.get('chunk_size', 1000)
        self.chunk_overlap = self.rag_config.get('chunk_overlap', 200)
        self.separators = self.rag_config.get('separators', ['\n\n', '\n', '. ', ' ', ''])

        print('Загрузка модели эмбеддингов (' + str(self.rag_config.get('embedding_model')) + ')...')
        self.embedder = SentenceTransformer(self.rag_config.get('embedding_model'))

        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.rag_config.get('embedding_model')
            )
        )

    def _recursive_split(self, text, separators, chunk_size, chunk_overlap):
        final_chunks = []
        if len(text) <= chunk_size:
            return [text] if text.strip() else []
        if not separators:
            for i in range(0, len(text), chunk_size - chunk_overlap):
                final_chunks.append(text[i:i + chunk_size])
            return final_chunks
        sep = separators[0]
        next_seps = separators[1:]
        splits = list(text) if sep == '' else text.split(sep)
        current = []
        current_len = 0
        for split in splits:
            if len(split) > chunk_size:
                if current:
                    final_chunks.append(sep.join(current))
                    current = []
                    current_len = 0
                final_chunks.extend(self._recursive_split(split, next_seps, chunk_size, chunk_overlap))
                continue
            if current_len + len(split) + len(sep) > chunk_size:
                if current:
                    final_chunks.append(sep.join(current))
                overlap = []
                overlap_len = 0
                for prev in reversed(current):
                    if overlap_len + len(prev) > chunk_overlap:
                        break
                    overlap.insert(0, prev)
                    overlap_len += len(prev) + len(sep)
                current = overlap
                current_len = overlap_len
            current.append(split)
            current_len += len(split) + len(sep)
        if current:
            final_chunks.append(sep.join(current))
        return final_chunks

    def _chunk_text(self, text):
        return self._recursive_split(text, self.separators, self.chunk_size, self.chunk_overlap)

    def index_folder(self, folder_path):
        folder = Path(folder_path)
        supported = ['.txt', '.docx', '.doc', '.xlsx', '.xls', '.pdf', '.png', '.jpg', '.jpeg']
        all_files = [f for f in folder.rglob('*') if f.suffix.lower() in supported]
        files_to_index = []
        for f in all_files:
            if f.name.startswith('~$'):
                continue
            files_to_index.append(f)

        print('Найдено файлов: ' + str(len(files_to_index)))
        count = 0
        for f in files_to_index:
            print('Обработка: ' + f.name + '...')
            try:
                pages = extract_pages(str(f), self.tools_config)
            except Exception as e:
                print('  [Ошибка] ' + str(e))
                continue

            all_chunks = []
            all_metas = []
            all_ids = []
            chunk_idx = 0

            for page in pages:
                text = page['text']
                if text.startswith('[Ошибка'):
                    print('  [Ошибка страницы] ' + text[:100])
                    continue
                base_meta = page.get('meta', {}).copy()
                # Если в meta уже есть source (для сконвертированных файлов),
                # оставляем его. Иначе ставим реальный путь.
                if 'source' not in base_meta:
                    base_meta['source'] = str(f)
                base_meta['disk_path'] = str(f)
                chunks = self._chunk_text(text)
                for chunk in chunks:
                    meta = base_meta.copy()
                    meta['chunk_id'] = chunk_idx
                    all_chunks.append(chunk)
                    all_metas.append(meta)
                    all_ids.append(f.name + '_chunk_' + str(chunk_idx))
                    chunk_idx += 1

            if not all_chunks:
                continue

            try:
                self.collection.delete(where={'source': str(f)})
            except Exception:
                pass

            self.collection.add(
                documents=all_chunks,
                metadatas=all_metas,
                ids=all_ids
            )
            count += 1

        print('✅ Индексация завершена. Файлов: ' + str(count))
        return count

    def search(self, query, top_k=4, where=None):
        kwargs = {'query_texts': [query], 'n_results': top_k}
        if where:
            kwargs['where'] = where
        try:
            results = self.collection.query(**kwargs)
        except Exception as e:
            print('  [RAG] where-фильтр не сработал: ' + str(e))
            results = self.collection.query(query_texts=[query], n_results=top_k)

        found = []
        if results['documents']:
            for i in range(len(results['documents'][0])):
                meta = results['metadatas'][0][i]
                found.append({
                    'text': results['documents'][0][i],
                    'source': meta.get('source', 'unknown'),
                    'chunk_id': meta.get('chunk_id', 0),
                    'meta': meta
                })
        return found

