import os
import re


NL = "\n"


# ============ Новые методы парсинга ============
NEW_EXTRACT_METHODS = NL.join([
    "    def _extract_folder_from_text(self, text):",
    "        # 1. Если весь текст (обрезанный) — существующая папка",
    "        cleaned = text.strip().strip('\"').strip(\"'\").strip('`').strip()",
    "        try:",
    "            if cleaned and os.path.isdir(cleaned):",
    "                return cleaned",
    "        except Exception:",
    "            pass",
    "",
    "        # 2. Ищем все вхождения 'X:\\' или 'X:/'",
    "        for m in re.finditer(r'[A-Za-z]:[\\\\/][^\\n\\r]*', text):",
    "            raw = m.group(0)",
    "            # Убираем завершающие кавычки и пунктуацию",
    "            raw = raw.rstrip('\"\\';,?!)]}>')",
    "            parts = raw.split(' ')",
    "            # От длинного к короткому — ищем существующую папку",
    "            for i in range(len(parts), 0, -1):",
    "                candidate = ' '.join(parts[:i]).strip()",
    "                if candidate:",
    "                    try:",
    "                        if os.path.isdir(candidate):",
    "                            return candidate",
    "                    except Exception:",
    "                        pass",
    "",
    "        # 3. Fallback: старое поведение (отдельные токены без пробелов)",
    "        bad = ('\"', \"'\", '`', '(', ')', '[', ']', '{', '}', '<', '>', ',', ';', '!', '?')",
    "        for raw in text.split():",
    "            t = raw",
    "            ch = True",
    "            while ch and t:",
    "                ch = False",
    "                if t[0] in bad:",
    "                    t = t[1:]",
    "                    ch = True",
    "                if t and t[-1] in bad:",
    "                    t = t[:-1]",
    "                    ch = True",
    "            if not t:",
    "                continue",
    "            try:",
    "                if os.path.isdir(t):",
    "                    return t",
    "            except Exception:",
    "                pass",
    "        return None",
    "",
    "    def _extract_path_from_text(self, text):",
    "        exts = ('.txt', '.docx', '.doc', '.pdf', '.xlsx', '.xls', '.csv',",
    "                '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.py', '.json', '.md',",
    "                '.html', '.xml', '.yaml', '.yml', '.ini', '.log', '.bat', '.ps1',",
    "                '.sh', '.rtf', '.odt')",
    "",
    "        # 1. Если весь текст — существующий файл",
    "        cleaned = text.strip().strip('\"').strip(\"'\").strip('`').strip()",
    "        try:",
    "            if cleaned and os.path.isfile(cleaned):",
    "                return cleaned",
    "        except Exception:",
    "            pass",
    "",
    "        # 2. Ищем 'X:\\...' и 'X:/...'",
    "        for m in re.finditer(r'[A-Za-z]:[\\\\/][^\\n\\r]*', text):",
    "            raw = m.group(0)",
    "            raw = raw.rstrip('\"\\';,?!)]}>')",
    "            parts = raw.split(' ')",
    "            for i in range(len(parts), 0, -1):",
    "                candidate = ' '.join(parts[:i]).strip()",
    "                if candidate and candidate.lower().endswith(exts):",
    "                    try:",
    "                        if os.path.isfile(candidate):",
    "                            return candidate",
    "                    except Exception:",
    "                        pass",
    "",
    "        # 3. Fallback: отдельные токены",
    "        bad = ('\"', \"'\", '`', '(', ')', '[', ']', '{', '}', '<', '>', ',', ';', ':', '!', '?')",
    "        for raw in text.split():",
    "            t = raw",
    "            ch = True",
    "            while ch and t:",
    "                ch = False",
    "                if t[0] in bad:",
    "                    t = t[1:]",
    "                    ch = True",
    "                if t and t[-1] in bad:",
    "                    t = t[:-1]",
    "                    ch = True",
    "            if not t:",
    "                continue",
    "            if t.lower().endswith(exts):",
    "                return t",
    "        return None",
    "",
    "",
])


# ============ Патч _execute_tool для ask_about_folder ============
OLD_ASK_FOLDER_CALL = NL.join([
    "        if tool_name == \"ask_about_folder\":",
    "            return self.ask_about_folder(user_text)",
])
NEW_ASK_FOLDER_CALL = NL.join([
    "        if tool_name == \"ask_about_folder\":",
    "            result = self.ask_about_folder(user_text)",
    "            if isinstance(result, str) and result.startswith(\"Укажите существующую папку\"):",
    "                self.pending_tool = 'ask_about_folder'",
    "            return result",
])


