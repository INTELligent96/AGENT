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
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkScrollableFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="AGENT PANEL", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.pack(padx=20, pady=(20, 10))

        # --- ТУМБЛЕРЫ ПРОВЕРКИ ---
        ctk.CTkLabel(self.sidebar, text="Проверка ответов:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(10, 0), anchor="w", padx=20)

        cfg = load_config()
        self.var_enabled = ctk.BooleanVar(value=cfg.get("self_check", {}).get("enabled", True))
        self.var_force = ctk.BooleanVar(value=cfg.get("self_check", {}).get("force_always", False))

        chk_enabled = ctk.CTkCheckBox(self.sidebar, text="Включить критика", variable=self.var_enabled, command=self._on_critic_toggle)
        chk_enabled.pack(padx=20, pady=5, anchor="w")
        ToolTip(chk_enabled, "Главный выключатель: включена ли проверка ответов ИИ.")

        chk_force = ctk.CTkCheckBox(self.sidebar, text="Всегда (даже для кода)", variable=self.var_force, command=self._on_critic_toggle)
        chk_force.pack(padx=20, pady=5, anchor="w")
        ToolTip(chk_force, "Проверять даже те задачи, где обычно хватает Python-валидатора. Медленнее, но строже.")

        # --- КНОПКИ ---
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

        ctk.CTkLabel(self.sidebar, text="Настройки:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Добавить LLM (API)", self.open_add_llm_window, "Подключить API", color="green")

        self.btn_stop = ctk.CTkButton(self, text="ЭКСТРЕННЫЙ СТОП", fg_color="red", hover_color="darkred", command=self.stop_agent)
        self.btn_stop.grid(row=0, column=0, sticky="sw", padx=20, pady=20)

        # --- ЧАТ ---
        self.chat_frame = ctk.CTkFrame(self)
        self.chat_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.chat_frame.grid_rowconfigure(0, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(self.chat_frame, state="disabled", wrap="word", font=("Consolas", 14))
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        self.input_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.user_input = ctk.CTkEntry(self.input_frame, placeholder_text="Спросите или дайте команду (например, 'сделай резюме D:/file.txt')")
        self.user_input.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.user_input.bind("<Return>", lambda e: self.send_message())

        self.btn_send = ctk.CTkButton(self.input_frame, text="Отправить", width=100, command=self.send_message)
        self.btn_send.grid(row=0, column=1)

    def _on_critic_toggle(self):
        cfg = load_config()
        if "self_check" not in cfg: cfg["self_check"] = {}
        cfg["self_check"]["enabled"] = self.var_enabled.get()
        cfg["self_check"]["force_always"] = self.var_force.get()
        save_config(cfg)
        # Применяем на лету (без перезапуска)
        self.agent.critic.enabled = self.var_enabled.get()
        self.agent.critic.force_always = self.var_force.get()
        self.log(f"[Настройки] Критик: {'ВКЛ' if self.var_enabled.get() else 'ВЫКЛ'}, force_always={self.var_force.get()}")

    def _add_btn(self, text, command, hint, color=None):
        btn = ctk.CTkButton(self.sidebar, text=text, command=command)
        if color: btn.configure(fg_color=color, hover_color="darkgreen" if color=="green" else "#4B0082")
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
            try: func(*args)
            except Exception as e: self.log(f"\n[ОШИБКА]: {str(e)}\n")
        threading.Thread(target=wrapper, daemon=True).start()

    # --- ОТПРАВКА ЧЕРЕЗ РОУТЕР ---
    def send_message(self):
        text = self.user_input.get()
        if not text.strip(): return
        self.user_input.delete(0, "end")
        self.log(f"\nВы: {text}")

        # Опасные действия — подтверждение
        routing_preview = self.agent.router.classify(text)
        dangerous_hit = [t for t in routing_preview["tools"] if t in self.agent.router.dangerous_tools]
        if dangerous_hit:
            ok = messagebox.askyesno("Подтверждение", f"Агент хочет выполнить: {dangerous_hit}. Это может создать/изменить файлы. Разрешить?")
            if not ok:
                self.log("[Отменено пользователем]")
                return

        def task():
            result = self.agent.run_task(text, log_callback=self.log)
            self.log(f"\nАгент: {result}")
        threading.Thread(target=task, daemon=True).start()

    # --- КНОПКИ (остались как были) ---
    def open_style_studio(self): StyleManagerWindow(self, self.agent)
    def index_folder(self):
        f = filedialog.askdirectory()
        if f: self.run_in_thread(lambda: self.log("[ИНДЕКСАЦИЯ] " + str(self.agent.index_folder(f))))
    def check_spell(self):
        f = filedialog.askopenfilename()
        if f: self.run_in_thread(lambda: self.log(f"РЕЗУЛЬТАТ:\n{self.agent.check_spelling_file(f)}"))
    def write_code(self):
        t = ctk.CTkInputDialog(text="Задача:", title="Код").get_input()
        if t: self.run_in_thread(lambda: self.log(self.agent.generate_code_with_validation(t)))
    def process_long_doc(self):
        f = filedialog.askopenfilename()
        if f: self.run_in_thread(lambda: self.log(self.agent.process_long_document(f)))
    def make_file_list_ui(self):
        f = filedialog.askdirectory()
        if not f: return
        r = messagebox.askyesno("Вложенность", "Включать подпапки?")
        self.run_in_thread(lambda: self.log(f"[СПИСОК]: {self.agent.make_file_list(f, r)}"))
    def make_excel_chart_ui(self):
        f = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls")])
        if f: self.run_in_thread(lambda: self.log(f"[ГРАФИК]: {self.agent.make_excel_chart(f)}"))
    def batch_summary_ui(self):
        f = filedialog.askdirectory()
        if f: self.run_in_thread(lambda: self.log(f"[РЕЗЮМЕ]: {self.agent.batch_summarize(f)}"))
    def classify_ui(self):
        f = filedialog.askdirectory()
        if f: self.run_in_thread(lambda: self.log(f"[СОРТИРОВКА]: {self.agent.classify_files(f)}"))
    def web_search_ui(self):
        q = ctk.CTkInputDialog(text="Запрос:", title="Поиск").get_input()
        if q: self.run_in_thread(lambda: self.log(self.agent.web_search(q)))
    def stop_agent(self):
        self.agent.request_stop()
        self.log("\n[СИСТЕМА] Стоп!")

    def open_add_llm_window(self):
        win = ctk.CTkToplevel(self); win.title("Добавить LLM"); win.geometry("450x400"); win.attributes("-topmost", True)
        ctk.CTkLabel(win, text="Название профиля:").pack(pady=(10,0)); e1 = ctk.CTkEntry(win, width=350); e1.pack()
        ctk.CTkLabel(win, text="Base URL:").pack(pady=(10,0)); e2 = ctk.CTkEntry(win, width=350); e2.pack()
        ctk.CTkLabel(win, text="API Key:").pack(pady=(10,0)); e3 = ctk.CTkEntry(win, width=350, show="*"); e3.pack()
        ctk.CTkLabel(win, text="Имя модели:").pack(pady=(10,0)); e4 = ctk.CTkEntry(win, width=350); e4.pack()
        v = ctk.BooleanVar(value=False); ctk.CTkCheckBox(win, text="Локальная?", variable=v).pack(pady=10)
        def save():
            n, u, k, m = e1.get(), e2.get(), e3.get(), e4.get()
            if not n or not u or not m: messagebox.showerror("Ошибка", "Заполните поля!"); return
            add_llm_profile(n, u, k, m, v.get())
            messagebox.showinfo("Успех", f"Модель {n} добавлена!"); win.destroy()
        ctk.CTkButton(win, text="Сохранить", command=save).pack(pady=20)
