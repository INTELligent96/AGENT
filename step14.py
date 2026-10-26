import os

NL = "\n"


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


# ================ AGENT.PY ================

# 1. Добавляем pending_tool и chat_history
agent_old_1 = (
    "        self.allowed_paths = [p.strip() for p in safety.get(\"allowed_paths\", []) if str(p).strip()]" + NL +
    "        self._indexed_folders = set()"
)
agent_new_1 = (
    "        self.allowed_paths = [p.strip() for p in safety.get(\"allowed_paths\", []) if str(p).strip()]" + NL +
    "        self._indexed_folders = set()" + NL +
    "        self.pending_tool = None   # инструмент, ожидающий аргумент (папка/файл)" + NL +
    "        self.chat_history = []     # [{'role': 'user'/'assistant', 'content': '...'}, ...]" + NL +
    "        self.max_history = 5       # сколько последних пар хранить"
)

# 2. Добавляем проверку pending_tool в начале run_task
agent_old_2 = (
    "    def run_task(self, user_text, log_callback=None):" + NL +
    "        def log(msg):" + NL +
    "            print(msg)" + NL +
    "            if log_callback:" + NL +
    "                log_callback(msg)"
)
agent_new_2 = (
    "    def run_task(self, user_text, log_callback=None):" + NL +
    "        def log(msg):" + NL +
    "            print(msg)" + NL +
    "            if log_callback:" + NL +
    "                log_callback(msg)" + NL +
    NL +
    "        # === Проверка: может быть, это ответ на 'Укажите папку/файл'? ===" + NL +
    "        if self.pending_tool:" + NL +
    "            resolved = self._try_resolve_pending(user_text, log)" + NL +
    "            if resolved is not None:" + NL +
    "                self._append_history(user_text, str(resolved))" + NL +
    "                return resolved"
)

# 3. Заменяем ask_question на версию с историей
agent_old_3 = (
    "    def ask_question(self, question):" + NL +
    "        return self.rag.ask(question)"
)
agent_new_3 = (
    "    def ask_question(self, question):" + NL +
    "        return self.rag.ask(question, history=self.chat_history)" + NL +
    NL +
    "    def _append_history(self, user, assistant):" + NL +
    "        self.chat_history.append({'role': 'user', 'content': str(user)})" + NL +
    "        self.chat_history.append({'role': 'assistant', 'content': str(assistant)})" + NL +
    "        # Обрезаем по парам" + NL +
    "        max_len = self.max_history * 2" + NL +
    "        if len(self.chat_history) > max_len:" + NL +
    "            self.chat_history = self.chat_history[-max_len:]" + NL +
    NL +
    "    def _try_resolve_pending(self, user_text, log):" + NL +
    "        tool = self.pending_tool" + NL +
    "        arg = user_text.strip().strip('\"').strip(\"'\")" + NL +
    NL +
    "        # Если в тексте есть команда (а не только путь) — отдаём роутеру" + NL +
    "        lower = user_text.lower()" + NL +
    "        command_words = ['проверь', 'сделай', 'напиши', 'построй', 'найди', 'создай', 'посчитай', 'переведи', 'отсортируй', 'разложи']" + NL +
    "        if any(w in lower for w in command_words):" + NL +
    "            self.pending_tool = None" + NL +
    "            return None" + NL +
    NL +
    "        self.pending_tool = None" + NL +
    "        log('[Диалог] Использую введённый путь: ' + arg)" + NL +
    NL +
    "        try:" + NL +
    "            if tool == 'make_file_list':" + NL +
    "                return self.make_file_list(arg, recursive=True)" + NL +
    "            if tool == 'classify_files':" + NL +
    "                return self.classify_files(arg)" + NL +
    "            if tool == 'batch_summarize':" + NL +
    "                return self.batch_summarize(arg)" + NL +
    "            if tool == 'index_folder':" + NL +
    "                return self.index_folder(arg)" + NL +
    "            if tool == 'make_excel_chart':" + NL +
    "                return self.make_excel_chart(arg)" + NL +
    "            if tool == 'summarize_file':" + NL +
    "                return self.summarize_file(arg)" + NL +
    "            if tool == 'check_spelling':" + NL +
    "                return self.check_spelling_file(arg)" + NL +
    "            if tool == 'process_long_doc':" + NL +
    "                return self.process_long_document(arg)" + NL +
    "            if tool == 'ask_about_folder':" + NL +
    "                return self.ask_about_folder('что в папке ' + arg + '?')" + NL +
    "        except Exception as e:" + NL +
    "            return '[Ошибка] ' + str(e)" + NL +
    "        return None"
)

