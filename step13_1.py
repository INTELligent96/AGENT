import os


NL = "\n"


# ================ ROUTER.PY (перезапись) ================
ROUTER = NL.join([
    "import json",
    "from llm.registry import LLMRegistry",
    "",
    "",
    "KEYWORD_RULES = {",
    '    "ask_about_folder": ["что в папке", "что находится в папке", "расскажи про папку", "расскажи о папке", "обзор папки", "вопрос по папке", "найди в папке", "краткое содержание папки"],',
    '    "generate_code": ["напиши код", "напиши функцию", "напиши скрипт", "сгенерируй код", "python код", "код на питоне", "напиши программу"],',
    '    "check_spelling": ["проверь ошибки", "орфография", "исправь ошибки", "пунктуация", "опечатки"],',
    '    "summarize_file": ["сделай резюме", "краткое содержание", "о чём документ", "о чем документ", "перескажи"],',
    '    "batch_summarize": ["резюме папки", "резюме всех файлов", "резюме всей папки"],',
    '    "classify_files": ["отсортируй файлы", "разложи по папкам", "классифицируй"],',
    '    "make_file_list": ["список файлов", "перечень файлов"],',
    '    "make_excel_chart": ["построй график", "сделай график", "график в excel", "диаграмма"],',
    '    "web_search": ["найди в интернете", "погугли", "поищи в сети", "поиск в интернете"],',
    '    "process_long_doc": ["полный разбор", "разбери книгу", "разбери документ целиком"],',
    '    "index_folder": ["проиндексируй", "индексируй папку"],',
    '    "translate": ["переведи", "перевод на", "translate"],',
    '    "open_style_studio": ["студия стилей", "замени стили", "сопоставь стили", "стили word"],',
    "}",
    "",
    "",
    "FOLDER_VERBS = [",
    '    "расскажи", "обзор", "покажи", "что в", "что находится",',
    '    "проанализ", "кратко", "опиши", "дай обзор", "перескажи",',
    "]",
    "",
    "",
    "INDEX_VERBS = [",
    '    "индексируй", "проиндексируй", "проиндексир",',
    "]",
    "",
    "",
    "SORT_VERBS = [",
    '    "отсортируй", "разложи", "сортировк", "классифиц",',
    "]",
    "",
    "",
    "class IntentRouter:",
    "    def __init__(self, registry: LLMRegistry, config: dict):",
    "        self.registry = registry",
    '        self.router_config = config.get("router", {})',
    '        self.dangerous_tools = list(self.router_config.get("dangerous_tools", []))',
    '        self.use_llm = self.router_config.get("use_llm_for_ambiguous", True)',
    "        self.plugins = {}",
    "",
    "    def attach_plugins(self, plugins: dict):",
    "        self.plugins = plugins",
    "        for name, plugin in plugins.items():",
    '            if getattr(plugin, "dangerous", False) and name not in self.dangerous_tools:',
    "                self.dangerous_tools.append(name)",
    "",
    "    def get_keyword_rules(self) -> dict:",
    "        rules = dict(KEYWORD_RULES)",
    "        for name, plugin in self.plugins.items():",
    "            if plugin.keywords:",
    "                rules[name] = [kw.lower() for kw in plugin.keywords]",
    "        return rules",
    "",
    "    def classify(self, user_text: str) -> dict:",
    "        text = user_text.lower()",
    "",
    "        # === ПРИОРИТЕТ 1: если упомянута папка + вопрос-глагол → ask_about_folder",
    '        has_folder = "папк" in text or "каталог" in text',
    "        has_folder_verb = any(v in text for v in FOLDER_VERBS)",
    "        is_explicit_command = (",
    "            any(v in text for v in INDEX_VERBS)",
    "            or any(v in text for v in SORT_VERBS)",
    '            or "резюме папки" in text',
    '            or "резюме всех файлов" in text',
    "        )",
    "        if has_folder and has_folder_verb and not is_explicit_command:",
    "            return {",
    '                "tools": ["ask_about_folder"],',
    '                "reasoning": "Упоминание папки + вопрос (приоритет)",',
    '                "ambiguous": False',
    "            }",
    "",
    "        rules = self.get_keyword_rules()",
    "        matched = []",
    "        for tool, keywords in rules.items():",
    "            if any(kw in text for kw in keywords):",
    "                matched.append(tool)",
    "",
    "        if matched:",
    "            return {",
    '                "tools": matched,',
    '                "reasoning": "Совпадение по ключевым словам: " + str(matched),',
    '                "ambiguous": False',
    "            }",
    "",
    "        if self.use_llm:",
    "            return self._classify_with_llm(user_text, rules)",
    "",
    "        return {",
    '            "tools": ["ask_question"],',
    '            "reasoning": "По умолчанию: RAG-поиск по документам",',
    '            "ambiguous": True',
    "        }",
    "",
    "    def _classify_with_llm(self, user_text: str, rules: dict) -> dict:",
    '        tools_desc = "\\n".join([f"- {t}" for t in rules.keys()])',
    "        prompt = (",
    '            "Ты - классификатор намерений. Доступные инструменты:\\n" + tools_desc + "\\n"',
    '            "- ask_question: вопросы по проиндексированным документам\\n\\n"',
    '            "Запрос: \\"" + user_text + "\\"\\n\\n"',
    '            "Верни ТОЛЬКО JSON: {\\"tools\\": [\\"имя\\"], \\"reasoning\\": \\"...\\"}"',
    "        )",
    '        raw = self.registry.generate_with_fallback("default_model", prompt)',
    "        try:",
    '            clean = raw.replace("```json", "").replace("```", "").strip()',
    "            data = json.loads(clean)",
    '            data["ambiguous"] = False',
    "            return data",
    "        except Exception:",
    "            return {",
    '                "tools": ["ask_question"],',
    '                "reasoning": "LLM не дал JSON. Fallback на RAG.",',
    '                "ambiguous": True',
    "            }",
])


