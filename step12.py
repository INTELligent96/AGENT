import os


FILES = {}

FILES["requirements.txt"] = "\n".join([
    "# AI Document Agent PRO - полный список зависимостей",
    "# Установка: pip install -r requirements.txt",
    "",
    "customtkinter>=5.2.0",
    "python-docx>=1.1.0",
    "openpyxl>=3.1.0",
    "PyMuPDF>=1.23.0",
    "pytesseract>=0.3.10",
    "Pillow>=10.0.0",
    "docxtpl>=0.16.0",
    "xlrd>=2.0.0",
    "pandas>=2.0.0",
    "pywin32>=306",
    "chromadb>=0.4.0",
    "sentence-transformers>=2.2.0",
    "lxml>=4.9.0",
    "ddgs>=0.1.0",
    "xlsxwriter>=3.1.0",
    "requests>=2.28.0",
    "pyyaml>=6.0",
    "",
])

FILES["tools/requirements_checker.py"] = "\n".join([
    "import importlib",
    "import subprocess",
    "import sys",
    "",
    "",
    "# Map: pip_name -> import_name (иногда они не совпадают)",
    "PACKAGE_MAP = {",
    '    "customtkinter": "customtkinter",',
    '    "python-docx": "docx",',
    '    "openpyxl": "openpyxl",',
    '    "PyMuPDF": "pymupdf",',
    '    "pytesseract": "pytesseract",',
    '    "Pillow": "PIL",',
    '    "docxtpl": "docxtpl",',
    '    "xlrd": "xlrd",',
    '    "pandas": "pandas",',
    '    "pywin32": "win32com",',
    '    "chromadb": "chromadb",',
    '    "sentence-transformers": "sentence_transformers",',
    '    "lxml": "lxml",',
    '    "ddgs": "ddgs",',
    '    "xlsxwriter": "xlsxwriter",',
    '    "requests": "requests",',
    '    "pyyaml": "yaml",',
    "}",
    "",
    "",
    "def check_missing():",
    "    # Возвращает список pip-имён отсутствующих пакетов.",
    "    missing = []",
    "    for pip_name, import_name in PACKAGE_MAP.items():",
    "        try:",
    "            importlib.import_module(import_name)",
    "        except ImportError:",
    "            missing.append(pip_name)",
    "    return missing",
    "",
    "",
    "def install_packages(packages):",
    "    if not packages:",
    "        return True",
    '    print("[Зависимости] Устанавливаю: " + ", ".join(packages))',
    "    try:",
    '        subprocess.check_call([sys.executable, "-m", "pip", "install"] + packages)',
    '        print("[Зависимости] Установка завершена.")',
    "        return True",
    "    except subprocess.CalledProcessError as e:",
    '        print("[Зависимости] Ошибка установки: " + str(e))',
    "        return False",
    "",
    "",
    "def check_and_report(auto_install=False):",
    "    # Возвращает (missing_list, all_ok_bool).",
    "    missing = check_missing()",
    "    if not missing:",
    '        print("[Зависимости] Все библиотеки на месте.")',
    "        return [], True",
    '    print("[Зависимости] Отсутствуют: " + ", ".join(missing))',
    "    if auto_install:",
    "        ok = install_packages(missing)",
    "        return missing, ok",
    "    return missing, False",
    "",
])

FILES["main.py"] = "\n".join([
    "import customtkinter as ctk",
    "import yaml",
    "from tkinter import messagebox",
    "",
    "",
    "def startup_check():",
    "    # Проверяет зависимости ДО запуска GUI, чтобы избежать непонятных ошибок.",
    "    try:",
    "        with open(\"config.yaml\", \"r\", encoding=\"utf-8\") as f:",
    "            cfg = yaml.safe_load(f) or {}",
    "    except Exception:",
    "        return",
    "    startup = cfg.get(\"startup\", {})",
    "    if not startup.get(\"check_dependencies\", True):",
    "        return",
    "",
    "    from tools.requirements_checker import check_and_report, install_packages",
    "    auto = startup.get(\"auto_install\", False)",
    "    missing, ok = check_and_report(auto_install=auto)",
    "    if missing and not ok:",
    "        msg = \"Не хватает библиотек:\\n\\n\" + \"\\n\".join(missing)",
    "        msg += \"\\n\\nУстановить их сейчас? (потребуется интернет)\"",
    "        answer = messagebox.askyesno(\"Отсутствуют зависимости\", msg)",
    "        if answer:",
    "            install_packages(missing)",
    "",
    "",
    "if __name__ == \"__main__\":",
    "    startup_check()",
    "    ctk.set_appearance_mode(\"Dark\")",
    "    ctk.set_default_color_theme(\"blue\")",
    "    from gui.app import AgentApp",
    "    app = AgentApp()",
    "    app.mainloop()",
    "",
])

STARTUP_BLOCK = "\n".join([
    "",
    "# Проверка зависимостей при старте",
    "startup:",
    "  check_dependencies: true",
    "  auto_install: false   # true - ставит библиотеки без вопросов",
    "",
])


def main():
    for path, content in FILES.items():
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("[OK] " + path)

    # Добавляем блок startup в config.yaml, если его там нет
    if os.path.exists("config.yaml"):
        with open("config.yaml", "r", encoding="utf-8") as f:
            cfg_content = f.read()
        if "startup:" not in cfg_content:
            with open("config.yaml", "a", encoding="utf-8") as f:
                f.write(STARTUP_BLOCK)
            print("[OK] config.yaml - добавлен блок startup")
        else:
            print("[SKIP] config.yaml - блок startup уже есть")

    print("")
    print("Готово! Запускай: python main.py")
    print("При старте увидишь строку [Зависимости] ...")


if __name__ == "__main__":
    main()