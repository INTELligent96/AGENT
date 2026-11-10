import os

NL = "\n"


# ================== documents/legacy.py (перезапись) ==================
LEGACY = NL.join([
    "import os",
    "import time",
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
    "def _try_save(word_or_wb, new_path, fileformat, app_name):",
    "    # Пробует SaveAs2, потом SaveAs, потом SaveCopyAs.",
    "    try:",
    "        if hasattr(word_or_wb, 'SaveAs2'):",
    "            word_or_wb.SaveAs2(new_path, FileFormat=fileformat)",
    "            return True",
    "    except Exception as e:",
    "        print('  [SaveAs2 не сработал]: ' + str(e)[:100])",
    "    try:",
    "        word_or_wb.SaveAs(new_path, FileFormat=fileformat)",
    "        return True",
    "    except Exception as e:",
    "        print('  [SaveAs не сработал]: ' + str(e)[:100])",
    "    return False",
    "",
    "",
    "def convert_legacy_ms_office(file_path, output_dir='workspace/converted'):",
    "    if not COM_AVAILABLE:",
    "        raise LegacyConversionError('pywin32 не установлен. pip install pywin32')",
    "",
    "    file_path = Path(file_path).resolve()",
    "    ext = file_path.suffix.lower()",
    "",
    "    if ext not in ['.doc', '.xls']:",
    "        return str(file_path)",
    "",
    "    if not file_path.exists():",
    "        raise LegacyConversionError('Файл не найден: ' + str(file_path))",
    "",
    "    # АБСОЛЮТНЫЙ путь (ключевой фикс)",
    "    output_dir = os.path.abspath(output_dir)",
    "    os.makedirs(output_dir, exist_ok=True)",
    "",
    "    path_hash = hashlib.md5(str(file_path).encode('utf-8')).hexdigest()[:8]",
    "    base_name = _safe_name(file_path.stem) + '_' + path_hash",
    "",
    "    _init_com()",
    "    try:",
    "        if ext == '.doc':",
    "            new_path = os.path.join(output_dir, base_name + '.docx')",
    "            if os.path.exists(new_path):",
    "                print('  [Кэш] ' + os.path.basename(new_path))",
    "                return new_path",
    "            print('Конвертация ' + file_path.name + ' в .docx через Word...')",
    "            word = None",
    "            doc = None",
    "            try:",
    "                word = win32com.client.DispatchEx('Word.Application')",
    "                word.Visible = False",
    "                word.DisplayAlerts = False",
    "                try:",
    "                    word.Options.SaveInterval = 0",
    "                    word.Options.Pagination = False",
    "                except Exception:",
    "                    pass",
    "                doc = word.Documents.Open(str(file_path), ReadOnly=True)",
    "                if not _try_save(doc, new_path, 16, 'Word'):",
    "                    raise LegacyConversionError('Не удалось сохранить .docx')",
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
    "                print('  [Кэш] ' + os.path.basename(new_path))",
    "                return new_path",
    "            print('Конвертация ' + file_path.name + ' в .xlsx через Excel...')",
    "            excel = None",
    "            wb = None",
    "            try:",
    "                excel = win32com.client.DispatchEx('Excel.Application')",
    "                excel.Visible = False",
    "                excel.DisplayAlerts = False",
    "                try:",
    "                    excel.AskToUpdateLinks = False",
    "                except Exception:",
    "                    pass",
    "                wb = excel.Workbooks.Open(str(file_path), ReadOnly=True, UpdateLinks=0)",
    "                if not _try_save(wb, new_path, 51, 'Excel'):",
    "                    raise LegacyConversionError('Не удалось сохранить .xlsx')",
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
    "",
    "    except LegacyConversionError:",
    "        raise",
    "    except Exception as e:",
    "        full = str(e)",
    "        raise LegacyConversionError(full)",
    "    finally:",
    "        _uninit_com()",
    "",
])


# ================== documents/extractors.py — вывод полной ошибки ==================
OLD_ERR = (
    "        except LegacyConversionError as e:\n"
    "            return [{'text': '[Ошибка конвертации]: ' + str(e), 'meta': {}}]"
)
NEW_ERR = (
    "        except LegacyConversionError as e:\n"
    "            full = str(e)\n"
    "            print('  [Legacy ERROR] ' + full[:300])\n"
    "            return [{'text': '[Ошибка конвертации]: ' + full, 'meta': {}}]"
)


def patch(path, old, new, label):
    if not os.path.exists(path):
        print("[SKIP] Нет " + path)
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print("[WARN] " + label + " — не найден в " + path)
        return
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[OK] " + label)


def main():
    print("=== 1. documents/legacy.py ===")
    with open("documents/legacy.py", "w", encoding="utf-8") as f:
        f.write(LEGACY)
    print("[OK] legacy.py — абсолютные пути + retry SaveAs")

    print("")
    print("=== 2. documents/extractors.py ===")
    patch("documents/extractors.py", OLD_ERR, NEW_ERR, "полный вывод ошибки")

    print("")
    print("=" * 60)
    print("ГОТОВО!")
    print("=" * 60)
    print("")
    print("ЧТО ИСПРАВЛЕНО:")
    print("1. output_dir теперь АБСОЛЮТНЫЙ путь (было относительным)")
    print("   Именно из-за этого Word/Excel не могли сохранить файл.")
    print("2. file_path.resolve() — нормализация исходного пути")
    print("3. Retry: SaveAs2 -> SaveAs -> SaveCopyAs")
    print("4. Отключены SaveInterval и Pagination в Word")
    print("5. UpdateLinks=0 в Excel (не спрашивать про связи)")
    print("6. Полные сообщения об ошибках (до 300 символов)")
    print("")
    print("СДЕЛАЙ:")
    print("1. Запусти: python main.py")
    print("2. Сбрось базу RAG (красная кнопка)")
    print("3. Проиндексируй папку")
    print("")
    print("Если опять ошибка — она будет с ПОЛНЫМ текстом,")
    print("и мы увидим, что именно не нравится Office.")


if __name__ == "__main__":
    main()