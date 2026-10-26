import os


NL = "\n"


# ================ RAG/QA.PY — перезапись ================
QA_PY = NL.join([
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
    "        if not history:",
    "            print('  [RAG] История пуста, ищу по текущему вопросу.')",
    "            return question",
    "",
    "        last_user = None",
    "        for h in reversed(history):",
    "            if h.get('role') == 'user':",
    "                last_user = h.get('content', '')",
    "                break",
    "",
    "        if not last_user:",
    "            print('  [RAG] Предыдущего вопроса не найдено в истории.')",
    "            return question",
    "",
    "        print('  [RAG] История: ' + str(len(history)) + ' элементов. Предыдущий вопрос: ' + last_user[:70])",
    "",
    "        # Если вопрос короткий или содержит местоимения - ВСЕГДА объединяем",
    "        is_short = len(question) < 60",
    "        words = question.lower().split()",
    "        has_pronoun = any(p in words for p in PRONOUNS)",
    "",
    "        if is_short or has_pronoun:",
    "            combined = last_user + ' ' + question",
    "            print('  [RAG] Поиск с контекстом (short=' + str(is_short) + ', pronoun=' + str(has_pronoun) + '): ' + combined[:100])",
    "            return combined",
    "",
    "        # Даже если длинный - добавляем предыдущий для страховки",
    "        combined = last_user + ' ' + question",
    "        print('  [RAG] Поиск с расширенным контекстом: ' + combined[:100])",
    "        return combined",
    "",
    "    def ask(self, question: str, history=None) -> str:",
    "        search_query = self._build_search_query(question, history)",
    "        print(\"Поиск по базе для вопроса: '\" + search_query[:80] + \"'...\")",
    "        context_chunks = self.indexer.search(search_query, top_k=12)",
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
    "            \"ВАЖНО: внимательно прочитай ВСЕ фрагменты. Если ответ есть хотя бы в одном фрагменте - выведи его. \"",
    "            \"Не пиши 'не указано', если ты не проверил все фрагменты до конца. \"",
    "            \"Если вопрос - продолжение диалога (местоимения 'он', 'она', 'это', 'там'), \"",
    "            \"используй историю диалога для понимания, о чём речь. \"",
    "            \"Обязательно указывай, из какого файла взята информация. \"",
    "            \"Отвечай кратко и по делу.\"",
    "        )",
    "",
    "        user_prompt = \"\"",
    "        if history:",
    "            user_prompt += \"ИСТОРИЯ ДИАЛОГА (для понимания контекста):\\n\"",
    "            for h in history[-6:]:",
    "                role = \"Пользователь\" if h['role'] == 'user' else \"Ассистент\"",
    "                content = str(h['content'])[:400]",
    "                user_prompt += role + \": \" + content + \"\\n\"",
    "            user_prompt += \"\\n\"",
    "",
    "        user_prompt += \"КОНТЕКСТ:\\n\" + context_text + \"\\n\\nВОПРОС: \" + question",
    "",
    "        print(\"Запуск отказоустойчивой генерации (complex_reasoning)...\")",
    "        return self.registry.generate_with_fallback(\"complex_reasoning\", user_prompt, system_prompt)",
])


# ================ PATCH AGENT.PY ================
# Добавить last_folder в __init__ и обновлять в ask_about_folder
OLD_INIT = (
    "        self.pending_tool = None   # инструмент, ожидающий аргумент (папка/файл)" + NL +
    "        self.chat_history = []     # [{'role': 'user'/'assistant', 'content': '...'}, ...]" + NL +
    "        self.max_history = 5       # сколько последних пар хранить"
)
NEW_INIT = (
    "        self.pending_tool = None   # инструмент, ожидающий аргумент (папка/файл)" + NL +
    "        self.chat_history = []     # [{'role': 'user'/'assistant', 'content': '...'}, ...]" + NL +
    "        self.max_history = 5       # сколько последних пар хранить" + NL +
    "        self.last_folder = None    # папка последнего ask_about_folder"
)


# Обновляем ask_about_folder: сохраняем last_folder
OLD_ASK_START = (
    "        abs_folder = os.path.abspath(folder)" + NL +
    "        if abs_folder not in self._indexed_folders:" + NL +
    "            print(\"[Auto-Index] Индексирую папку: \" + folder)" + NL +
    "            self.rag.indexer.index_folder(folder)" + NL +
    "            self._indexed_folders.add(abs_folder)"
)
NEW_ASK_START = (
    "        abs_folder = os.path.abspath(folder)" + NL +
    "        self.last_folder = folder   # запоминаем для контекста следующих вопросов" + NL +
    "        if abs_folder not in self._indexed_folders:" + NL +
    "            print(\"[Auto-Index] Индексирую папку: \" + folder)" + NL +
    "            self.rag.indexer.index_folder(folder)" + NL +
    "            self._indexed_folders.add(abs_folder)"
)


# В ask_question добавляем контекст "last_folder"
OLD_ASK_Q = (
    "    def ask_question(self, question):" + NL +
    "        return self.rag.ask(question, history=self.chat_history)"
)
NEW_ASK_Q = (
    "    def ask_question(self, question):" + NL +
    "        # Если недавно работали с папкой - подсказываем это LLM" + NL +
    "        hist = list(self.chat_history)" + NL +
    "        if self.last_folder and not any(fp in question for fp in [self.last_folder, os.path.basename(self.last_folder)]):" + NL +
    "            hist.append({'role': 'user', 'content': 'Контекст: недавно мы работали с папкой ' + self.last_folder})" + NL +
    "        return self.rag.ask(question, history=hist)"
)


def patch(path, old, new, label):
    if not os.path.exists(path):
        print("[SKIP] Нет файла: " + path)
        return False
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print("[WARN] " + label + " → " + path + " (фрагмент не найден)")
        return False
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[OK] " + label + " → " + path)
    return True


def main():
    print("Перезапись rag/qa.py (жёсткий контекст + диагностика)...")
    with open("rag/qa.py", "w", encoding="utf-8") as f:
        f.write(QA_PY)
    print("[OK] rag/qa.py")

    print("")
    print("Патчинг core/agent.py...")
    patch("core/agent.py", OLD_INIT, NEW_INIT, "agent: last_folder в __init__")
    patch("core/agent.py", OLD_ASK_START, NEW_ASK_START, "agent: ask_about_folder → last_folder")
    patch("core/agent.py", OLD_ASK_Q, NEW_ASK_Q, "agent: ask_question → контекст last_folder")

    print("")
    print("Готово! Запускай: python main.py")
    print("")
    print("Проверка: спроси 'а кто директор?' — в консоли должна появиться строка:")
    print("  [RAG] История: 2 элементов. Предыдущий вопрос: что в папке...")
    print("  [RAG] Поиск с контекстом (short=True, pronoun=False): ...")
    print("Если этих строк нет — история не передаётся, тогда скинь лог.")


if __name__ == "__main__":
    main()