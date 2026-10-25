import os
import zipfile
import textwrap

PROJECT_NAME = "agent_gui_app"

FILES = {
    # Новая точка входа для GUI
    "main.py": """\
import customtkinter as ctk
from gui.app import AgentApp

if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    app = AgentApp()
    app.mainloop()
""",

    "gui/__init__.py": "",

    # Модуль для управления конфигом прямо из интерфейса
    "gui/config_manager.py": """\
import yaml
import os

def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_config(config, path="config.yaml"):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)

def add_llm_profile(name, base_url, api_key, model_name, is_local):
    config = load_config()
    if "llm_profiles" not in config:
        config["llm_profiles"] = {}

    config["llm_profiles"][name] = {
        "type": "openai_compat",
        "base_url": base_url,
        "api_key": api_key,
        "model_name": model_name,
        "is_local": is_local
    }
    save_config(config)
""",

    # Главное окно приложения
    "gui/app.py": """\
import customtkinter as ctk
import threading
import os
from tkinter import filedialog, messagebox
from core.agent import Agent
from gui.config_manager import add_llm_profile

class AgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI Document Agent")
        self.geometry("1000x700")
        self.agent = Agent("config.yaml")

        # --- Раскладка сетки ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- ЛЕВАЯ ПАНЕЛЬ (Кнопки) ---
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="AGENT PANEL", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.pack(padx=20, pady=(20, 10))

        self.btn_index = ctk.CTkButton(self.sidebar, text="Индексировать папку", command=self.index_folder)
        self.btn_index.pack(padx=20, pady=10)

        self.btn_spell = ctk.CTkButton(self.sidebar, text="Проверить орфографию", command=self.check_spell)
        self.btn_spell.pack(padx=20, pady=10)

        self.btn_code = ctk.CTkButton(self.sidebar, text="Написать код", command=self.write_code)
        self.btn_code.pack(padx=20, pady=10)

        self.btn_add_llm = ctk.CTkButton(self.sidebar, text="Добавить LLM (API)", fg_color="green", hover_color="darkgreen", command=self.open_add_llm_window)
        self.btn_add_llm.pack(padx=20, pady=(40, 10))

        self.btn_stop = ctk.CTkButton(self.sidebar, text="ЭКСТРЕННЫЙ СТОП", fg_color="red", hover_color="darkred", command=self.stop_agent)
        self.btn_stop.pack(padx=20, pady=10, side="bottom")

        # --- ПРАВАЯ ПАНЕЛЬ (Чат) ---
        self.chat_frame = ctk.CTkFrame(self)
        self.chat_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.chat_frame.grid_rowconfigure(0, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(self.chat_frame, state="disabled", wrap="word", font=("Arial", 14))
        self.chat_display.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        # Панель ввода
        self.input_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.user_input = ctk.CTkEntry(self.input_frame, placeholder_text="Задайте вопрос по документам или напишите команду...")
        self.user_input.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.user_input.bind("<Return>", lambda e: self.send_message())

        self.btn_send = ctk.CTkButton(self.input_frame, text="Отправить", width=100, command=self.send_message)
        self.btn_send.grid(row=0, column=1)

    def log(self, text):
        \"\"\"Безопасно добавляет текст в чат из любого потока.\"\"\"
        def _update():
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", text + "\\n")
            self.chat_display.see("end")
            self.chat_display.configure(state="disabled")
        self.after(0, _update)

    def run_in_thread(self, func, *args):
        \"\"\"Запускает тяжелые задачи в фоне, чтобы окно не зависало.\"\"\"
        def wrapper():
            try:
                func(*args)
            except Exception as e:
                self.log(f"\\n[ОШИБКА ИНТЕРФЕЙСА]: {str(e)}\\n")
        threading.Thread(target=wrapper, daemon=True).start()

    # --- ДЕЙСТВИЯ КНОПОК ---
    def index_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку с документами")
        if folder:
            self.log(f"\\n[СИСТЕМА] Начинаю индексацию папки: {folder}")
            self.run_in_thread(self._task_index, folder)

    def _task_index(self, folder):
        self.agent.index_folder(folder)
        self.log("[СИСТЕМА] Индексация успешно завершена!")

    def check_spell(self):
        file_path = filedialog.askopenfilename(title="Выберите файл для проверки")
        if file_path:
            self.log(f"\\n[СИСТЕМА] Проверяю орфографию в: {os.path.basename(file_path)}")
            self.run_in_thread(self._task_spell, file_path)

    def _task_spell(self, file_path):
        result = self.agent.check_spelling_file(file_path)
        self.log(f"[РЕЗУЛЬТАТ]:\\n{result}")

    def write_code(self):
        # Для простоты используем диалоговое окно ввода
        dialog = ctk.CTkInputDialog(text="Опишите задачу для написания кода:", title="Генерация кода")
        task = dialog.get_input()
        if task:
            self.log(f"\\n[СИСТЕМА] Пишу код: {task}")
            self.run_in_thread(self._task_code, task)

    def _task_code(self, task):
        code = self.agent.generate_code_with_validation(task)
        self.log(f"[КОД]:\\n{code}")

    def send_message(self):
        text = self.user_input.get()
        if not text.strip():
            return
        self.user_input.delete(0, "end")
        self.log(f"\\nВы: {text}")

        # Если пользователь вставил ответ из веб-чата (Ручной мост)
        if text.startswith("--- ОТВЕТ ИЗ ВЕБ-ЧАТА ---"):
            self.log("[СИСТЕМА] Ответ принят! (Логика обработки будет добавлена в следующем шаге)")
            return

        self.run_in_thread(self._task_chat, text)

    def _task_chat(self, question):
        self.log("Агент: Думаю...")
        answer = self.agent.ask_question(question)
        self.log(f"Агент: {answer}")

    def stop_agent(self):
        self.agent.request_stop()
        self.log("\\n[СИСТЕМА] Отправлен сигнал экстренной остановки!")

    # --- ОКНО ДОБАВЛЕНИЯ API ---
    def open_add_llm_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Добавить LLM (API)")
        win.geometry("400x350")
        win.attributes("-topmost", True)

        ctk.CTkLabel(win, text="Название профиля (например, deepseek_api):").pack(pady=(10,0))
        entry_name = ctk.CTkEntry(win, width=300)
        entry_name.pack()

        ctk.CTkLabel(win, text="Base URL (например, https://api.deepseek.com/v1):").pack(pady=(10,0))
        entry_url = ctk.CTkEntry(win, width=300)
        entry_url.pack()

        ctk.CTkLabel(win, text="API Key:").pack(pady=(10,0))
        entry_key = ctk.CTkEntry(win, width=300, show="*")
        entry_key.pack()

        ctk.CTkLabel(win, text="Имя модели (например, deepseek-chat):").pack(pady=(10,0))
        entry_model = ctk.CTkEntry(win, width=300)
        entry_model.pack()

        is_local_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(win, text="Это локальная модель?", variable=is_local_var).pack(pady=10)

        def save():
            name = entry_name.get().strip()
            url = entry_url.get().strip()
            key = entry_key.get().strip()
            model = entry_model.get().strip()
            is_local = is_local_var.get()

            if not name or not url or not model:
                messagebox.showerror("Ошибка", "Заполните все обязательные поля!")
                return

            add_llm_profile(name, url, key, model, is_local)
            messagebox.showinfo("Успех", f"Модель {name} добавлена в config.yaml!\\nПерезапустите приложение для применения.")
            win.destroy()

        ctk.CTkButton(win, text="Сохранить", command=save).pack(pady=20)
"""
}


def create_project():
    print(f"Создание GUI проекта {PROJECT_NAME}...")
    for filepath, content in FILES.items():
        clean_content = textwrap.dedent(content)
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(clean_content)
        print(f"  Создан/обновлен: {filepath}")

    zip_name = f"{PROJECT_NAME}.zip"
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filepath in FILES.keys():
            zipf.write(filepath)
    print(f"\\nГотово! Архив {zip_name} создан.")


if __name__ == "__main__":
    create_project()