# 4. Меняем "Укажите папку/файл" на запоминание pending_tool
# 4.1: batch_summarize
agent_old_4a = (
    "        if tool_name == \"batch_summarize\":" + NL +
    "            f = self._extract_folder_from_text(user_text) or self._extract_path_from_text(user_text)" + NL +
    "            if not f: return \"Укажите папку.\"" + NL +
    "            return self.batch_summarize(f)"
)
agent_new_4a = (
    "        if tool_name == \"batch_summarize\":" + NL +
    "            f = self._extract_folder_from_text(user_text) or self._extract_path_from_text(user_text)" + NL +
    "            if not f:" + NL +
    "                self.pending_tool = 'batch_summarize'" + NL +
    "                return \"Укажите папку. Напишите путь следующим сообщением (например: D:/Docs) или повторите команду с путём.\"" + NL +
    "            return self.batch_summarize(f)"
)

# 4.2: classify_files
agent_old_4b = (
    "        if tool_name == \"classify_files\":" + NL +
    "            f = self._extract_folder_from_text(user_text)" + NL +
    "            if not f: return \"Укажите папку.\"" + NL +
    "            return self.classify_files(f)"
)
agent_new_4b = (
    "        if tool_name == \"classify_files\":" + NL +
    "            f = self._extract_folder_from_text(user_text)" + NL +
    "            if not f:" + NL +
    "                self.pending_tool = 'classify_files'" + NL +
    "                return \"Укажите папку. Напишите путь следующим сообщением.\"" + NL +
    "            return self.classify_files(f)"
)

# 4.3: make_file_list
agent_old_4c = (
    "        if tool_name == \"make_file_list\":" + NL +
    "            f = self._extract_folder_from_text(user_text)" + NL +
    "            if not f: return \"Укажите папку.\"" + NL +
    "            return self.make_file_list(f, recursive=True)"
)
agent_new_4c = (
    "        if tool_name == \"make_file_list\":" + NL +
    "            f = self._extract_folder_from_text(user_text)" + NL +
    "            if not f:" + NL +
    "                self.pending_tool = 'make_file_list'" + NL +
    "                return \"Укажите папку. Напишите путь следующим сообщением.\"" + NL +
    "            return self.make_file_list(f, recursive=True)"
)

# 4.4: summarize_file
agent_old_4d = (
    "        if tool_name == \"summarize_file\":" + NL +
    "            fp = self._extract_path_from_text(user_text)" + NL +
    "            if not fp:" + NL +
    "                return \"Укажите файл: 'сделай резюме путь/к/файлу'\""
)
agent_new_4d = (
    "        if tool_name == \"summarize_file\":" + NL +
    "            fp = self._extract_path_from_text(user_text)" + NL +
    "            if not fp:" + NL +
    "                self.pending_tool = 'summarize_file'" + NL +
    "                return \"Укажите файл. Напишите путь следующим сообщением.\""
)

# 4.5: check_spelling
agent_old_4e = (
    "        if tool_name == \"check_spelling\":" + NL +
    "            fp = self._extract_path_from_text(user_text)" + NL +
    "            if not fp:" + NL +
    "                return \"Укажите файл: 'проверь ошибки путь/к/файлу'\""
)
agent_new_4e = (
    "        if tool_name == \"check_spelling\":" + NL +
    "            fp = self._extract_path_from_text(user_text)" + NL +
    "            if not fp:" + NL +
    "                self.pending_tool = 'check_spelling'" + NL +
    "                return \"Укажите файл. Напишите путь следующим сообщением.\""
)


# ================ RAG/QA.PY ================

QA_PY = NL.join([
    "from pathlib import Path",
    "from .indexer import RAGIndexer",
    "from llm.registry import LLMRegistry",
    "",
    "",
    "class RAGQuestionAnswerer:",
    "    def __init__(self, config: dict, tools_config: dict, registry: LLMRegistry):",
    "        self.indexer = RAGIndexer(config, tools_config)",
    "        self.registry = registry",
    "",
    "    def ask(self, question: str, history=None) -> str:",
    "        print(\"Поиск по базе для вопроса: '\" + question[:60] + \"'...\")",
    "        context_chunks = self.indexer.search(question, top_k=5)",
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
    "            \"Если в тексте нет ответа, честно скажи, что не знаешь. \"",
    "            \"Обязательно указывай, из какого файла взята информация. \"",
    "            \"Отвечай кратко и по делу.\"",
    "        )",
    "",
    "        user_prompt = \"\"",
    "        if history:",
    "            user_prompt += \"ИСТОРИЯ ДИАЛОГА (для понимания контекста):\\n\"",
    "            for h in history[-6:]:",
    "                role = \"Пользователь\" if h[\"role\"] == \"user\" else \"Ассистент\"",
    "                content = str(h[\"content\"])[:300]",
    "                user_prompt += role + \": \" + content + \"\\n\"",
    "            user_prompt += \"\\n\"",
    "",
    "        user_prompt += \"КОНТЕКСТ:\\n\" + context_text + \"\\n\\nВОПРОС: \" + question",
    "",
    "        print(\"Запуск отказоустойчивой генерации (complex_reasoning)...\")",
    "        return self.registry.generate_with_fallback(\"complex_reasoning\", user_prompt, system_prompt)",
])


