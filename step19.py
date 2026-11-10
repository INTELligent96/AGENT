import os

NL = "\n"


# ============ 1. documents/legacy.py ============
LEGACY_PY = NL.join([
    "import os",
    "import hashlib",
    "from pathlib import Path",
    "",
    "try:",
    "    import win32com.client",
    "    import pythoncom",
    "    COM_AVAILABLE = True",
    "except ImportError:",
    "    COM_AVAILABLE = False",
    "",
    "",
    "class LegacyConversionError(Exception):",
    "    pass",
    "",
    "",
    "def _init_com():",
    "    if COM_AVAILABLE:",
    "        try:",
    "            pythoncom.CoInitialize()",
    "        except Exception:",
    "            pass",
    "",
    "",
    "def _uninit_com():",
    "    if COM_AVAILABLE:",
    "        try:",
    "            pythoncom.CoUninitialize()",
    "        except Exception:",
    "            pass",
    "",
    "",
    "def convert_legacy_ms_office(file_path, cache_dir='workspace/converted'):",
    "    if not COM_AVAILABLE:",
    "        raise LegacyConversionError('pywin32 не установлен. Установи: pip install pywin32')",
    "",
    "    file_path = Path(file_path).absolute()",
    "    ext = file_path.suffix.lower()",
    "",
    "    if ext not in ['.doc', '.xls']:",
    "        return str(file_path)",
    "",
    "    cache = Path(cache_dir)",
    "    cache.mkdir(parents=True, exist_ok=True)",
    "",
    "    target_ext = '.docx' if ext == '.doc' else '.xlsx'",
    "    h = hashlib.md5(str(file_path).encode('utf-8')).hexdigest()[:8]",
    "    cached = cache / (file_path.stem + '_' + h + target_ext)",
    "",
    "    if cached.exists() and cached.stat().st_mtime >= file_path.stat().st_mtime:",
    "        print('  [Legacy] Использую кэш: ' + str(cached))",
    "        return str(cached)",
    "",
    "    _init_com()",
    "    try:",
    "        if ext == '.doc':",
    "            print('Конвертация ' + file_path.name + ' в .docx через Word...')",
    "            word = None",
    "            doc = None",
    "            try:",
    "                word = win32com.client.DispatchEx('Word.Application')",
    "                word.Visible = False",
    "                word.DisplayAlerts = False",
    "                doc = word.Documents.Open(str(file_path), ReadOnly=True)",
    "                doc.SaveAs2(str(cached), FileFormat=16)",
    "                doc.Close(False)",
    "                doc = None",
    "                return str(cached)",
    "            finally:",
    "                if doc is not None:",
    "                    try: doc.Close(False)",
    "                    except Exception: pass",
    "                if word is not None:",
    "                    try: word.Quit()",
    "                    except Exception: pass",
    "",
    "        elif ext == '.xls':",
    "            print('Конвертация ' + file_path.name + ' в .xlsx через Excel...')",
    "            excel = None",
    "            wb = None",
    "            try:",
    "                excel = win32com.client.DispatchEx('Excel.Application')",
    "                excel.Visible = False",
    "                excel.DisplayAlerts = False",
    "                wb = excel.Workbooks.Open(str(file_path), ReadOnly=True)",
    "                wb.SaveAs(str(cached), FileFormat=51)",
    "                wb.Close(False)",
    "                wb = None",
    "                return str(cached)",
    "            finally:",
    "                if wb is not None:",
    "                    try: wb.Close(False)",
    "                    except Exception: pass",
    "                if excel is not None:",
    "                    try: excel.Quit()",
    "                    except Exception: pass",
    "    except Exception as e:",
    "        raise LegacyConversionError(str(e))",
    "    finally:",
    "        _uninit_com()",
    "",
])


# ============ 2. documents/extractors.py — новый extract_excel ============
NEW_EXCEL = NL.join([
    "def extract_excel(file_path: str) -> str:",
    "    wb = openpyxl.load_workbook(file_path, data_only=True)",
    "    text = []",
    "    for sheet in wb.sheetnames:",
    "        text.append('[Лист: ' + sheet + ']')",
    "        ws = wb[sheet]",
    "        for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):",
    "            row_str = ' | '.join(str(cell) if cell is not None else '' for cell in row)",
    "            if row_str.strip():",
    "                text.append('[Стр. ' + str(row_idx) + '] ' + row_str)",
    "    return '\\n'.join(text)",
    "",
])


