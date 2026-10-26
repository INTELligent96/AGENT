import os


NL = "\n"
FILES = {}


# ================ RAG/QA.PY (перезапись) ================
FILES["rag/qa.py"] = NL.join([
    "from pathlib import Path",
    "from .indexer import RAGIndexer",
    "from llm.registry import LLMRegistry",
    "",
    "",
    "PRONOUNS = [",
    "    'он', 'она', 'оно', 'они', 'это', 'этот', 'эта', 'эти',",
    "    'там', 'тут', 'его', 'её', 'их', 'ему', 'ей', 'тот', 'та', 'те',",
    "    'той', 'того', 'этого', 'этой', 'который', 'которая', 'которое', 'которые',",
    "]",
    "",
    "",
    "class RAGQuestionAnswerer:",
    "    def __init__(self, config: dict, tools_config: dict, registry: LLMRegistry):",
    "        self.indexer = RAGIndexer(config, tools_config)",
    "        self.registry = registry",
    "",
    "    def _build_search_query(self, question, history):",
    "        # Если вопрос короткий или содержит местоимения - дополняем предыдущим вопросом",
    "        if not history:",
    "            return question",
    "        last_user = None",
    "        for h in reversed(history):",
    "            if h.get('role') == 'user':",
    "                last_user = h.get('content', '')",
    "                break",
    "        if not last_user:",
    "            return question",
    "",
    "        is_short = len(question) < 50",
    "        words = question.lower().split()",
    "        has_pronoun = any(p in words for p in PRONOUNS)",
    "        if is_short or has_pronoun:",
    "            combined = last_user + ' ' + question",
    "            print(\"  [RAG] Поиск с контекстом: '\" + combined[:90] + \"...'\")",
    "            return combined",
    "        return question",
    "",
    "    def ask(self, question: str, history=None) -> str:",
    "        search_query = self._build_search_query(question, history)",
    "        print(\"Поиск по базе для вопроса: '\" + search_query[:60] + \"'...\")",
    "        context_chunks = self.indexer.search(search_query, top_k=8)",
    "",
    "        if not context_chunks:",
    "            return \"В базе данных не найдено информации по этому вопросу.\"",
    "",
    "        context_text = \"\"",
    "        for i, chunk in enumerate(context_chunks, 1):",
    "            source = Path(chunk['source']).name",
    "            context_text += \"--- Фрагмент \" + str(i) + \" (Источник: \" + source + \", часть \" + str(chunk['chunk_id']) + \") ---\\n\"",
    "            context_text += chunk['text'] + \"\\n\\n\"",
    "",
    "        system_prompt = (",
    "            \"Ты - ассистент по работе с документами. Отвечай на вопрос пользователя, \"",
    "            \"ОПИРАЯСЬ ТОЛЬКО на предоставленные фрагменты текста. \"",
    "            \"Если вопрос - продолжение диалога (местоимения 'он', 'она', 'это', 'там'), \"",
    "            \"используй историю диалога для понимания, о чём речь. \"",
    "            \"Если в тексте нет ответа, честно скажи, что не знаешь. \"",
    "            \"Обязательно указывай, из какого файла взята информация. \"",
    "            \"Отвечай кратко и по делу.\"",
    "        )",
    "",
    "        user_prompt = \"\"",
    "        if history:",
    "            user_prompt += \"ИСТОРИЯ ДИАЛОГА:\\n\"",
    "            for h in history[-6:]:",
    "                role = \"Пользователь\" if h['role'] == 'user' else \"Ассистент\"",
    "                content = str(h['content'])[:300]",
    "                user_prompt += role + \": \" + content + \"\\n\"",
    "            user_prompt += \"\\n\"",
    "",
    "        user_prompt += \"КОНТЕКСТ:\\n\" + context_text + \"\\n\\nВОПРОС: \" + question",
    "",
    "        print(\"Запуск отказоустойчивой генерации (complex_reasoning)...\")",
    "        return self.registry.generate_with_fallback(\"complex_reasoning\", user_prompt, system_prompt)",
])


# ================ CORE/AGENT.PY — патч ask_about_folder ================

OLD_ASK = NL.join([
    "    def ask_about_folder(self, user_text):",
    "        folder = self._extract_folder_from_text(user_text)",
    "        if not folder:",
    "            return \"Укажите существующую папку. Пример: что в папке D:/Docs? кто директор?\"",
    "        err = self._require_allowed(folder)",
    "        if err:",
    "            return err",
    "        abs_folder = os.path.abspath(folder)",
    "        if abs_folder not in self._indexed_folders:",
    "            print(\"[Auto-Index] Индексирую папку: \" + folder)",
    "            self.rag.indexer.index_folder(folder)",
    "            self._indexed_folders.add(abs_folder)",
    "        question = user_text.replace(folder, \"\").strip()",
    "        # Убираем общие слова про папку, чтобы понять, есть ли специфичный вопрос",
    "        generic = [\"расскажи\", \"кратко\", \"обзор\", \"покажи\", \"о папке\", \"про папку\", \"что в\", \"что находится\", \"проанализируй\", \"опиши\", \"дай обзор\", \"перескажи\", \"папке\", \"папки\", \"папку\", \"каталоге\", \"каталог\"]",
    "        specific = question",
    "        for gw in generic:",
    "            specific = specific.replace(gw, \" \")",
    "        specific = specific.strip(\" ?!.,;:\\t\\n\")",
    "        if len(specific) < 5:",
    "            question = \"Сделай краткий обзор содержимого этих документов. Какие темы/вопросы они освещают?\"",
    "        return self.ask_question(question)",
])

