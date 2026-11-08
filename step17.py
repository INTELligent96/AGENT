import os


NL = "\n"


# ============ Новый legacy.py ============
LEGACY_PY = NL.join([
    "import os",
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
    "def convert_legacy_ms_office(file_path):",
    "    if not COM_AVAILABLE:",
    "        raise LegacyConversionError('pywin32 не установлен. Установи: pip install pywin32')",
    "",
    "    file_path = Path(file_path).absolute()",
    "    ext = file_path.suffix.lower()",
    "",
    "    if ext not in ['.doc', '.xls']:",
    "        return str(file_path)",
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
    "                new_path = str(file_path.with_suffix('.docx'))",
    "                doc.SaveAs2(new_path, FileFormat=16)",
    "                doc.Close(False)",
    "                doc = None",
    "                return new_path",
    "            finally:",
    "                if doc is not None:",
    "                    try:",
    "                        doc.Close(False)",
    "                    except Exception:",
    "                        pass",
    "                if word is not None:",
    "                    try:",
    "                        word.Quit()",
    "                    except Exception:",
    "                        pass",
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
    "                new_path = str(file_path.with_suffix('.xlsx'))",
    "                wb.SaveAs(new_path, FileFormat=51)",
    "                wb.Close(False)",
    "                wb = None",
    "                return new_path",
    "            finally:",
    "                if wb is not None:",
    "                    try:",
    "                        wb.Close(False)",
    "                    except Exception:",
    "                        pass",
    "                if excel is not None:",
    "                    try:",
    "                        excel.Quit()",
    "                    except Exception:",
    "                        pass",
    "    except Exception as e:",
    "        raise LegacyConversionError(str(e))",
    "    finally:",
    "        _uninit_com()",
    "",
])


# ============ Патч extractors.py ============
OLD_IMPORT = "from .legacy import convert_legacy_ms_office"
NEW_IMPORT = NL.join([
    "from .legacy import convert_legacy_ms_office, LegacyConversionError, COM_AVAILABLE",
])

OLD_LEGACY_BLOCK = NL.join([
    "    if ext in ['.doc', '.xls']:",
    "        if tools_config.get(\"use_ms_office\"):",
    "            file_path = convert_legacy_ms_office(file_path)",
    "            ext = Path(file_path).suffix.lower()",
    "        else:",
    "            return f\"[Ошибка] Для файлов {ext} требуется MS Office.\"",
])

NEW_LEGACY_BLOCK = NL.join([
    "    if ext in ['.doc', '.xls']:",
    "        if not tools_config.get(\"use_ms_office\"):",
    "            return f\"[Ошибка] Для файлов {ext} требуется MS Office (use_ms_office: true в config.yaml).\"",
    "        if not COM_AVAILABLE:",
    "            return f\"[Ошибка] pywin32 не установлен. Установи: pip install pywin32\"",
    "        try:",
    "            new_path = convert_legacy_ms_office(file_path)",
    "            file_path = new_path",
    "            ext = Path(file_path).suffix.lower()",
    "            print('  [Legacy] Сконвертировано: ' + file_path)",
    "        except LegacyConversionError as e:",
    "            return f\"[Ошибка конвертации {ext}]: {e}\"",
    "        except Exception as e:",
    "            return f\"[Неожиданная ошибка конвертации {ext}]: {e}\"",
])


# ============ Заменить функцию extract_text целиком ============
NEW_EXTRACT_TEXT = NL.join([
    "def extract_text(file_path: str, tools_config: dict) -> str:",
    "    ext = Path(file_path).suffix.lower()",
    "",
    "    if ext in ['.doc', '.xls']:",
    "        if not tools_config.get(\"use_ms_office\"):",
    "            return f\"[Ошибка] Для файлов {ext} требуется MS Office (use_ms_office: true в config.yaml).\"",
    "        if not COM_AVAILABLE:",
    "            return f\"[Ошибка] pywin32 не установлен. Установи: pip install pywin32\"",
    "        try:",
    "            new_path = convert_legacy_ms_office(file_path)",
    "            file_path = new_path",
    "            ext = Path(file_path).suffix.lower()",
    "            print('  [Legacy] Сконвертировано: ' + file_path)",
    "        except LegacyConversionError as e:",
    "            return f\"[Ошибка конвертации {ext}]: {e}\"",
    "        except Exception as e:",
    "            return f\"[Неожиданная ошибка конвертации {ext}]: {e}\"",
    "",
    "    if ext == '.txt':",
    "        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:",
    "            return f.read()",
    "    elif ext == '.docx':",
    "        return extract_docx(file_path)",
    "    elif ext == '.xlsx':",
    "        return extract_excel(file_path)",
    "    elif ext == '.pdf':",
    "        return extract_pdf(file_path, tools_config)",
    "    elif ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']:",
    "        return extract_image(file_path, tools_config)",
    "    else:",
    "        return f\"[Ошибка] Неподдерживаемый формат: {ext}\"",
    "",
])


def replace_extract_text(content):
    import re
    pattern = re.compile(
        r"def extract_text\(file_path: str, tools_config: dict\) -> str:.*?(?=\n\ndef |\Z)",
        re.DOTALL,
    )
    m = pattern.search(content)
    if not m:
        return content, False
    return content[:m.start()] + NEW_EXTRACT_TEXT + content[m.end():], True


def main():
    print("=== 1. Перезапись documents/legacy.py ===")
    with open("documents/legacy.py", "w", encoding="utf-8") as f:
        f.write(LEGACY_PY + NL)
    print("[OK] documents/legacy.py перезаписан (с CoInitialize)")

    print("")
    print("=== 2. Патч documents/extractors.py ===")
    path = "documents/extractors.py"
    if not os.path.exists(path):
        print("[SKIP] нет файла")
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 2.1 Импорт
    if OLD_IMPORT in content:
        content = content.replace(OLD_IMPORT, NEW_IMPORT, 1)
        print("[OK] импорт обновлён")

    # 2.2 Блок легаси внутри extract_text
    if OLD_LEGACY_BLOCK in content:
        content = content.replace(OLD_LEGACY_BLOCK, NEW_LEGACY_BLOCK, 1)
        print("[OK] блок legacy обновлён")

    # 2.3 Заменить extract_text целиком (если блок не сработал)
    content, ok = replace_extract_text(content)
    if ok:
        print("[OK] extract_text перезаписан целиком")
    else:
        print("[WARN] extract_text не найден")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print("")
    print("=" * 60)
    print("Готово! Перезапусти агент: python main.py")
    print("=" * 60)
    print("")
    print("Что изменилось:")
    print("- convert_legacy_ms_office теперь вызывает pythoncom.CoInitialize()")
    print("- Использует DispatchEx вместо Dispatch (отдельный процесс Word/Excel)")
    print("- Открывает файлы ReadOnly=True (безопасно)")
    print("- При ошибке возвращает ЯВНУЮ ошибку, а не исходный .doc")
    print("- Освобождает COM-объекты в finally")
    print("")
    print("Теперь .doc и .xls должны нормально конвертироваться, даже в фоновом потоке.")


if __name__ == "__main__":
    main()