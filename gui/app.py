import customtkinter as ctk
import threading
import os
from tkinter import filedialog, messagebox
from core.agent import Agent
from gui.config_manager import add_llm_profile, load_config, save_config
from gui.tooltip import ToolTip
from gui.style_manager import StyleManagerWindow


class AgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI Document Agent PRO")
        self.geometry("1200x800")
        self.agent = Agent("config.yaml")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        self.sidebar = ctk.CTkScrollableFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")

        self.footer = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.footer.grid(row=2, column=0, sticky="ew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="AGENT PANEL", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.pack(padx=20, pady=(20, 10))

        ctk.CTkLabel(self.sidebar, text="Проверка ответов:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(10, 0), anchor="w", padx=20)

        cfg = load_config()
        self.var_enabled = ctk.BooleanVar(value=cfg.get("self_check", {}).get("enabled", True))
        self.var_force = ctk.BooleanVar(value=cfg.get("self_check", {}).get("force_always", False))

        chk_enabled = ctk.CTkCheckBox(self.sidebar, text="Включить критика", variable=self.var_enabled, command=self._on_critic_toggle)
        chk_enabled.pack(padx=20, pady=5, anchor="w")
        ToolTip(chk_enabled, "Главный выключатель проверки ответов ИИ.")

        chk_force = ctk.CTkCheckBox(self.sidebar, text="Всегда (даже для кода)", variable=self.var_force, command=self._on_critic_toggle)
        chk_force.pack(padx=20, pady=5, anchor="w")
        ToolTip(chk_force, "Проверять даже код. Медленнее, но строже.")

        ctk.CTkLabel(self.sidebar, text="Базовые функции:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Индексировать папку", self.index_folder, "Прочитать файлы для RAG")
        self._add_btn("Проверить орфографию", self.check_spell, "Найти ошибки")
        self._add_btn("Написать код", self.write_code, "Сгенерировать Python-код")
        self._add_btn("Полный разбор документа", self.process_long_doc, "Резюме больших книг", color="#8A2BE2")

        ctk.CTkLabel(self.sidebar, text="Word Студия:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Студия стилей Word", self.open_style_studio, "Замена стилей, нумерация", color="#B8860B")

        ctk.CTkLabel(self.sidebar, text="Данные:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Список файлов (CSV)", self.make_file_list_ui, "Создать CSV со списком")
        self._add_btn("График в Excel", self.make_excel_chart_ui, "Построить график")
        self._add_btn("Пакетное резюме", self.batch_summary_ui, "Резюме папки в Word")
        self._add_btn("Сортировка файлов", self.classify_ui, "Разложить по категориям")
        self._add_btn("Веб-поиск", self.web_search_ui, "Поиск в интернете")

        gui_plugins = {n: p for n, p in self.agent.plugins.items() if getattr(p, "gui_enabled", False)}
        if gui_plugins:
            ctk.CTkLabel(self.sidebar, text="Плагины:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
            for pname, plugin in gui_plugins.items():
                btn_text = plugin.gui_button_text or plugin.name
                self._add_btn(btn_text, lambda n=pname: self.run_plugin_from_gui(n), plugin.description or "", color="#8B4513")

        ctk.CTkLabel(self.sidebar, text="Настройки:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Добавить LLM (API)", self.open_add_llm_window, "Подключить API", color="green")
        self._add_btn("Список плагинов", self.show_plugins_window, "Загруженные плагины")

        self.btn_stop = ctk.CTkButton(self.footer, text="ЭКСТРЕННЫЙ СТОП", fg_color="red", hover_color="darkred", command=self.stop_agent)
        self.btn_stop.pack(padx=15, pady=15, fill="x")

        # === SANDBOX PANEL (справа сверху) ===
        self.sandbox_frame = ctk.CTkFrame(self)
        self.sandbox_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=(10, 0))
        self._build_sandbox_bar()

        # === CHAT ===
        self.chat_frame = ctk.CTkFrame(self)
        self.chat_frame.grid(row=1, column=1, rowspan=2, sticky="nsew", padx=10, pady=10)
        self.chat_frame.grid_rowconfigure(0, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(self.chat_frame, state="disabled", wrap="word", font=("Consolas", 14))
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        self.input_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.user_input = ctk.CTkEntry(self.input_frame, placeholder_text="Спросите или дайте команду")
        self.user_input.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.user_input.bind("<Return>", lambda e: self.send_message())

        self.btn_send = ctk.CTkButton(self.input_frame, text="Отправить", width=100, command=self.send_message)
        self.btn_send.grid(row=0, column=1)

    def _build_sandbox_bar(self):
        label = ctk.CTkLabel(self.sandbox_frame, text="🔒 Разрешённые директории (по одной на строку, пусто = без ограничений):", font=("Arial", 12))
        label.pack(anchor="w", padx=10, pady=(8, 0))

        row = ctk.CTkFrame(self.sandbox_frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=8)

        self.sandbox_text = ctk.CTkTextbox(row, height=50, font=("Consolas", 11))
        self.sandbox_text.pack(side="left", fill="x", expand=True, padx=(0, 10))

        btn = ctk.CTkButton(row, text="Применить", width=110, command=self.save_sandbox_paths)
        btn.pack(side="right")
        ToolTip(btn, "Сохранить список разрешённых папок. Агент не сможет работать с файлами вне их.")

        current = self.agent.allowed_paths
        if current:
            self.sandbox_text.insert("1.0", "\n".join(current))

    def save_sandbox_paths(self):
        raw = self.sandbox_text.get("1.0", "end").strip()
        paths = [p.strip() for p in raw.splitlines() if p.strip()]
        self.agent.set_allowed_paths(paths)
        if paths:
            self.log("[Настройки] Разрешено: " + ", ".join(paths))
        else:
            self.log("[Настройки] Ограничений нет. Доступ к любым папкам.")

    def _on_critic_toggle(self):
        cfg = load_config()
        if "self_check" not in cfg:
            cfg["self_check"] = {}
        cfg["self_check"]["enabled"] = self.var_enabled.get()
        cfg["self_check"]["force_always"] = self.var_force.get()
        save_config(cfg)
        self.agent.critic.enabled = self.var_enabled.get()
        self.agent.critic.force_always = self.var_force.get()
        self.log("[Настройки] Критик: " + ("ВКЛ" if self.var_enabled.get() else "ВЫКЛ") + ", force=" + str(self.var_force.get()))

    def _add_btn(self, text, command, hint, color=None):
        btn = ctk.CTkButton(self.sidebar, text=text, command=command)
        if color:
            hover = "darkgreen" if color == "green" else ("#4B0082" if color == "#8A2BE2" else "#6B3410")
            btn.configure(fg_color=color, hover_color=hover)
        btn.pack(padx=20, pady=5, fill="x")
        ToolTip(btn, hint)

    def log(self, text):
        def _update():
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", text + "\n")
            self.chat_display.see("end")
            self.chat_display.configure(state="disabled")
        self.after(0, _update)

    def run_in_thread(self, func, *args):
        def wrapper():
            try:
                func(*args)
            except Exception as e:
                self.log("\n[ОШИБКА]: " + str(e) + "\n")
        threading.Thread(target=wrapper, daemon=True).start()

    def run_plugin_from_gui(self, plugin_name):
        plugin = self.agent.plugins[plugin_name]
        file_path = filedialog.askopenfilename(title=plugin.gui_button_text or plugin_name)
        if not file_path:
            return
        self.log("\n[Плагин: " + plugin_name + "] Файл: " + os.path.basename(file_path))
        def task():
            try:
                result = plugin.execute(file_path, self.agent)
                self.log("[Плагин: " + plugin_name + "] Результат:\n" + result)
            except Exception as e:
                self.log("[Плагин: " + plugin_name + "] Ошибка: " + str(e))
        threading.Thread(target=task, daemon=True).start()

    def show_plugins_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Загруженные плагины")
        win.geometry("600x500")
        win.attributes("-topmost", True)
        if not self.agent.plugins:
            ctk.CTkLabel(win, text="Плагины не загружены.", font=("Arial", 14)).pack(pady=40)
            return
        textbox = ctk.CTkTextbox(win, font=("Consolas", 12))
        textbox.pack(fill="both", expand=True, padx=10, pady=10)
        for name, plugin in self.agent.plugins.items():
            info = "Имя: " + name + "\n"
            info += "Описание: " + (plugin.description or "-") + "\n"
            info += "GUI-кнопка: " + ("Да" if plugin.gui_enabled else "Нет") + "\n"
            info += "Опасный: " + ("Да" if plugin.dangerous else "Нет") + "\n"
            info += "-" * 50 + "\n"
            textbox.insert("end", info)
        textbox.configure(state="disabled")

    def send_message(self):
        text = self.user_input.get()
        if not text.strip():
            return
        self.user_input.delete(0, "end")
        self.log("\nВы: " + text)

        routing_preview = self.agent.router.classify(text)
        dangerous_hit = [t for t in routing_preview["tools"] if t in self.agent.router.dangerous_tools]
        if dangerous_hit:
            ok = messagebox.askyesno("Подтверждение", "Агент хочет выполнить: " + str(dangerous_hit) + "\nРазрешить?")
            if not ok:
                self.log("[Отменено пользователем]")
                return

        def task():
            result = self.agent.run_task(text, log_callback=self.log)
            self.log("\nАгент: " + result)
        threading.Thread(target=task, daemon=True).start()

    def open_style_studio(self):
        StyleManagerWindow(self, self.agent)

    def index_folder(self):
        f = filedialog.askdirectory()
        if f:
            self.run_in_thread(lambda: self.log("[ИНДЕКСАЦИЯ] " + str(self.agent.index_folder(f))))

    def check_spell(self):
        f = filedialog.askopenfilename()
        if f:
            self.run_in_thread(lambda: self.log("РЕЗУЛЬТАТ:\n" + self.agent.check_spelling_file(f)))

    def write_code(self):
        t = ctk.CTkInputDialog(text="Задача:", title="Код").get_input()
        if t:
            self.run_in_thread(lambda: self.log(self.agent.generate_code_with_validation(t)))

    def process_long_doc(self):
        f = filedialog.askopenfilename()
        if f:
            self.run_in_thread(lambda: self.log(self.agent.process_long_document(f)))

    def make_file_list_ui(self):
        f = filedialog.askdirectory()
        if not f:
            return
        r = messagebox.askyesno("Вложенность", "Включать подпапки?")
        self.run_in_thread(lambda: self.log("[СПИСОК]: " + str(self.agent.make_file_list(f, r))))

    def make_excel_chart_ui(self):
        f = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls")])
        if f:
            self.run_in_thread(lambda: self.log("[ГРАФИК]: " + str(self.agent.make_excel_chart(f))))

    def batch_summary_ui(self):
        f = filedialog.askdirectory()
        if f:
            self.run_in_thread(lambda: self.log("[РЕЗЮМЕ]: " + str(self.agent.batch_summarize(f))))

    def classify_ui(self):
        f = filedialog.askdirectory()
        if f:
            self.run_in_thread(lambda: self.log("[СОРТИРОВКА]: " + str(self.agent.classify_files(f))))

    def web_search_ui(self):
        q = ctk.CTkInputDialog(text="Запрос:", title="Поиск").get_input()
        if q:
            self.run_in_thread(lambda: self.log(self.agent.web_search(q)))

    def stop_agent(self):
        self.agent.request_stop()
        self.log("\n[СИСТЕМА] Стоп!")

    def open_add_llm_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Добавить LLM")
        win.geometry("450x400")
        win.attributes("-topmost", True)
        ctk.CTkLabel(win, text="Название профиля:").pack(pady=(10, 0))
        e1 = ctk.CTkEntry(win, width=350); e1.pack()
        ctk.CTkLabel(win, text="Base URL:").pack(pady=(10, 0))
        e2 = ctk.CTkEntry(win, width=350); e2.pack()
        ctk.CTkLabel(win, text="API Key:").pack(pady=(10, 0))
        e3 = ctk.CTkEntry(win, width=350, show="*"); e3.pack()
        ctk.CTkLabel(win, text="Имя модели:").pack(pady=(10, 0))
        e4 = ctk.CTkEntry(win, width=350); e4.pack()
        v = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(win, text="Локальная?", variable=v).pack(pady=10)
        def save():
            n, u, k, m = e1.get(), e2.get(), e3.get(), e4.get()
            if not n or not u or not m:
                messagebox.showerror("Ошибка", "Заполните поля!")
                return
            add_llm_profile(n, u, k, m, v.get())
            messagebox.showinfo("Успех", "Модель " + n + " добавлена!")
            win.destroy()
        ctk.CTkButton(win, text="Сохранить", command=save).pack(pady=20)