# ============ 3. rag/indexer.py — полностью новый ============
INDEXER_PY = NL.join([
    "import os",
    "import re",
    "import hashlib",
    "from pathlib import Path",
    "import chromadb",
    "from sentence_transformers import SentenceTransformer",
    "from documents.extractors import extract_text",
    "",
    "",
    "class RAGIndexer:",
    "    def __init__(self, config: dict, tools_config: dict):",
    "        self.rag_config = config.get('rag', {})",
    "        self.tools_config = tools_config",
    "",
    "        self.db_path = self.rag_config.get('db_path', 'chroma_db')",
    "        self.collection_name = self.rag_config.get('collection_name', 'documents')",
    "        self.chunk_size = self.rag_config.get('chunk_size', 1000)",
    "        self.chunk_overlap = self.rag_config.get('chunk_overlap', 200)",
    "        self.separators = self.rag_config.get('separators', ['\\n\\n', '\\n', '. ', ' ', ''])",
    "",
    "        print('Загрузка модели эмбеддингов (' + str(self.rag_config.get('embedding_model')) + ')...')",
    "        self.embedder = SentenceTransformer(self.rag_config.get('embedding_model'))",
    "",
    "        self.client = chromadb.PersistentClient(path=self.db_path)",
    "        self.collection = self.client.get_or_create_collection(",
    "            name=self.collection_name,",
    "            embedding_function=chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction(",
    "                model_name=self.rag_config.get('embedding_model')",
    "            )",
    "        )",
    "",
    "    def _recursive_split(self, text, separators, chunk_size, chunk_overlap):",
    "        final_chunks = []",
    "        if len(text) <= chunk_size:",
    "            return [text] if text.strip() else []",
    "",
    "        if not separators:",
    "            for i in range(0, len(text), chunk_size - chunk_overlap):",
    "                final_chunks.append(text[i:i + chunk_size])",
    "            return final_chunks",
    "",
    "        sep = separators[0]",
    "        next_seps = separators[1:]",
    "        splits = list(text) if sep == '' else text.split(sep)",
    "",
    "        current = []",
    "        current_len = 0",
    "        for s in splits:",
    "            s_len = len(s)",
    "            if s_len > chunk_size:",
    "                if current:",
    "                    final_chunks.append(sep.join(current))",
    "                    current = []",
    "                    current_len = 0",
    "                final_chunks.extend(self._recursive_split(s, next_seps, chunk_size, chunk_overlap))",
    "                continue",
    "            if current_len + s_len + len(sep) > chunk_size:",
    "                if current:",
    "                    final_chunks.append(sep.join(current))",
    "                overlap_chunk = []",
    "                overlap_len = 0",
    "                for prev in reversed(current):",
    "                    if overlap_len + len(prev) > chunk_overlap:",
    "                        break",
    "                    overlap_chunk.insert(0, prev)",
    "                    overlap_len += len(prev) + len(sep)",
    "                current = overlap_chunk",
    "                current_len = overlap_len",
    "            current.append(s)",
    "            current_len += s_len + len(sep)",
    "        if current:",
    "            final_chunks.append(sep.join(current))",
    "        return final_chunks",
    "",
    "    def _chunk_text(self, text):",
    "        return self._recursive_split(text, self.separators, self.chunk_size, self.chunk_overlap)",
    "",
    "    def _extract_chunk_meta(self, chunk_text, last_pos):",
    "        page = last_pos.get('page')",
    "        section = last_pos.get('section')",
    "        sheet = last_pos.get('sheet')",
    "",
    "        pages = re.findall(r'\\[Стр\\. (\\d+)\\]', chunk_text)",
    "        if pages:",
    "            page = int(pages[-1])",
    "        sections = re.findall(r'\\[Раздел: ([^\\]]+)\\]', chunk_text)",
    "        if sections:",
    "            section = sections[-1]",
    "        sheets = re.findall(r'\\[Лист: ([^\\]]+)\\]', chunk_text)",
    "        if sheets:",
    "            sheet = sheets[-1]",
    "",
    "        return {'page': page, 'section': section, 'sheet': sheet}",
    "",
    "    def index_folder(self, folder_path):",
    "        folder = Path(folder_path)",
    "        supported = ['.txt', '.docx', '.doc', '.xlsx', '.xls', '.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.csv']",
    "",
    "        all_files = [f for f in folder.rglob('*') if f.suffix.lower() in supported]",
    "        files_to_index = []",
    "        for f in all_files:",
    "            ext = f.suffix.lower()",
    "            if ext == '.doc' and f.with_suffix('.docx').exists():",
    "                print('  [Skip] ' + f.name + ' (есть .docx)')",
    "                continue",
    "            if ext == '.xls' and f.with_suffix('.xlsx').exists():",
    "                print('  [Skip] ' + f.name + ' (есть .xlsx)')",
    "                continue",
    "            files_to_index.append(f)",
    "",
    "        print('Найдено файлов для индексации: ' + str(len(files_to_index)))",
    "        doc_id_counter = 0",
    "",
    "        for file_path in files_to_index:",
    "            ext_lower = file_path.suffix.lower()",
    "            is_converted = ext_lower in ['.doc', '.xls']",
    "            original_source = str(file_path)",
    "",
    "            print('Обработка: ' + file_path.name + '...')",
    "            try:",
    "                text = extract_text(str(file_path), self.tools_config)",
    "            except Exception as e:",
    "                print('  Пропуск (ошибка чтения): ' + str(e))",
    "                continue",
    "",
    "            if text.startswith('[Ошибка'):",
    "                print('  Пропуск: ' + text[:100])",
    "                continue",
    "",
    "            chunks = self._chunk_text(text)",
    "            if not chunks:",
    "                continue",
    "",
    "            try:",
    "                self.collection.delete(where={'source': str(file_path)})",
    "            except Exception:",
    "                pass",
    "",
    "            file_hash = hashlib.md5(str(file_path).encode('utf-8')).hexdigest()[:8]",
    "            ids = [file_path.name + '_' + file_hash + '_chunk_' + str(i) for i in range(len(chunks))]",
    "",
    "            current_pos = {'page': None, 'section': None, 'sheet': None}",
    "            metadatas = []",
    "            for i, chunk in enumerate(chunks):",
    "                current_pos = self._extract_chunk_meta(chunk, current_pos)",
    "                metadatas.append({",
    "                    'source': str(file_path),",
    "                    'original_source': original_source,",
    "                    'is_converted': is_converted,",
    "                    'page_chunk': i,",
    "                    'page': current_pos['page'],",
    "                    'section': current_pos['section'],",
    "                    'sheet': current_pos['sheet'],",
    "                })",
    "",
    "            try:",
    "                self.collection.add(documents=chunks, metadatas=metadatas, ids=ids)",
    "                doc_id_counter += 1",
    "            except Exception as e:",
    "                print('  Ошибка добавления в Chroma: ' + str(e))",
    "",
    "        print('Индексация завершена. Обработано документов: ' + str(doc_id_counter))",
    "        return doc_id_counter",
    "",
    "    def search(self, query, top_k=4, where=None):",
    "        kwargs = {'query_texts': [query], 'n_results': top_k}",
    "        if where:",
    "            kwargs['where'] = where",
    "        try:",
    "            results = self.collection.query(**kwargs)",
    "        except Exception as e:",
    "            print('  [RAG] where-фильтр не сработал: ' + str(e))",
    "            results = self.collection.query(query_texts=[query], n_results=top_k)",
    "",
    "        found = []",
    "        if results['documents']:",
    "            for i in range(len(results['documents'][0])):",
    "                meta = results['metadatas'][0][i]",
    "                found.append({",
    "                    'text': results['documents'][0][i],",
    "                    'source': meta.get('source', 'unknown'),",
    "                    'chunk_id': meta.get('page_chunk', 'unknown'),",
    "                    'original_source': meta.get('original_source', meta.get('source', 'unknown')),",
    "                    'is_converted': meta.get('is_converted', False),",
    "                    'page': meta.get('page'),",
    "                    'section': meta.get('section'),",
    "                    'sheet': meta.get('sheet'),",
    "                })",
    "        return found",
    "",
])


