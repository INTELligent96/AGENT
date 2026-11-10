import os
import re


NL = "\n"


# ============ 1. documents/extractors.py ============
# Добавляем страницы (PDF) и разделы (DOCX)
NEW_PDF = NL.join([
    "def extract_pdf(file_path: str, tools_config: dict) -> str:",
    "    doc = fitz.open(file_path)",
    "    text = []",
    "    for i, page in enumerate(doc):",
    "        page_text = page.get_text()",
    "        if page_text.strip():",
    "            text.append('[Стр. ' + str(i + 1) + '] ' + page_text)",
    "        else:",
    "            pix = page.get_pixmap()",
    "            img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)",
    "            text.append('[Стр. ' + str(i + 1) + '] ' + ocr_image(img, tools_config))",
    "    return '\\n'.join(text)",
    "",
])

NEW_DOCX = NL.join([
    "def extract_docx(file_path: str) -> str:",
    "    doc = Document(file_path)",
    "    text = []",
    "    current_section = 'Начало'",
    "    for para in doc.paragraphs:",
    "        # Отслеживаем заголовки",
    "        try:",
    "            style_name = para.style.name.lower() if para.style else ''",
    "            if 'heading' in style_name or 'заголовок' in style_name:",
    "                if para.text.strip():",
    "                    current_section = para.text.strip()",
    "        except Exception:",
    "            pass",
    "        if para.text.strip():",
    "            text.append('[Раздел: ' + current_section + '] ' + para.text)",
    "    for table in doc.tables:",
    "        for row in table.rows:",
    "            row_text = ' | '.join(cell.text for cell in row.cells)",
    "            if row_text.strip():",
    "                text.append(row_text)",
    "    return '\\n'.join(text)",
    "",
])


def replace_function(content, func_name, new_body):
    pattern = re.compile(
        r"def " + re.escape(func_name) + r"\([^)]*\):.*?(?=\n\ndef |\Z)",
        re.DOTALL,
    )
    m = pattern.search(content)
    if not m:
        return content, False
    return content[:m.start()] + new_body + content[m.end():], True


# ============ 2. rag/indexer.py ============
# Дедупликация .doc, если есть .docx
OLD_FILES = (
    "        files_to_index = [f for f in folder.rglob('*') if f.suffix.lower() in supported_exts]"
)
NEW_FILES = NL.join([
    "        all_files = [f for f in folder.rglob('*') if f.suffix.lower() in supported_exts]",
    "        files_to_index = []",
    "        for f in all_files:",
    "            if f.suffix.lower() == '.doc':",
    "                if f.with_suffix('.docx').exists():",
    "                    print('  [Skip] ' + f.name + ' (есть .docx версия)')",
    "                    continue",
    "            files_to_index.append(f)",
])


# ============ 3. core/agent.py ============
# 1. Сохраняем первоначальный вопрос в pending_query
# 2. При восстановлении из pending — склеиваем вопрос и путь
# 3. Передаём оригинальный вопрос в ask_about_folder

# 3.1 __init__
OLD_INIT = (
    "        self.pending_tool = None   # инструмент, ожидающий аргумент (папка/файл)"
)
NEW_INIT = (
    "        self.pending_tool = None   # инструмент, ожидающий аргумент (папка/файл)\n"
    "        self.pending_query = None  # исходный вопрос пользователя"
)

# 3.2 _try_resolve_pending — возвращаем ask_about_folder(исходный_вопрос + путь)
OLD_RESOLVE = NL.join([
    "        self.pending_tool = None",
    "        log('[Диалог] Использую введённый путь: ' + arg)",
    "",
    "        try:",
    "            if tool == 'make_file_list':",
])
NEW_RESOLVE = NL.join([
    "        self.pending_tool = None",
    "        original_q = getattr(self, 'pending_query', '') or ''",
    "        self.pending_query = None",
    "        log('[Диалог] Использую введённый путь: ' + arg)",
    "",
    "        try:",
    "            if tool == 'make_file_list':",
])

# 3.3 Восстановление для ask_about_folder
OLD_RESOLVE_FOLDER = NL.join([
    "            if tool == 'ask_about_folder':",
    "                return self.ask_about_folder(arg)",
])
NEW_RESOLVE_FOLDER = NL.join([
    "            if tool == 'ask_about_folder':",
    "                combined = original_q + ' ' + arg if original_q else arg",
    "                return self.ask_about_folder(combined)",
])

# 3.4 Сохраняем pending_query при запросе папки (все инструменты)
OLD_BATCH = (
    "            if not f:\n"
    "                self.pending_tool = 'batch_summarize'\n"
)
NEW_BATCH = (
    "            if not f:\n"
    "                self.pending_tool = 'batch_summarize'\n"
    "                self.pending_query = user_text\n"
)

