import os


NL = "\n"


def patch_file(path, old, new):
    if not os.path.exists(path):
        print("  [SKIP] Файл не найден: " + path)
        return False
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print("  [WARN] Не найден фрагмент в " + path)
        print("         Возможно, файл был изменён вручную.")
        return False
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("  [OK] Патчен: " + path)
    return True


# ============================================================
# ROUTER.PY — 2 патча
# ============================================================

router_old_1 = (
    '        self.use_llm = self.router_config.get("use_llm_for_ambiguous", True)' + NL +
    NL +
    '    def classify(self, user_text: str) -> dict:' + NL +
    '        text = user_text.lower()' + NL +
    NL +
    '        matched = []' + NL +
    '        for tool, keywords in KEYWORD_RULES.items():' + NL +
    '            if any(kw in text for kw in keywords):' + NL +
    '                matched.append(tool)'
)

router_new_1 = (
    '        self.use_llm = self.router_config.get("use_llm_for_ambiguous", True)' + NL +
    '        self.plugins = {}' + NL +
    NL +
    '    def attach_plugins(self, plugins):' + NL +
    '        self.plugins = plugins' + NL +
    '        for name, plugin in plugins.items():' + NL +
    '            if getattr(plugin, "dangerous", False) and name not in self.dangerous_tools:' + NL +
    '                self.dangerous_tools.append(name)' + NL +
    NL +
    '    def get_keyword_rules(self):' + NL +
    '        rules = dict(KEYWORD_RULES)' + NL +
    '        for name, plugin in self.plugins.items():' + NL +
    '            if plugin.keywords:' + NL +
    '                rules[name] = [kw.lower() for kw in plugin.keywords]' + NL +
    '        return rules' + NL +
    NL +
    '    def classify(self, user_text: str) -> dict:' + NL +
    '        text = user_text.lower()' + NL +
    '        rules = self.get_keyword_rules()' + NL +
    NL +
    '        matched = []' + NL +
    '        for tool, keywords in rules.items():' + NL +
    '            if any(kw in text for kw in keywords):' + NL +
    '                matched.append(tool)'
)

router_old_2 = (
    '            return self._classify_with_llm(user_text)' + NL +
    NL +
    '        return {' + NL +
    '            "tools": ["ask_question"],' + NL +
    '            "reasoning": "По умолчанию: RAG-поиск по документам",' + NL +
    '            "ambiguous": True' + NL +
    '        }' + NL +
    NL +
    '    def _classify_with_llm(self, user_text: str) -> dict:' + NL +
    '        tools_desc = "\\n".join([f"- {t}: {\', \'.join(kw[:2])}" for t, kw in KEYWORD_RULES.items()])'
)

router_new_2 = (
    '            return self._classify_with_llm(user_text, rules)' + NL +
    NL +
    '        return {' + NL +
    '            "tools": ["ask_question"],' + NL +
    '            "reasoning": "По умолчанию: RAG-поиск по документам",' + NL +
    '            "ambiguous": True' + NL +
    '        }' + NL +
    NL +
    '    def _classify_with_llm(self, user_text: str, rules: dict) -> dict:' + NL +
    '        tools_desc = "\\n".join([f"- {t}: {\', \'.join(kw[:2])}" for t, kw in rules.items()])'
)


# ============================================================
# AGENT.PY — 3 патча
# ============================================================

agent_old_1 = 'from rag.qa import RAGQuestionAnswerer'
agent_new_1 = (
    'from rag.qa import RAGQuestionAnswerer' + NL +
    'from plugins.loader import load_plugins'
)

agent_old_2 = (
    '        self.critic = Critic(self.registry, self.config)' + NL +
    NL +
    '        safety = self.config.get("safety", {})'
)
agent_new_2 = (
    '        self.critic = Critic(self.registry, self.config)' + NL +
    NL +
    '        plugins_dir = self.config.get("plugins", {}).get("dir", "plugins")' + NL +
    '        self.plugins = load_plugins(plugins_dir)' + NL +
    '        self.router.attach_plugins(self.plugins)' + NL +
    NL +
    '        safety = self.config.get("safety", {})'
)

agent_old_3 = (
    '    def _execute_tool(self, tool_name: str, user_text: str, log) -> str:' + NL +
    '        if tool_name == "ask_question":'
)
agent_new_3 = (
    '    def _execute_tool(self, tool_name: str, user_text: str, log) -> str:' + NL +
    '        if tool_name in self.plugins:' + NL +
    '            plugin = self.plugins[tool_name]' + NL +
    '            log("[Плагин] Выполняю: " + plugin.name)' + NL +
    '            try:' + NL +
    '                return plugin.execute(user_text, self)' + NL +
    '            except Exception as e:' + NL +
    '                return "[Ошибка плагина " + plugin.name + "]: " + str(e)' + NL +
    '        if tool_name == "ask_question":'
)


# ============================================================
# GUI/APP.PY — 3 патча
# ============================================================