NEW_ASK = NL.join([
    "    def ask_about_folder(self, user_text):",
    "        folder = self._extract_folder_from_text(user_text)",
    "        if not folder:",
    "            return \"Укажите существующую папку. Пример: что в папке D:/Docs? кто директор?\"",
    "        err = self._require_allowed(folder)",
    "        if err:",
    "            return err",
    "        abs_folder = os.path.abspath(folder)",
    "        if abs_folder not in self._indexed_folders:",
    "            print(\"[Auto-Index] Индексирую папку: \" + folder)",
    "            self.rag.indexer.index_folder(folder)",
    "            self._indexed_folders.add(abs_folder)",
    "",
    "        # === Получаем список файлов для явного перечисления ===",
    "        file_list_text = \"\"",
    "        lower_text = user_text.lower()",
    "        wants_file_list = any(kw in lower_text for kw in [",
    "            \"что в папке\", \"что находится\", \"список файлов\", \"какие файлы\",",
    "            \"покажи файлы\", \"перечень\", \"содержимое папки\", \"обзор папки\"",
    "        ])",
    "        if wants_file_list:",
    "            try:",
    "                from pathlib import Path as _P",
    "                all_files = [f for f in _P(folder).rglob('*') if f.is_file()]",
    "                if all_files:",
    "                    file_list_text = \"Файлы в папке \" + folder + \":\\n\"",
    "                    for f in all_files[:30]:",
    "                        file_list_text += \"- \" + f.name + \"\\n\"",
    "                    if len(all_files) > 30:",
    "                        file_list_text += \"... и ещё \" + str(len(all_files) - 30) + \" файлов\\n\"",
    "            except Exception as e:",
    "                file_list_text = \"[Не удалось получить список: \" + str(e) + \"]\\n\"",
    "",
    "        question = user_text.replace(folder, \"\").strip()",
    "        generic = [\"расскажи\", \"кратко\", \"обзор\", \"покажи\", \"о папке\", \"про папку\", \"что в\", \"что находится\", \"проанализируй\", \"опиши\", \"дай обзор\", \"перескажи\", \"папке\", \"папки\", \"папку\", \"каталоге\", \"каталог\", \"содержимое\", \"содержимом\"]",
    "        specific = question",
    "        for gw in generic:",
    "            specific = specific.replace(gw, \" \")",
    "        specific = specific.strip(\" ?!.,;:\\t\\n\")",
    "",
    "        # Если специфичного вопроса нет - только файлы + общий обзор",
    "        if len(specific) < 5:",
    "            if file_list_text:",
    "                question = \"Сделай краткий обзор содержимого этих документов: какие темы, ключевые факты и вопросы они освещают?\"",
    "                rag_answer = self.ask_question(question)",
    "                return file_list_text + \"\\n--- Обзор содержимого ---\\n\" + rag_answer",
    "            else:",
    "                question = \"Сделай краткий обзор содержимого этих документов. Какие темы/вопросы они освещают?\"",
    "        else:",
    "            question = specific",
    "",
    "        # Если есть специфичный вопрос - RAG-ответ + (опционально) список файлов сверху",
    "        rag_answer = self.ask_question(question)",
    "        if file_list_text:",
    "            return file_list_text + \"\\n--- Ответ на вопрос ---\\n\" + rag_answer",
    "        return rag_answer",
])


def patch(path, old, new, label):
    if not os.path.exists(path):
        print("[SKIP] Нет файла: " + path)
        return False
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print("[WARN] " + label + " → " + path)
        return False
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[OK] " + label + " → " + path)
    return True


def main():
    print("Перезапись rag/qa.py (умный поиск с историей)...")
    with open("rag/qa.py", "w", encoding="utf-8") as f:
        f.write(FILES["rag/qa.py"])
    print("[OK] rag/qa.py перезаписан")

    print("")
    print("Патчинг core/agent.py (файлы + RAG в ask_about_folder)...")
    patch("core/agent.py", OLD_ASK, NEW_ASK, "agent: ask_about_folder + файлы")

    print("")
    print("Готово! Запускай: python main.py")
    print("")
    print("Проверки:")
    print("1. 'что в папке D:/.../TEST_FULL? в каком году основана компания?'")
    print("   → должен вывести список файлов + ответ про 1995 год")
    print("2. 'а кто директор?' → должен найти Ивана Иванова через историю")
    print("3. 'расскажи кратко о папке D:/.../TEST_FULL'")
    print("   → должен вывести список файлов + общий обзор")


if __name__ == "__main__":
    main()