OLD_CLASSIFY = (
    "            if not f:\n"
    "                self.pending_tool = 'classify_files'\n"
)
NEW_CLASSIFY = (
    "            if not f:\n"
    "                self.pending_tool = 'classify_files'\n"
    "                self.pending_query = user_text\n"
)

OLD_LIST = (
    "            if not f:\n"
    "                self.pending_tool = 'make_file_list'\n"
)
NEW_LIST = (
    "            if not f:\n"
    "                self.pending_tool = 'make_file_list'\n"
    "                self.pending_query = user_text\n"
)

OLD_SPELL = (
    "            if not fp:\n"
    "                self.pending_tool = 'check_spelling'\n"
)
NEW_SPELL = (
    "            if not fp:\n"
    "                self.pending_tool = 'check_spelling'\n"
    "                self.pending_query = user_text\n"
)

OLD_SUMMARIZE = (
    "            if not fp:\n"
    "                self.pending_tool = 'summarize_file'\n"
)
NEW_SUMMARIZE = (
    "            if not fp:\n"
    "                self.pending_tool = 'summarize_file'\n"
    "                self.pending_query = user_text\n"
)

# 3.5 Для ask_about_folder тоже сохраняем
OLD_ASK_TOOL = NL.join([
    "            result = self.ask_about_folder(user_text)",
    "            if isinstance(result, str) and result.startswith(\"Укажите существующую папку\"):",
    "                self.pending_tool = 'ask_about_folder'",
])
NEW_ASK_TOOL = NL.join([
    "            result = self.ask_about_folder(user_text)",
    "            if isinstance(result, str) and result.startswith(\"Укажите существующую папку\"):",
    "                self.pending_tool = 'ask_about_folder'",
    "                self.pending_query = user_text",
])


def patch_file(path, old, new, label):
    if not os.path.exists(path):
        print("[SKIP] Нет " + path)
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print("[WARN] " + label + " — фрагмент не найден")
        return
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[OK] " + label)


def main():
    # 1. extractors.py
    print("=== 1. documents/extractors.py ===")
    with open("documents/extractors.py", "r", encoding="utf-8") as f:
        content = f.read()
    content, ok = replace_function(content, "extract_pdf", NEW_PDF)
    print("[OK] extract_pdf (страницы)" if ok else "[WARN] extract_pdf")
    content, ok = replace_function(content, "extract_docx", NEW_DOCX)
    print("[OK] extract_docx (разделы)" if ok else "[WARN] extract_docx")
    with open("documents/extractors.py", "w", encoding="utf-8") as f:
        f.write(content)

    # 2. indexer.py
    print("")
    print("=== 2. rag/indexer.py ===")
    with open("rag/indexer.py", "r", encoding="utf-8") as f:
        content = f.read()
    if OLD_FILES in content:
        content = content.replace(OLD_FILES, NEW_FILES, 1)
        with open("rag/indexer.py", "w", encoding="utf-8") as f:
            f.write(content)
        print("[OK] дедупликация .doc/.docx")
    else:
        print("[WARN] не найден files_to_index")

    # 3. agent.py
    print("")
    print("=== 3. core/agent.py ===")
    patch_file("core/agent.py", OLD_INIT, NEW_INIT, "pending_query в __init__")
    patch_file("core/agent.py", OLD_RESOLVE, NEW_RESOLVE, "_try_resolve_pending: original_q")
    patch_file("core/agent.py", OLD_RESOLVE_FOLDER, NEW_RESOLVE_FOLDER, "ask_about_folder: combined")

    patch_file("core/agent.py", OLD_BATCH, NEW_BATCH, "pending_query: batch_summarize")
    patch_file("core/agent.py", OLD_CLASSIFY, NEW_CLASSIFY, "pending_query: classify_files")
    patch_file("core/agent.py", OLD_LIST, NEW_LIST, "pending_query: make_file_list")
    patch_file("core/agent.py", OLD_SPELL, NEW_SPELL, "pending_query: check_spelling")
    patch_file("core/agent.py", OLD_SUMMARIZE, NEW_SUMMARIZE, "pending_query: summarize_file")
    patch_file("core/agent.py", OLD_ASK_TOOL, NEW_ASK_TOOL, "pending_query: ask_about_folder")

    print("")
    print("=" * 60)
    print("ГОТОВО! Запускай: python main.py")
    print("=" * 60)
    print("")
    print("Что изменилось:")
    print("1. Агент теперь ЗАПОМИНАЕТ первоначальный вопрос, когда просит папку.")
    print("2. При следующем сообщении с путём — он использует вопрос + путь.")
    print("3. В PDF добавлены [Стр. N], в DOCX — [Раздел: ...].")
    print("4. .doc не дублируется, если есть .docx.")
    print("")
    print("ВАЖНО: так как формат текста изменился (страницы/разделы),")
    print("нужно СБРОСИТЬ базу RAG и переиндексировать папку заново!")


if __name__ == "__main__":
    main()