import importlib
import subprocess
import sys


# Map: pip_name -> import_name (иногда они не совпадают)
PACKAGE_MAP = {
    "customtkinter": "customtkinter",
    "python-docx": "docx",
    "openpyxl": "openpyxl",
    "PyMuPDF": "pymupdf",
    "pytesseract": "pytesseract",
    "Pillow": "PIL",
    "docxtpl": "docxtpl",
    "xlrd": "xlrd",
    "pandas": "pandas",
    "pywin32": "win32com",
    "chromadb": "chromadb",
    "sentence-transformers": "sentence_transformers",
    "lxml": "lxml",
    "ddgs": "ddgs",
    "xlsxwriter": "xlsxwriter",
    "requests": "requests",
    "pyyaml": "yaml",
}


def check_missing():
    # Возвращает список pip-имён отсутствующих пакетов.
    missing = []
    for pip_name, import_name in PACKAGE_MAP.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pip_name)
    return missing


def install_packages(packages):
    if not packages:
        return True
    print("[Зависимости] Устанавливаю: " + ", ".join(packages))
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + packages)
        print("[Зависимости] Установка завершена.")
        return True
    except subprocess.CalledProcessError as e:
        print("[Зависимости] Ошибка установки: " + str(e))
        return False


def check_and_report(auto_install=False):
    # Возвращает (missing_list, all_ok_bool).
    missing = check_missing()
    if not missing:
        print("[Зависимости] Все библиотеки на месте.")
        return [], True
    print("[Зависимости] Отсутствуют: " + ", ".join(missing))
    if auto_install:
        ok = install_packages(missing)
        return missing, ok
    return missing, False