# ============ 4. rag/qa.py — обновление блока источников ============
# Возьмём текущий файл и заменим только блок источников

OLD_SOURCES_BLOCK = NL.join([
    "        # Блок \"Использованные источники\" - программно, без участия LLM",
    "        sources = '\\n\\n' + '=' * 50 + '\\nИСПОЛЬЗОВАННЫЕ ИСТОЧНИКИ:\\n'",
    "        for i, chunk in enumerate(context_chunks, 1):",
    "            src = Path(chunk['source']).name",
    "            preview = chunk['text'][:120].replace('\\n', ' ').strip()",
    "            sources += str(i) + '. ' + src + ' (часть ' + str(chunk['chunk_id']) + '): «' + preview + '...»\\n'",
    "        return answer + sources",
])

NEW_SOURCES_BLOCK = NL.join([
    "        # Блок \"Использованные источники\" - программно, без участия LLM",
    "        sources = '\\n\\n' + '=' * 50 + '\\nИСПОЛЬЗОВАННЫЕ ИСТОЧНИКИ:\\n'",
    "        for i, chunk in enumerate(context_chunks, 1):",
    "            src = Path(chunk['source']).name",
    "            meta_parts = []",
    "            if chunk.get('page'):",
    "                meta_parts.append('Стр. ' + str(chunk['page']))",
    "            if chunk.get('section'):",
    "                meta_parts.append('Раздел: ' + str(chunk['section']))",
    "            if chunk.get('sheet'):",
    "                meta_parts.append('Лист: ' + str(chunk['sheet']))",
    "            if chunk.get('is_converted'):",
    "                orig_ext = Path(chunk.get('original_source', '')).suffix.upper()",
    "                if orig_ext:",
    "                    meta_parts.append('конвертировано из ' + orig_ext)",
    "            meta_str = (', ' + ', '.join(meta_parts)) if meta_parts else ''",
    "            preview = chunk['text'][:120].replace('\\n', ' ').strip()",
    "            sources += str(i) + '. ' + src + ' (часть ' + str(chunk['chunk_id']) + meta_str + '): «' + preview + '...»\\n'",
    "        return answer + sources",
])


