import customtkinter as ctk
import threading
import os
from tkinter import filedialog, messagebox
from core.agent import Agent
from gui.config_manager import add_llm_profile
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

        ctk.CTkLabel(self.sidebar, text="Базовые функции:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(10, 0), anchor="w", padx=20)
        self._add_btn("Индексировать папку", self.index_folder, "Прочитать файлы для RAG-поиска")
        self._add_btn("Проверить орфографию", self.check_spell, "Найти ошибки в файле")
        self._add_btn("Написать код", self.write_code, "Сгенерировать и проверить Python-код")
        self._add_btn("Полный разбор документа", self.process_long_doc, "Резюме больших книг/PDF с чекпоинтами", color="#8A2BE2")

        ctk.CTkLabel(self.sidebar, text="Инструменты Word:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Студия стилей Word", self.open_style_studio, "Замена стилей, нумерация таблиц и рисунков", color="#B8860B")

        ctk.CTkLabel(self.sidebar, text="Данные и поиск:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Список файлов (CSV)", self.make_file_list_ui, "Создать список всех файлов в папке")
        self._add_btn("График в Excel", self.make_excel_chart_ui, "Создать график по данным из Excel")
        self._add_btn("Пакетное резюме", self.batch_summary_ui, "Сделать резюме для всех файлов в папке")
        self._add_btn("Сортировка файлов", self.classify_ui, "Разложить файлы по категориям")
        self._add_btn("Веб-поиск", self.web_search_ui, "Найти информацию в интернете")

        ctk.CTkLabel(self.sidebar, text="Настройки:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Добавить LLM (API)", self.open_add_llm_window, "Подключить внешнюю модель", color="green")

        self.btn_stop = ctk.CTkButton(self, text="ЭКСТРЕННЫЙ СТОП", fg_color="red", hover_color="darkred", command=self.stop_agent)
        self.btn_stop.grid(row=0, column=0, sticky="sw", padx=20, pady=20)
        ToolTip(self.btn_stop, "Остановить агента, сохранив последний результат")

        self.chat_frame = ctk.CTkFrame(self)
        self.chat_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.chat_frame.grid_rowconfigure(0, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(self.chat_frame, state="disabled", wrap="word", font=("Consolas", 14))
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        self.input_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.user_input = ctk.CTkEntry(self.input_frame, placeholder_text="Задайте вопрос по документам...")
        self.user_input.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.user_input.bind("<Return>", lambda e: self.send_message())

        self.btn_send = ctk.CTkButton(self.input_frame, text="Отправить", width=100, command=self.send_message)
        self.btn_send.grid(row=0, column=1)

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

    def open_style_studio(self):
        StyleManagerWindow(self, self.agent)

    # ... остальные методы (index_folder, check_spell и т.д.) оставляем без изменений ...
    def index_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку")
        if folder: self.run_in_thread(lambda: self.log("[ИНДЕКСАЦИЯ] " + str(self.agent.index_folder(folder))))

    def check_spell(self):
        file_path = filedialog.askopenfilename(title="Выберите файл")
        if file_path: self.run_in_thread(lambda: self.log(f"РЕЗУЛЬТАТ:\n{self.agent.check_spelling_file(file_path)}"))

    def write_code(self):
        task = ctk.CTkInputDialog(text="Опишите задачу:", title="Код").get_input()
        if task: self.run_in_thread(lambda: self.log(self.agent.generate_code_with_validation(task)))

    def process_long_doc(self):
        file_path = filedialog.askopenfilename(title="Выберите большой документ")
        if file_path: self.run_in_thread(lambda: self.log(self.agent.process_long_document(file_path)))

    def make_file_list_ui(self):
        folder = filedialog.askdirectory(title="Выберите папку для списка")
        if not folder: return
        recursive = messagebox.askyesno("Вложенность", "Включать файлы из внутренних папок?")
        self.run_in_thread(lambda: self.log(f"[СПИСОК] Сохранен: {self.agent.make_file_list(folder, recursive)}"))

    def make_excel_chart_ui(self):
        file_path = filedialog.askopenfilename(title="Выберите Excel файл", filetypes=[("Excel", "*.xlsx *.xls")])
        if file_path: self.run_in_thread(lambda: self.log(f"[ГРАФИК] Сохранен: {self.agent.make_excel_chart(file_path)}"))

    def batch_summary_ui(self):
        folder = filedialog.askdirectory(title="Выберите папку для резюме")
        if folder: self.run_in_thread(lambda: self.log(f"[РЕЗЮМЕ] Сохранено: {self.agent.batch_summarize(folder)}"))

    def classify_ui(self):
        folder = filedialog.askdirectory(title="Выберите папку для сортировки")
        if folder: self.run_in_thread(lambda: self.log(f"[СОРТИРОВКА] Сохранено в: {self.agent.classify_files(folder)}"))

    def web_search_ui(self):
        query = ctk.CTkInputDialog(text="Что искать в интернете?", title="Поиск").get_input()
        if query: self.run_in_thread(lambda: self.log(self.agent.web_search(query)))

    def send_message(self):
        text = self.user_input.get()
        if not text.strip(): return
        self.user_input.delete(0, "end")
        self.log(f"\nВы: {text}")
        self.run_in_thread(lambda: self.log(f"Агент: {self.agent.ask_question(text)}"))

    def stop_agent(self):
        self.agent.request_stop()
        self.log("\n[СИСТЕМА] Сигнал остановки отправлен!")

    def open_add_llm_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Добавить LLM")
        win.geometry("450x400")
        win.attributes("-topmost", True)

        ctk.CTkLabel(win, text="Название профиля:").pack(pady=(10,0))
        entry_name = ctk.CTkEntry(win, width=350); entry_name.pack()
        ctk.CTkLabel(win, text="Base URL:").pack(pady=(10,0))
        entry_url = ctk.CTkEntry(win, width=350); entry_url.pack()
        ctk.CTkLabel(win, text="API Key:").pack(pady=(10,0))
        entry_key = ctk.CTkEntry(win, width=350, show="*"); entry_key.pack()
        ctk.CTkLabel(win, text="Имя модели:").pack(pady=(10,0))
        entry_model = ctk.CTkEntry(win, width=350); entry_model.pack()

        is_local_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(win, text="Это локальная модель?", variable=is_local_var).pack(pady=10)

        def save():
            name, url, key, model = entry_name.get(), entry_url.get(), entry_key.get(), entry_model.get()
            if not name or not url or not model:
                messagebox.showerror("Ошибка", "Заполните все обязательные поля!")
                return
            add_llm_profile(name, url, key, model, is_local_var.get())
            messagebox.showinfo("Успех", f"Модель {name} добавлена! Перезапустите приложение.")
            win.destroy()

        ctk.CTkButton(win, text="Сохранить", command=save).pack(pady=20)
