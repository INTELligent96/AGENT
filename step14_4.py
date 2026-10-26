import os

NL = "\n"


def patch(path, old, new, label):
    if not os.path.exists(path):
        print("[SKIP] Нет файла: " + path)
        return False
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print("[WARN] " + label + " — фрагмент не найден")
        return False
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[OK] " + label)
    return True


# ============ 1. RAG/QA.PY ============
QA_LINES = [
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
    "GENERIC_WORDS = [",
    "    'что в папке', 'что находится в папке', 'расскажи о папке', 'расскажи про папку',",
    "    'про папку', 'о папке', 'обзор папки', 'перечень файлов', 'список файлов',",
    "    'содержимое папки', 'покажи файлы', 'какие файлы',",
    "]",
    "",
    "",
    "class RAGQuestionAnswerer:",
    "    def __init__(self, config, tools_config, registry):",
    "        self.indexer = RAGIndexer(config, tools_config)",
    "        self.registry = registry",
    "",
    "    def _clean_text(self, text):",
    "        parts = []",
    "        for w in text.split():",
    "            # Windows-путь: D:/foo или C:/foo",
    "            if len(w) >= 3 and w[1] == ':' and not w[2].isalnum():",
    "                continue",
    "            if w.startswith('/') and len(w) > 2:",
    "                continue",
    "            parts.append(w)",
    "        text = ' '.join(parts)",
    "        lower = text.lower()",
    "        for gw in GENERIC_WORDS:",
    "            lower = lower.replace(gw, ' ')",
    "        return ' '.join(lower.split()).strip()",
    "",
    "    def _build_search_query(self, question, history):",
    "        if not history:",
    "            return question",
    "        last_user = None",
    "        for h in reversed(history):",
    "            if h.get('role') == 'user':",
    "                c = h.get('content', '')",
    "                if c.startswith('Контекст:') or c.startswith('[Диалог]'):",
    "                    continue",
    "                last_user = c",
    "                break",
    "        if not last_user:",
    "            return question",
    "        is_short = len(question) < 60",
    "        words = question.lower().split()",
    "        has_pronoun = any(p in words for p in PRONOUNS)",
    "        if is_short or has_pronoun:",
    "            clean_prev = self._clean_text(last_user)",
    "            clean_curr = self._clean_text(question)",
    "            combined = (clean_prev + ' ' + clean_curr).strip()",
    "            if not combined:",
    "                combined = question",
    "            print('  [RAG] Поиск с контекстом: ' + combined[:120])",
    "            return combined",
    "        return question",
    "",
    "    def _get_source_filter(self, folder):",
    "        if not folder:",
    "            return None",
    "        try:",
    "            files = [str(f) for f in Path(folder).rglob('*') if f.is_file()]",
    "            if not files:",
    "                return None",
    "            return {'source': {'$in': files}}",
    "        except Exception:",
    "            return None",
    "",
    "    def ask(self, question, history=None, last_folder=None, folder_filter=None):",
    "        search_query = self._build_search_query(question, history)",
    "        print(\"Поиск по базе: '\" + search_query[:80] + \"'...\")",
    "        where = self._get_source_filter(folder_filter)",
    "        context_chunks = self.indexer.search(search_query, top_k=12, where=where)",
    "        if not context_chunks:",
    "            return 'В базе данных не найдено информации по этому вопросу.'",
    "        print('  [RAG] Источники:')",
    "        for c in context_chunks:",
    "            print('    - ' + Path(c['source']).name + ' (part ' + str(c['chunk_id']) + ')')",
    "        context_text = ''",
    "        for i, chunk in enumerate(context_chunks, 1):",
    "            src = Path(chunk['source']).name",
    "            context_text += '--- Фрагмент ' + str(i) + ' (' + src + ', part ' + str(chunk['chunk_id']) + ') ---\\n'",
    "            context_text += chunk['text'] + '\\n\\n'",
    "        system_prompt = 'Ты - ассистент по документам. Отвечай ТОЛЬКО на основе фрагментов. Прочитай ВСЕ фрагменты. Если ответ есть хотя бы в одном - выведи его. Указывай файл-источник.'",
    "        user_prompt = ''",
    "        if history:",
    "            user_prompt += 'ИСТОРИЯ:\\n'",
    "            for h in history[-6:]:",
    "                role = 'Пользователь' if h['role'] == 'user' else 'Ассистент'",
    "                user_prompt += role + ': ' + str(h['content'])[:300] + '\\n'",
    "            user_prompt += '\\n'",
    "        if last_folder:",
    "            user_prompt += 'КОНТЕКСТ_ПАПКИ: ' + last_folder + '\\n\\n'",
    "        user_prompt += 'КОНТЕКСТ:\\n' + context_text + '\\n\\nВОПРОС: ' + question",
    "        print('Генерация ответа...')",
    "        return self.registry.generate_with_fallback('complex_reasoning', user_prompt, system_prompt)",
    "",
]


# ============ 2. rag/indexer.py (патч search) ============
OLD_SIG = "    def search(self, query: str, top_k: int = 4) -> list[dict]:"
NEW_SIG = "    def search(self, query: str, top_k: int = 4, where: dict = None) -> list[dict]:"