# ================ GUI/APP.PY PATCH ================

# 1. Кнопки копирования/сохранения в sandbox_frame (рядом с sandbox)
gui_old_1 = (
    "        btn = ctk.CTkButton(row, text=\"Применить\", width=110, command=self.save_sandbox_paths)" + NL +
    "        btn.pack(side=\"right\")" + NL +
    "        ToolTip(btn, \"Сохранить список разрешённых папок. Агент не сможет работать с файлами вне их.\")"
)
gui_new_1 = (
    "        btn = ctk.CTkButton(row, text=\"Применить\", width=110, command=self.save_sandbox_paths)" + NL +
    "        btn.pack(side=\"right\")" + NL +
    "        ToolTip(btn, \"Сохранить список разрешённых папок. Агент не сможет работать с файлами вне их.\")" + NL +
    NL +
    "        chat_btns = ctk.CTkFrame(self.sandbox_frame, fg_color=\"transparent\")" + NL +
    "        chat_btns.pack(fill=\"x\", padx=10, pady=(0, 8))" + NL +
    "        ctk.CTkButton(chat_btns, text=\"Копировать чат\", width=130, command=self.copy_chat).pack(side=\"left\", padx=(0, 5))" + NL +
    "        ctk.CTkButton(chat_btns, text=\"Сохранить чат в файл\", width=170, command=self.save_chat_to_file).pack(side=\"left\")"
)

# 2. Возврат фокуса в user_input после log()
gui_old_2 = (
    "    def log(self, text):" + NL +
    "        def _update():" + NL +
    "            self.chat_display.configure(state=\"normal\")" + NL +
    "            self.chat_display.insert(\"end\", text + \"\\n\")" + NL +
    "            self.chat_display.see(\"end\")" + NL +
    "            self.chat_display.configure(state=\"disabled\")" + NL +
    "        self.after(0, _update)"
)
gui_new_2 = (
    "    def log(self, text):" + NL +
    "        def _update():" + NL +
    "            self.chat_display.configure(state=\"normal\")" + NL +
    "            self.chat_display.insert(\"end\", text + \"\\n\")" + NL +
    "            self.chat_display.see(\"end\")" + NL +
    "            self.chat_display.configure(state=\"disabled\")" + NL +
    "            try:" + NL +
    "                self.user_input.focus_set()" + NL +
    "            except Exception:" + NL +
    "                pass" + NL +
    "        self.after(0, _update)" + NL +
    NL +
    "    def copy_chat(self):" + NL +
    "        try:" + NL +
    "            text = self.chat_display.get(\"1.0\", \"end\")" + NL +
    "            self.clipboard_clear()" + NL +
    "            self.clipboard_append(text)" + NL +
    "            self.log(\"[Система] Чат скопирован в буфер обмена.\")" + NL +
    "        except Exception as e:" + NL +
    "            self.log(\"[Ошибка] Не удалось скопировать: \" + str(e))" + NL +
    NL +
    "    def save_chat_to_file(self):" + NL +
    "        from datetime import datetime" + NL +
    "        import os as _os" + NL +
    "        try:" + NL +
    "            _os.makedirs(self.agent.output_dir, exist_ok=True)" + NL +
    "            fname = \"chat_\" + datetime.now().strftime(\"%Y%m%d_%H%M%S\") + \".txt\"" + NL +
    "            fpath = _os.path.join(self.agent.output_dir, fname)" + NL +
    "            text = self.chat_display.get(\"1.0\", \"end\")" + NL +
    "            with open(fpath, \"w\", encoding=\"utf-8\") as f:" + NL +
    "                f.write(text)" + NL +
    "            self.log(\"[Система] Чат сохранён: \" + fpath)" + NL +
    "        except Exception as e:" + NL +
    "            self.log(\"[Ошибка] Не удалось сохранить: \" + str(e))"
)

