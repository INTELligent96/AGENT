
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
    "        # Берём только реальные вопросы пользователя (без системных вставок)",
    "        if not history:",
    "            return question",
    "",
    "        last_user = None",
    "        for h in reversed(history):",
    "            if h.get('role') == 'user':",
    "                content = h.get('content', '')",
    "                if content.startswith('Контекст:') or content.startswith('[Диалог]'):",
    "                    continue",
    "                last_user = content",
    "                break",
    "",
    "        if not last_user:",
    "            return question",
    "",
    "        is_short = len(question) < 60",
    "        words = question.lower().split()",
    "        has_pronoun = any(p in words for p in PRONOUNS)",
    "",
    "        if is_short or has_pronoun:",
    "            combined = last_user + ' ' + question",
    "            print('  [RAG] Поиск с контекстом (short=' + str(is_short) + ', pronoun=' + str(has_pronoun) + '): ' + combined[:100])",
    "            return combined",
    "",
    "        print('  [RAG] Поиск по чистому вопросу (длинный, без местоимений)')",
    "        return question",
    "",
    "    def ask(self, question: str, history=None, last_folder=None) -> str:",
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
    "            \"Если вопрос - продолжение диалога, используй историю для понимания контекста. \"",
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
    "        if last_folder:",
    "            user_prompt += \"КОНТЕКСТ_ПАПКИ: мы недавно работали с папкой \" + last_folder + \"\\n\\n\"",
    "",
    "        user_prompt += \"КОНТЕКСТ ИЗ ДОКУМЕНТОВ:\\n\" + context_text + \"\\n\\nВОПРОС: \" + question",
    "",
    "        print(\"Запуск отказоустойчивой генерации (complex_reasoning)...\")",
    "        return self.registry.generate_with_fallback(\"complex_reasoning\", user_prompt, system_prompt)",
])


# ================ AGENT.PY PATCH ================
# Убираем добавление last_folder в историю, передаём его отдельным параметром
OLD_ASK_Q = (
    "    def ask_question(self, question):" + NL +
    "        # Если недавно работали с папкой - подсказываем это LLM" + NL +
    "        hist = list(self.chat_history)" + NL +
    "        if self.last_folder and not any(fp in question for fp in [self.last_folder, os.path.basename(self.last_folder)]):" + NL +
    "            hist.append({'role': 'user', 'content': 'Контекст: недавно мы работали с папкой ' + self.last_folder})" + NL +
    "        return self.rag.ask(question, history=hist)"
)
NEW_ASK_Q = (
    "    def ask_question(self, question):" + NL +
    "        return self.rag.ask(question, history=self.chat_history, last_folder=self.last_folder)"
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
    print("Перезапись rag/qa.py (чистый поиск, last_folder отдельно)...")
    with open("rag/qa.py", "w", encoding="utf-8") as f:
        f.write(QA_PY)
    print("[OK] rag/qa.py")

    print("")
    print("Патчинг core/agent.py...")
    patch("core/agent.py", OLD_ASK_Q, NEW_ASK_Q, "agent: ask_question без мусора в истории")

    print("")
    print("Готово! Запускай: python main.py")
    print("")
    print("Проверка: спроси 'а кто директор?' — в логе должно быть:")
    print("  [RAG] Поиск с контекстом (short=True, pronoun=False): [предыдущий вопрос] а кто директор?")
    print("БЕЗ упоминания D:/DEEPSEEK/AGENT/TEST_FULL")


if __name__ == "__main__":
    main()