gui_old_1 = (
    '        self._add_btn("Веб-поиск", self.web_search_ui, "Поиск в интернете")' + NL +
    NL +
    '        ctk.CTkLabel(self.sidebar, text="Настройки:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)'
)
gui_new_1 = (
    '        self._add_btn("Веб-поиск", self.web_search_ui, "Поиск в интернете")' + NL +
    NL +
    '        gui_plugins = {n: p for n, p in self.agent.plugins.items() if getattr(p, "gui_enabled", False)}' + NL +
    '        if gui_plugins:' + NL +
    '            ctk.CTkLabel(self.sidebar, text="Плагины:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)' + NL +
    '            for pname, plugin in gui_plugins.items():' + NL +
    '                btn_text = plugin.gui_button_text or plugin.name' + NL +
    '                self._add_btn(btn_text, lambda n=pname: self.run_plugin_from_gui(n), plugin.description or "", color="#8B4513")' + NL +
    NL +
    '        ctk.CTkLabel(self.sidebar, text="Настройки:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)'
)

gui_old_2 = '        self._add_btn("Добавить LLM (API)", self.open_add_llm_window, "Подключить API", color="green")'
gui_new_2 = (
    '        self._add_btn("Добавить LLM (API)", self.open_add_llm_window, "Подключить API", color="green")' + NL +
    '        self._add_btn("Список плагинов", self.show_plugins_window, "Посмотреть загруженные плагины")'
)

gui_old_3 = (
    '    def stop_agent(self):' + NL +
    '        self.agent.request_stop()'
)
gui_new_3 = (
    '    def run_plugin_from_gui(self, plugin_name):' + NL +
    '        plugin = self.agent.plugins[plugin_name]' + NL +
    '        file_path = filedialog.askopenfilename(title=plugin.gui_button_text or plugin_name)' + NL +
    '        if not file_path:' + NL +
    '            return' + NL +
    '        self.log("\\n[Плагин: " + plugin_name + "] Файл: " + os.path.basename(file_path))' + NL +
    '        def task():' + NL +
    '            try:' + NL +
    '                result = plugin.execute(file_path, self.agent)' + NL +
    '                self.log("[Плагин: " + plugin_name + "] Результат:\\n" + result)' + NL +
    '            except Exception as e:' + NL +
    '                self.log("[Плагин: " + plugin_name + "] Ошибка: " + str(e))' + NL +
    '        threading.Thread(target=task, daemon=True).start()' + NL +
    NL +
    '    def show_plugins_window(self):' + NL +
    '        win = ctk.CTkToplevel(self)' + NL +
    '        win.title("Загруженные плагины")' + NL +
    '        win.geometry("600x500")' + NL +
    '        win.attributes("-topmost", True)' + NL +
    '        if not self.agent.plugins:' + NL +
    '            ctk.CTkLabel(win, text="Плагины не загружены.\\nПоложи .py файлы в папку plugins/", font=("Arial", 14)).pack(pady=40)' + NL +
    '            return' + NL +
    '        textbox = ctk.CTkTextbox(win, font=("Consolas", 12))' + NL +
    '        textbox.pack(fill="both", expand=True, padx=10, pady=10)' + NL +
    '        for name, plugin in self.agent.plugins.items():' + NL +
    '            info = "Имя: " + name + "\\n"' + NL +
    '            info += "Описание: " + (plugin.description or "—") + "\\n"' + NL +
    '            info += "Ключевые слова: " + ", ".join(plugin.keywords or []) + "\\n"' + NL +
    '            info += "GUI-кнопка: " + ("Да (" + (plugin.gui_button_text or name) + ")" if plugin.gui_enabled else "Нет") + "\\n"' + NL +
    '            info += "Опасный: " + ("Да" if plugin.dangerous else "Нет") + "\\n"' + NL +
    '            info += "-" * 60 + "\\n"' + NL +
    '            textbox.insert("end", info)' + NL +
    '        textbox.configure(state="disabled")' + NL +
    NL +
    '    def stop_agent(self):' + NL +
    '        self.agent.request_stop()'
)


# ============================================================
# MAIN
# ============================================================

def main():
    print("Патчинг core/router.py...")
    patch_file("core/router.py", router_old_1, router_new_1)
    patch_file("core/router.py", router_old_2, router_new_2)

    print("\nПатчинг core/agent.py...")
    patch_file("core/agent.py", agent_old_1, agent_new_1)
    patch_file("core/agent.py", agent_old_2, agent_new_2)
    patch_file("core/agent.py", agent_old_3, agent_new_3)

    print("\nПатчинг gui/app.py...")
    patch_file("gui/app.py", gui_old_1, gui_new_1)
    patch_file("gui/app.py", gui_old_2, gui_new_2)
    patch_file("gui/app.py", gui_old_3, gui_new_3)

    print("\nГотово! Запускай: python main.py")
    print("В консоли должна появиться строка:")
    print("  [Плагины] Загружен: word_count (word_count.py)")
    print("  [Плагины] Всего загружено: 1")
    print("\nЕсли видишь [WARN] — значит файл был изменён вручную.")
    print("Скинь мне сообщение, помогу разобраться.")


if __name__ == "__main__":
    main()