# 3. Добавляем сохранение истории в Agent после ответа + автосохранение при закрытии
gui_old_3 = (
    "    def send_message(self):" + NL +
    "        text = self.user_input.get()" + NL +
    "        if not text.strip():" + NL +
    "            return" + NL +
    "        self.user_input.delete(0, \"end\")" + NL +
    "        self.log(\"\\nВы: \" + text)" + NL +
    NL +
    "        routing_preview = self.agent.router.classify(text)" + NL +
    "        dangerous_hit = [t for t in routing_preview[\"tools\"] if t in self.agent.router.dangerous_tools]" + NL +
    "        if dangerous_hit:" + NL +
    "            ok = messagebox.askyesno(\"Подтверждение\", \"Агент хочет выполнить: \" + str(dangerous_hit) + \"\\nРазрешить?\")" + NL +
    "            if not ok:" + NL +
    "                self.log(\"[Отменено пользователем]\")" + NL +
    "                return" + NL +
    NL +
    "        def task():" + NL +
    "            result = self.agent.run_task(text, log_callback=self.log)" + NL +
    "            self.log(\"\\nАгент: \" + result)" + NL +
    "        threading.Thread(target=task, daemon=True).start()"
)
gui_new_3 = (
    "    def send_message(self):" + NL +
    "        text = self.user_input.get()" + NL +
    "        if not text.strip():" + NL +
    "            return" + NL +
    "        self.user_input.delete(0, \"end\")" + NL +
    "        self.log(\"\\nВы: \" + text)" + NL +
    NL +
    "        routing_preview = self.agent.router.classify(text)" + NL +
    "        dangerous_hit = [t for t in routing_preview[\"tools\"] if t in self.agent.router.dangerous_tools]" + NL +
    "        if dangerous_hit:" + NL +
    "            ok = messagebox.askyesno(\"Подтверждение\", \"Агент хочет выполнить: \" + str(dangerous_hit) + \"\\nРазрешить?\")" + NL +
    "            if not ok:" + NL +
    "                self.log(\"[Отменено пользователем]\")" + NL +
    "                return" + NL +
    NL +
    "        def task():" + NL +
    "            result = self.agent.run_task(text, log_callback=self.log)" + NL +
    "            self.log(\"\\nАгент: \" + result)" + NL +
    "            try:" + NL +
    "                self.agent._append_history(text, result)" + NL +
    "            except Exception:" + NL +
    "                pass" + NL +
    "        threading.Thread(target=task, daemon=True).start()"
)

# 4. Автосохранение чата при закрытии + кнопка "Копировать чат"
gui_old_4 = (
    "        self.btn_send = ctk.CTkButton(self.input_frame, text=\"Отправить\", width=100, command=self.send_message)" + NL +
    "        self.btn_send.grid(row=0, column=1)"
)
gui_new_4 = (
    "        self.btn_send = ctk.CTkButton(self.input_frame, text=\"Отправить\", width=100, command=self.send_message)" + NL +
    "        self.btn_send.grid(row=0, column=1)" + NL +
    NL +
    "        self.protocol(\"WM_DELETE_WINDOW\", self._on_closing)" + NL +
    NL +
    "    def _on_closing(self):" + NL +
    "        try:" + NL +
    "            self.save_chat_to_file()" + NL +
    "        except Exception:" + NL +
    "            pass" + NL +
    "        self.destroy()"
)


def main():
    print("Патчинг core/agent.py...")
    patch("core/agent.py", agent_old_1, agent_new_1, "agent: pending_tool + chat_history")
    patch("core/agent.py", agent_old_2, agent_new_2, "agent: run_task с pending")
    patch("core/agent.py", agent_old_3, agent_new_3, "agent: ask_question + _try_resolve_pending")
    patch("core/agent.py", agent_old_4a, agent_new_4a, "agent: batch_summarize pending")
    patch("core/agent.py", agent_old_4b, agent_new_4b, "agent: classify_files pending")
    patch("core/agent.py", agent_old_4c, agent_new_4c, "agent: make_file_list pending")
    patch("core/agent.py", agent_old_4d, agent_new_4d, "agent: summarize_file pending")
    patch("core/agent.py", agent_old_4e, agent_new_4e, "agent: check_spelling pending")

    print("")
    print("Перезапись rag/qa.py...")
    with open("rag/qa.py", "w", encoding="utf-8") as f:
        f.write(QA_PY)
    print("[OK] rag/qa.py перезаписан (история диалога)")

    print("")
    print("Патчинг gui/app.py...")
    patch("gui/app.py", gui_old_1, gui_new_1, "gui: кнопки копирования/сохранения")
    patch("gui/app.py", gui_old_2, gui_new_2, "gui: фокус + copy_chat + save_chat")
    patch("gui/app.py", gui_old_3, gui_new_3, "gui: сохранение истории")
    patch("gui/app.py", gui_old_4, gui_new_4, "gui: автосохранение при закрытии")

    print("")
    print("Готово! Запускай: python main.py")
    print("")
    print("Проверки:")
    print("1. Спроси: 'сделай список файлов' → агент ответит 'Укажите папку'")
    print("2. Следующим сообщением: 'D:/TEST_FULL' → агент выполнит make_file_list")
    print("3. Спроси: 'что в папке X?' → 'а кто директор?' (2-й вопрос поймёт контекст)")
    print("4. Кнопка 'Копировать чат' — скопирует весь текст в буфер")
    print("5. Закрой окно — чат автосохранится в output/chat_*.txt")


if __name__ == "__main__":
    main()