import os

NL = "\n"


# ================== documents/legacy.py (перезапись) ==================
LEGACY = NL.join([
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
    "def _safe_name(stem):",
    "    safe = ''.join(c for c in stem if c.isalnum() or c in ' ._-')",
    "    safe = safe.strip().strip('.')",
    "    return safe[:60] if safe else 'file'",
    "",
    "",
    "def convert_legacy_ms_office(file_path, output_dir='workspace/converted'):",
    "    # Конвертирует .doc в .docx и .xls в .xlsx через MS Office.",
    "    # Сохраняет в output_dir (отдельная папка), а не рядом с оригиналом.",
    "    if not COM_AVAILABLE:",
    "        raise LegacyConversionError('pywin32 не установлен. Установи: pip install pywin32')",
    "",
    "    file_path = Path(file_path).absolute()",
    "    ext = file_path.suffix.lower()",
    "",
    "    if ext not in ['.doc', '.xls']:",
    "        return str(file_path)",
    "",
    "    os.makedirs(output_dir, exist_ok=True)",
    "",
    "    # Уникальное имя: имя + короткий хеш от полного пути",
    "    path_hash = hashlib.md5(str(file_path).encode('utf-8')).hexdigest()[:8]",
    "    base_name = _safe_name(file_path.stem) + '_' + path_hash",
    "",
    "    _init_com()",
    "    try:",
    "        if ext == '.doc':",
    "            new_path = os.path.join(output_dir, base_name + '.docx')",
    "            if os.path.exists(new_path):",
    "                print('  [Кэш] Уже сконвертировано: ' + os.path.basename(new_path))",
    "                return new_path",
    "            print('Конвертация ' + file_path.name + ' в .docx через Word...')",
    "            word = None",
    "            doc = None",
    "            try:",
    "                word = win32com.client.DispatchEx('Word.Application')",
    "                word.Visible = False",
    "                word.DisplayAlerts = False",
    "                doc = word.Documents.Open(str(file_path), ReadOnly=True)",
    "                doc.SaveAs2(new_path, FileFormat=16)",
    "                doc.Close(False)",
    "                doc = None",
    "                return new_path",
    "            finally:",
    "                if doc is not None:",
    "                    try: doc.Close(False)",
    "                    except Exception: pass",
    "                if word is not None:",
    "                    try: word.Quit()",
    "                    except Exception: pass",
    "",
    "        elif ext == '.xls':",
    "            new_path = os.path.join(output_dir, base_name + '.xlsx')",
    "            if os.path.exists(new_path):",
    "                print('  [Кэш] Уже сконвертировано: ' + os.path.basename(new_path))",
    "                return new_path",
    "            print('Конвертация ' + file_path.name + ' в .xlsx через Excel...')",
    "            excel = None",
    "            wb = None",
    "            try:",
    "                excel = win32com.client.DispatchEx('Excel.Application')",
    "                excel.Visible = False",
    "                excel.DisplayAlerts = False",
    "                wb = excel.Workbooks.Open(str(file_path), ReadOnly=True)",
    "                wb.SaveAs(new_path, FileFormat=51)",
    "                wb.Close(False)",
    "                wb = None",
    "                return new_path",
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


# ================== documents/extractors.py — правим .doc блок ==================
OLD_DOC_BLOCK = NL.join([
    "    if ext in ['.doc', '.xls']:",
    "        if not tools_config.get('use_ms_office'):",
    "            return [{'text': '[Ошибка] Для ' + ext + ' нужен MS Office', 'meta': {}}]",
    "        if not COM_AVAILABLE:",
    "            return [{'text': '[Ошибка] pywin32 не установлен', 'meta': {}}]",
    "        try:",
    "            new_path = convert_legacy_ms_office(file_path)",
    "            print('  [Legacy] Сконвертировано: ' + new_path)",
    "            return extract_pages(new_path, tools_config)",
    "        except LegacyConversionError as e:",
    "            return [{'text': '[Ошибка конвертации]: ' + str(e), 'meta': {}}]",
])

NEW_DOC_BLOCK = NL.join([
    "    if ext in ['.doc', '.xls']:",
    "        if not tools_config.get('use_ms_office'):",
    "            return [{'text': '[Ошибка] Для ' + ext + ' нужен MS Office', 'meta': {}}]",
    "        if not COM_AVAILABLE:",
    "            return [{'text': '[Ошибка] pywin32 не установлен', 'meta': {}}]",
    "        orig_path = str(file_path)",
    "        try:",
    "            new_path = convert_legacy_ms_office(file_path)",
    "            print('  [Legacy] Сконвертировано: ' + new_path)",
    "            pages = extract_pages(new_path, tools_config)",
    "            for p in pages:",
    "                p['meta']['source'] = orig_path",
    "                p['meta']['original_filename'] = Path(orig_path).name",
    "                p['meta']['converted_from'] = ext",
    "            return pages",
    "        except LegacyConversionError as e:",
    "            return [{'text': '[Ошибка конвертации]: ' + str(e), 'meta': {}}]",
])


# ================== rag/indexer.py — убираем пропуск .doc/.xls ==================
OLD_SKIP = NL.join([
    "        files_to_index = []",
    "        for f in all_files:",
    "            if f.suffix.lower() == '.doc' and f.with_suffix('.docx').exists():",
    "                print('  [Skip] ' + f.name + ' (есть .docx)')",
    "                continue",
    "            if f.suffix.lower() == '.xls' and f.with_suffix('.xlsx').exists():",
    "                print('  [Skip] ' + f.name + ' (есть .xlsx)')",
    "                continue",
    "            if f.name.startswith('~$'):",
    "                continue",
    "            files_to_index.append(f)",
])
NEW_SKIP = NL.join([
    "        files_to_index = []",
    "        for f in all_files:",
    "            if f.name.startswith('~$'):",
    "                continue",
    "            files_to_index.append(f)",
])


# ================== rag/indexer.py — source берём из meta, если задан ==================
OLD_META = NL.join([
    "                base_meta = page.get('meta', {}).copy()",
    "                base_meta['source'] = str(f)",
])
NEW_META = NL.join([
    "                base_meta = page.get('meta', {}).copy()",
    "                # Если в meta уже есть source (для сконвертированных файлов),",
    "                # оставляем его. Иначе ставим реальный путь.",
    "                if 'source' not in base_meta:",
    "                    base_meta['source'] = str(f)",
    "                base_meta['disk_path'] = str(f)",
])


# ================== rag/qa.py — показываем пометку для сконвертированных ==================
OLD_FORMAT_LINE = NL.join([
    "    def _format_source_line(self, i, chunk):",
    "        src = Path(chunk['source']).name",
    "        meta = chunk.get('meta', {})",
    "        extra = []",
    "        if 'page' in meta:",
    "            extra.append('стр. ' + str(meta['page']))",
    "        if 'section' in meta:",
    "            extra.append('раздел: «' + meta['section'] + '»')",
    "        if 'sheet' in meta:",
    "            extra.append('лист: «' + meta['sheet'] + '»')",
    "        header = str(i) + '. ' + src",
    "        if extra:",
    "            header += ' (' + ', '.join(extra) + ')'",
    "        header += ' [часть ' + str(chunk['chunk_id']) + ']'",
    "        preview = chunk['text'][:120].replace('\\n', ' ').strip()",
    "        return header + ': «' + preview + '...»'",
])
NEW_FORMAT_LINE = NL.join([
    "    def _format_source_line(self, i, chunk):",
    "        meta = chunk.get('meta', {})",
    "        src = meta.get('original_filename') or Path(chunk['source']).name",
    "        extra = []",
    "        if meta.get('converted_from'):",
    "            extra.append('сконвертирован из ' + meta['converted_from'])",
    "        if 'page' in meta:",
    "            extra.append('стр. ' + str(meta['page']))",
    "        if 'section' in meta:",
    "            extra.append('раздел: «' + meta['section'] + '»')",
    "        if 'sheet' in meta:",
    "            extra.append('лист: «' + meta['sheet'] + '»')",
    "        header = str(i) + '. ' + src",
    "        if extra:",
    "            header += ' (' + ', '.join(extra) + ')'",
    "        header += ' [часть ' + str(chunk['chunk_id']) + ']'",
    "        preview = chunk['text'][:120].replace('\\n', ' ').strip()",
    "        return header + ': «' + preview + '...»'",
])


def patch(path, old, new, label):
    if not os.path.exists(path):
        print("[SKIP] Нет " + path)
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print("[WARN] " + label + " — фрагмент не найден в " + path)
        return
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[OK] " + label)


def main():
    # 1. legacy.py — перезапись
    print("=== 1. documents/legacy.py ===")
    with open("documents/legacy.py", "w", encoding="utf-8") as f:
        f.write(LEGACY)
    print("[OK] legacy.py — конвертация в workspace/converted/")

    # 2. extractors.py — правка блока .doc/.xls
    print("")
    print("=== 2. documents/extractors.py ===")
    patch("documents/extractors.py", OLD_DOC_BLOCK, NEW_DOC_BLOCK, "extract_pages: source=orig")

    # 3. indexer.py — убираем skip .doc/.xls
    print("")
    print("=== 3. rag/indexer.py ===")
    patch("rag/indexer.py", OLD_SKIP, NEW_SKIP, "indexer: без skip .doc/.xls")
    patch("rag/indexer.py", OLD_META, NEW_META, "indexer: source из meta")

    # 4. qa.py — форматирование с пометкой
    print("")
    print("=== 4. rag/qa.py ===")
    patch("rag/qa.py", OLD_FORMAT_LINE, NEW_FORMAT_LINE, "qa: 'сконвертирован из .doc'")

    print("")
    print("=" * 60)
    print("ГОТОВО!")
    print("=" * 60)
    print("")
    print("ЧТО ИЗМЕНИЛОСЬ:")
    print("1. .doc/.xls НИКОГДА не пропускаются — даже если есть .docx/.xlsx.")
    print("2. Сконвертированные файлы идут в workspace/converted/ (не в исходную папку).")
    print("3. Уникальное имя по хешу пути — нет конфликтов при одинаковых именах.")
    print("4. Кэш: если уже сконвертировано — не конвертируется заново.")
    print("5. В источниках: 'Книга X.doc (сконвертирован из .doc, стр. 5)'")
    print("")
    print("ВАЖНО ПЕРЕД ЗАПУСКОМ:")
    print("1. Удали старые .docx/.xlsx, если они были сконвертированы ранее в исходной папке")
    print("   (те, что ты сам не создавал). Иначе они проиндексируются как отдельные файлы.")
    print("2. 'Сбросить базу RAG' — обязательно.")
    print("3. Заново проиндексируй папку.")


if __name__ == "__main__":
    main()