# ================ PATCHES для AGENT.PY ================
OLD_EXTS = (
    '        exts = (\'.txt\', \'.docx\', \'.doc\', \'.pdf\', \'.xlsx\', \'.xls\', \'.csv\', \'.png\', \'.jpg\', \'.jpeg\', \'.bmp\', \'.tiff\')'
)

NEW_EXTS = (
    '        exts = (\'.txt\', \'.docx\', \'.doc\', \'.pdf\', \'.xlsx\', \'.xls\', \'.csv\', \'.png\', \'.jpg\', \'.jpeg\', \'.bmp\', \'.tiff\', \'.py\', \'.json\', \'.md\', \'.html\', \'.xml\', \'.yaml\', \'.yml\', \'.ini\', \'.log\', \'.bat\', \'.ps1\', \'.sh\', \'.rtf\', \'.odt\')'
)

OLD_RESULTS_OK = '                results.append("=== " + tool_name + " ===\\n" + result)'
NEW_RESULTS_OK = '                results.append("=== " + tool_name + " ===\\n" + str(result))'

OLD_RESULTS_ERR = '                results.append("=== " + tool_name + " (ОШИБКА) ===\\n" + str(e))'
NEW_RESULTS_ERR = '                results.append("=== " + tool_name + " (ОШИБКА) ===\\n" + str(e))'

# Более умный ask_about_folder
OLD_ASK = NL.join([
    "    def ask_about_folder(self, user_text):",
    "        folder = self._extract_folder_from_text(user_text)",
    "        if not folder:",
    '            return "Укажите существующую папку. Пример: что в папке D:/Docs? кто директор?"',
    "        err = self._require_allowed(folder)",
    "        if err:",
    "            return err",
    "        abs_folder = os.path.abspath(folder)",
    "        if abs_folder not in self._indexed_folders:",
    '            print("[Auto-Index] Индексирую папку: " + folder)',
    "            self.rag.indexer.index_folder(folder)",
    "            self._indexed_folders.add(abs_folder)",
    '        question = user_text.replace(folder, "").strip()',
    "        if not question or len(question) < 5:",
    '            question = "Сделай краткий обзор содержимого этих документов."',
    "        return self.ask_question(question)",
])

NEW_ASK = NL.join([
    "    def ask_about_folder(self, user_text):",
    "        folder = self._extract_folder_from_text(user_text)",
    "        if not folder:",
    '            return "Укажите существующую папку. Пример: что в папке D:/Docs? кто директор?"',
    "        err = self._require_allowed(folder)",
    "        if err:",
    "            return err",
    "        abs_folder = os.path.abspath(folder)",
    "        if abs_folder not in self._indexed_folders:",
    '            print("[Auto-Index] Индексирую папку: " + folder)',
    "            self.rag.indexer.index_folder(folder)",
    "            self._indexed_folders.add(abs_folder)",
    '        question = user_text.replace(folder, "").strip()',
    "        # Убираем общие слова про папку, чтобы понять, есть ли специфичный вопрос",
    '        generic = ["расскажи", "кратко", "обзор", "покажи", "о папке", "про папку", "что в", "что находится", "проанализируй", "опиши", "дай обзор", "перескажи", "папке", "папки", "папку", "каталоге", "каталог"]',
    "        specific = question",
    "        for gw in generic:",
    '            specific = specific.replace(gw, " ")',
    '        specific = specific.strip(" ?!.,;:\\t\\n")',
    "        if len(specific) < 5:",
    '            question = "Сделай краткий обзор содержимого этих документов. Какие темы/вопросы они освещают?"',
    "        return self.ask_question(question)",
])


def patch_file(path, old, new, label):
    if not os.path.exists(path):
        print("[SKIP] Нет файла: " + path)
        return False
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print("[WARN] (" + label + ") Не найден фрагмент в " + path)
        return False
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[OK] " + label + " → " + path)
    return True


def main():
    # 1. Перезаписываем router.py целиком
    with open("core/router.py", "w", encoding="utf-8") as f:
        f.write(ROUTER)
    print("[OK] Перезаписан: core/router.py")

    # 2. Патчим agent.py
    print("")
    print("Патчинг core/agent.py...")
    patch_file("core/agent.py", OLD_EXTS, NEW_EXTS, "exts: +py/json/md и др.")
    patch_file("core/agent.py", OLD_RESULTS_OK, NEW_RESULTS_OK, "run_task: str(result)")
    patch_file("core/agent.py", OLD_ASK, NEW_ASK, "ask_about_folder: умный обзор")

    print("")
    print("Готово! Запускай: python main.py")


if __name__ == "__main__":
    main()