# ============ Патч _try_resolve_pending для ask_about_folder ============
OLD_RESOLVE_FOLDER = NL.join([
    "            if tool == 'ask_about_folder':",
    "                return self.ask_about_folder('что в папке ' + arg + '?')",
])
NEW_RESOLVE_FOLDER = NL.join([
    "            if tool == 'ask_about_folder':",
    "                return self.ask_about_folder(arg)",
])


def replace_method(content, func_name, new_body):
    """Заменяет метод по имени (def <name>(...) до следующего def на том же уровне)."""
    pattern = re.compile(
        r"    def " + re.escape(func_name) + r"\([^)]*\):.*?(?=\n    def |\Z)",
        re.DOTALL,
    )
    m = pattern.search(content)
    if not m:
        return content, False
    return content[:m.start()] + new_body + "\n" + content[m.end():], True


def main():
    path = "core/agent.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Удаляем старые методы парсинга и вставляем новые
    old_folder_pattern = re.compile(
        r"    def _extract_folder_from_text\(self, text\):.*?(?=\n    def )",
        re.DOTALL,
    )
    old_path_pattern = re.compile(
        r"    def _extract_path_from_text\(self, text\):.*?(?=\n    def |\Z)",
        re.DOTALL,
    )

    # Сначала удаляем _extract_folder_from_text
    m1 = old_folder_pattern.search(content)
    if m1:
        content = content[:m1.start()] + content[m1.end():]
        print("[OK] старый _extract_folder_from_text удалён")
    else:
        print("[WARN] не найден старый _extract_folder_from_text")

    # Потом _extract_path_from_text
    m2 = old_path_pattern.search(content)
    if m2:
        content = content[:m2.start()] + content[m2.end():]
        print("[OK] старый _extract_path_from_text удалён")
    else:
        print("[WARN] не найден старый _extract_path_from_text")

    # Вставляем новые методы перед ask_question
    anchor = "    def ask_question"
    if anchor in content:
        content = content.replace(anchor, NEW_EXTRACT_METHODS + anchor, 1)
        print("[OK] новые методы _extract_* добавлены")
    else:
        print("[WARN] не найден ask_question — некуда вставить")

    # 2. Патч _execute_tool для ask_about_folder
    if OLD_ASK_FOLDER_CALL in content:
        content = content.replace(OLD_ASK_FOLDER_CALL, NEW_ASK_FOLDER_CALL, 1)
        print("[OK] ask_about_folder → pending_tool при ошибке")
    else:
        print("[WARN] не найден вызов ask_about_folder в _execute_tool")

    # 3. Патч _try_resolve_pending
    if OLD_RESOLVE_FOLDER in content:
        content = content.replace(OLD_RESOLVE_FOLDER, NEW_RESOLVE_FOLDER, 1)
        print("[OK] _try_resolve_pending → ask_about_folder(arg)")
    else:
        print("[WARN] не найден блок _try_resolve_pending для ask_about_folder")

    # 4. Убеждаемся, что re импортирован
    if "import re" not in content.split("class Agent")[0]:
        # Добавим после первого import
        first_import_end = content.find("\n", content.find("import "))
        content = content[:first_import_end] + "\nimport re" + content[first_import_end:]
        print("[OK] добавлен import re")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print("")
    print("=" * 60)
    print("Готово! Запускай: python main.py")
    print("=" * 60)
    print("")
    print("Что проверить:")
    print("1. Задай вопрос с длинным путём в кавычках или без:")
    print("   'проанализируй документы в папке D:\\DEEPSEEK\\ДАННЫЕ ДЛЯ АГЕНТА\\ТЭО с подсчетом запасов Черногорского_2010\\'")
    print("2. Если агент спросит 'Укажите папку' — следующим сообщением дай путь:")
    print("   'D:\\DEEPSEEK\\ДАННЫЕ ДЛЯ АГЕНТА\\ТЭО с подсчетом запасов Черногорского_2010\\'")
    print("   Агент должен подхватить путь и запустить анализ.")
    print("")
    print("Если что-то упадёт — скинь лог.")


if __name__ == "__main__":
    main()