OLD_QUERY = NL.join([
    "        results = self.collection.query(",
    "            query_texts=[query],",
    "            n_results=top_k",
    "        )",
])
NEW_QUERY = NL.join([
    "        kwargs = {'query_texts': [query], 'n_results': top_k}",
    "        if where:",
    "            kwargs['where'] = where",
    "        try:",
    "            results = self.collection.query(**kwargs)",
    "        except Exception as e:",
    "            print('  [RAG] where-фильтр не сработал: ' + str(e))",
    "            results = self.collection.query(query_texts=[query], n_results=top_k)",
])


# ============ 3. core/agent.py ============
OLD_ASK = (
    "    def ask_question(self, question):" + NL +
    "        return self.rag.ask(question, history=self.chat_history, last_folder=self.last_folder)"
)
NEW_ASK = (
    "    def ask_question(self, question, folder_filter=None):" + NL +
    "        return self.rag.ask(question, history=self.chat_history, last_folder=self.last_folder, folder_filter=folder_filter)"
)

OLD_ASK_IN_FOLDER = "rag_answer = self.ask_question(question)"
NEW_ASK_IN_FOLDER = "rag_answer = self.ask_question(question, folder_filter=folder)"

RESET_LINES = [
    "    def reset_rag_db(self):",
    "        try:",
    "            import shutil",
    "            db_path = self.config.get('rag', {}).get('db_path', 'chroma_db')",
    "            if os.path.exists(db_path):",
    "                shutil.rmtree(db_path)",
    "                print('[RAG] База данных удалена: ' + db_path)",
    "            self._rag = None",
    "            self._indexed_folders.clear()",
    "            return 'База RAG очищена. Проиндексируйте папку заново.'",
    "        except Exception as e:",
    "            return '[Ошибка очистки]: ' + str(e)",
    "",
    "",
]
RESET_CODE = NL.join(RESET_LINES)


def main():
    # 1. rag/qa.py — прямая запись
    print("=== 1. rag/qa.py ===")
    with open("rag/qa.py", "w", encoding="utf-8") as f:
        f.write(NL.join(QA_LINES) + NL)
    print("[OK] rag/qa.py перезаписан")

    # 2. rag/indexer.py — 2 патча
    print("")
    print("=== 2. rag/indexer.py ===")
    patch("rag/indexer.py", OLD_SIG, NEW_SIG, "indexer: search + where")
    patch("rag/indexer.py", OLD_QUERY, NEW_QUERY, "indexer: query с фильтром")

    # 3. core/agent.py — 3 патча
    print("")
    print("=== 3. core/agent.py ===")
    patch("core/agent.py", OLD_ASK, NEW_ASK, "agent: ask_question + folder_filter")
    patch("core/agent.py", OLD_ASK_IN_FOLDER, NEW_ASK_IN_FOLDER, "agent: ask_about_folder → folder_filter")

    # Добавляем reset_rag_db
    path = "core/agent.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if "def reset_rag_db" not in content:
        anchor = "    def request_stop(self):"
        if anchor in content:
            content = content.replace(anchor, RESET_CODE + anchor, 1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            print("[OK] agent: reset_rag_db() добавлен")
        else:
            print("[WARN] agent: не найдено место для reset_rag_db")
    else:
        print("[SKIP] agent: reset_rag_db уже есть")

    # 4. gui/app.py — кнопка
    print("")
    print("=== 4. gui/app.py ===")
    path = "gui/app.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "Сбросить базу RAG" in content:
        print("[SKIP] gui: кнопка сброса уже есть")
    else:
        anchor = '        self._add_btn("Сортировка файлов", self.classify_ui, "Разложить по категориям")'
        new_line = anchor + NL + '        self._add_btn("Сбросить базу RAG", self.reset_rag_ui, "Удалить базу и начать заново", color="#B22222")'
        if anchor in content:
            content = content.replace(anchor, new_line, 1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            print("[OK] gui: кнопка добавлена")
        else:
            print("[WARN] gui: не найдена 'Сортировка файлов'")

    # 5. Метод reset_rag_ui в GUI
    path = "gui/app.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if "def reset_rag_ui" not in content:
        anchor = "    def stop_agent(self):"
        new_method = NL.join([
            "    def reset_rag_ui(self):",
            "        if not messagebox.askyesno('Подтверждение', 'Удалить базу RAG?\\nПридётся переиндексировать папки.'):",
            "            return",
            "        result = self.agent.reset_rag_db()",
            "        self.log('[Система] ' + result)",
            "",
            "",
        ])
        if anchor in content:
            content = content.replace(anchor, new_method + anchor, 1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            print("[OK] gui: метод reset_rag_ui добавлен")
        else:
            print("[WARN] gui: не найден stop_agent")
    else:
        print("[SKIP] gui: reset_rag_ui уже есть")

    print("")
    print("=" * 60)
    print("ГОТОВО! Запускай: python main.py")
    print("=" * 60)
    print("")
    print("ВАЖНО ПЕРЕД ТЕСТОМ:")
    print("1. Нажми в GUI 'Сбросить базу RAG' — удалит старые чанки (DataCRC000.txt и др.)")
    print("2. Заново проиндексируй TEST_FULL: 'проиндексируй папку D:/DEEPSEEK/AGENT/TEST_FULL'")
    print("3. Спроси: 'что в папке D:/.../TEST_FULL? в каком году основана компания?'")
    print("4. Спроси: 'а кто директор?'")
    print("")
    print("В логе теперь будет [RAG] Источники: список всех файлов, откуда взяты чанки.")


if __name__ == "__main__":
    main()