def main():
    # 1. legacy.py
    print("=== 1. documents/legacy.py ===")
    with open("documents/legacy.py", "w", encoding="utf-8") as f:
        f.write(LEGACY_PY + NL)
    print("[OK] legacy.py перезаписан (кэш в workspace/converted/)")

    # 2. extractors.py — extract_excel
    print("")
    print("=== 2. documents/extractors.py ===")
    with open("documents/extractors.py", "r", encoding="utf-8") as f:
        content = f.read()
    import re as _re
    pattern = _re.compile(r"def extract_excel\(file_path: str\) -> str:.*?(?=\n\ndef |\Z)", _re.DOTALL)
    m = pattern.search(content)
    if m:
        content = content[:m.start()] + NEW_EXCEL + content[m.end():]
        with open("documents/extractors.py", "w", encoding="utf-8") as f:
            f.write(content)
        print("[OK] extract_excel: [Лист: ...] + [Стр. N]")
    else:
        print("[WARN] extract_excel не найден")

    # 3. indexer.py — полная замена
    print("")
    print("=== 3. rag/indexer.py ===")
    with open("rag/indexer.py", "w", encoding="utf-8") as f:
        f.write(INDEXER_PY + NL)
    print("[OK] indexer.py перезаписан (page/section/sheet + original_source/is_converted)")

    # 4. qa.py — блок источников
    print("")
    print("=== 4. rag/qa.py ===")
    with open("rag/qa.py", "r", encoding="utf-8") as f:
        content = f.read()
    if OLD_SOURCES_BLOCK in content:
        content = content.replace(OLD_SOURCES_BLOCK, NEW_SOURCES_BLOCK, 1)
        with open("rag/qa.py", "w", encoding="utf-8") as f:
            f.write(content)
        print("[OK] блок источников обновлён (страницы/разделы/листы)")
    else:
        print("[WARN] блок источников не найден — старая версия qa.py")
        print("       Скажи мне, перезапишу qa.py целиком")

    print("")
    print("=" * 60)
    print("ГОТОВО! Что сделать сейчас:")
    print("=" * 60)
    print("1. Запусти python main.py")
    print("2. Нажми 'Сбросить базу RAG' (красная кнопка)")
    print("   ВАЖНО: старые чанки НЕ СОВМЕСТИМЫ (нет новых полей)")
    print("3. Заново проиндексируй папку")
    print("4. Задай вопрос — увидишь в источниках:")
    print("   Книга_9-11.docx (часть 71, Раздел: Контроль качества)")
    print("   Сводный отчет.pdf (часть 33, Стр. 41)")
    print("   Приложение.xlsx (часть 5, Лист: Запасы)")
    print("   Книга.doc (часть 12, конвертировано из .DOC)")


if __name__ == "__main__":
    main()