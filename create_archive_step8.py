import os
import zipfile
import textwrap

PROJECT_NAME = "agent_super_features"

FILES = {
    # 1. Менеджер файлов (Списки файлов)
    "tools/file_manager.py": """\
import os
from pathlib import Path
import csv

def generate_file_list(folder_path: str, recursive: bool = True, output_dir: str = "output") -> str:
    \"\"\"Генерирует список файлов в папке и сохраняет в CSV.\"\"\"
    Path(output_dir).mkdir(exist_ok=True)
    folder = Path(folder_path)

    files_data = []
    if recursive:
        for f in folder.rglob('*'):
            if f.is_file():
                files_data.append([f.name, str(f.parent), f.stat().st_size, f.suffix])
    else:
        for f in folder.glob('*'):
            if f.is_file():
                files_data.append([f.name, str(f.parent), f.stat().st_size, f.suffix])

    out_file = Path(output_dir) / f"file_list_{folder.name}.csv"
    with open(out_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(["Имя файла", "Папка", "Размер (байт)", "Расширение"])
        writer.writerows(files_data)

    return str(out_file)
""",

    # 2. Инструменты Excel (Графики и Pandas)
    "tools/excel_tools.py": """\
import pandas as pd
import xlsxwriter
from pathlib import Path
import os

def create_excel_chart(file_path: str, output_dir: str = "output") -> str:
    \"\"\"Читает Excel, строит график по первым двум колонкам и сохраняет.\"\"\"
    Path(output_dir).mkdir(exist_ok=True)
    out_file = Path(output_dir) / f"chart_{Path(file_path).name}"

    try:
        df = pd.read_excel(file_path)
        if df.empty or len(df.columns) < 2:
            return "[Ошибка] В файле недостаточно данных (нужно минимум 2 колонки)."

        x_col = df.columns[0]
        y_col = df.columns[1]

        # Очищаем данные от пустых строк
        df = df.dropna(subset=[x_col, y_col])

        workbook = xlsxwriter.Workbook(str(out_file))
        worksheet = workbook.add_worksheet("Данные")
        chart = workbook.add_chart({'type': 'column'})

        # Записываем данные
        worksheet.write(0, 0, x_col)
        worksheet.write(0, 1, y_col)
        for row_num, (x_val, y_val) in enumerate(zip(df[x_col], df[y_col]), start=1):
            worksheet.write(row_num, 0, x_val)
            worksheet.write(row_num, 1, y_val)

        # Настраиваем график
        chart.add_series({
            'categories': ['Данные', 1, 0, len(df), 0],
            'values':     ['Данные', 1, 1, len(df), 1],
            'name':       y_col
        })
        chart.set_title({'name': f'График: {y_col} от {x_col}'})
        worksheet.insert_chart('D2', chart)

        workbook.close()
        return str(out_file)
    except Exception as e:
        return f"[Ошибка] Не удалось создать график: {e}"
""",

    # 3. Веб-поиск
    "tools/web_search.py": """\
from duckduckgo_search import DDGS

def search_web(query: str, max_results: int = 3) -> str:
    \"\"\"Ищет информацию в интернете.\"\"\"
    try:
        results = DDGS().text(query, max_results=max_results)
        if not results:
            return "Ничего не найдено в интернете."

        output = ""
        for r in results:
            output += f"Источник: {r['title']}\\nСсылка: {r['href']}\\nТекст: {r['body']}\\n\\n"
        return output
    except Exception as e:
        return f"Ошибка поиска: {e}"
""",

    # 4. Обновляем Агента (подключаем все фичи)
    "core/agent.py": """\
import os
import time
import yaml
import shutil
from pathlib import Path
from llm.registry import LLMRegistry
from documents.extractors import extract_text
from documents.writers import create_simple_docx
from core.prompts import SUMMARIZE_PROMPT, STRUCTURE_PROMPT, SPELLCHECK_PROMPT, CODE_PROMPT
from core.workspace import WorkspaceManager
from tools.validator import validate_python_code
from tools.file_manager import generate_file_list
from tools.excel_tools import create_excel_chart
from tools.web_search import search_web
from rag.qa import RAGQuestionAnswerer

class Agent:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.tools = self.config.get("tools", {})
        self.registry = LLMRegistry(config_path)

        safety = self.config.get("safety", {})
        self.workspace = WorkspaceManager(
            workspace_dir=safety.get("workspace_dir", "workspace"),
            read_only_originals=safety.get("read_only_originals", True)
        )

        agent_loop = self.config.get("agent_loop", {})
        self.max_iterations = agent_loop.get("max_iterations", 10)
        self.task_timeout = agent_loop.get("task_timeout_seconds", 600)
        self.code_timeout = agent_loop.get("code_execution_timeout", 15)

        self._stop_requested = False
        self._rag = None
        self.output_dir = "output"
        Path(self.output_dir).mkdir(exist_ok=True)

    @property
    def rag(self):
        if self._rag is None:
            self._rag = RAGQuestionAnswerer(self.config, self.tools, self.registry)
        return self._rag

    # --- НОВЫЕ ИНСТРУМЕНТЫ ---
    def make_file_list(self, folder_path: str, recursive: bool) -> str:
        print(f"Генерация списка файлов: {folder_path}")
        return generate_file_list(folder_path, recursive, self.output_dir)

    def make_excel_chart(self, file_path: str) -> str:
        print(f"Создание графика для: {file_path}")
        return create_excel_chart(file_path, self.output_dir)

    def classify_files(self, folder_path: str) -> str:
        \"\"\"Сортирует файлы по категориям (копирует, не двигает).\"\"\"
        folder = Path(folder_path)
        sorted_dir = Path(self.output_dir) / f"sorted_{folder.name}"
        sorted_dir.mkdir(parents=True, exist_ok=True)

        files = [f for f in folder.iterdir() if f.is_file()]
        for f in files:
            text = extract_text(str(f), self.tools)[:2000] # Берем кусок для анализа
            prompt = f"Определи категорию документа (одним словом: Договор, Счет, Отчет, Письмо, Прочее). Текст: {text}"
            category = self.registry.generate_with_fallback("default_model", prompt).strip()
            # Очищаем от мусора
            category = category.split()[0].replace('.', '').replace('"', '').replace("'", "")

            cat_dir = sorted_dir / category
            cat_dir.mkdir(exist_ok=True)
            shutil.copy2(f, cat_dir / f.name)

        return str(sorted_dir)

    def batch_summarize(self, folder_path: str) -> str:
        \"\"\"Делает резюме для всех файлов и собирает в один Word.\"\"\"
        folder = Path(folder_path)
        files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in ['.txt', '.docx', '.pdf']]

        final_text = ""
        for f in files:
            text = self._read_safe(str(f))
            if text.startswith("[Ошибка]"): continue

            prompt = SUMMARIZE_PROMPT.format(text=text[:6000])
            summary = self.registry.generate_with_fallback("default_model", prompt)
            final_text += f"=== РЕЗЮМЕ ФАЙЛА: {f.name} ===\\n{summary}\\n\\n"

        out_file = Path(self.output_dir) / f"batch_summary_{folder.name}.docx"
        create_simple_docx(final_text, str(out_file))
        return str(out_file)

    def web_search(self, query: str) -> str:
        print(f"Поиск в интернете: {query}")
        return search_web(query)

    # --- БАЗОВЫЕ МЕТОДЫ ---
    def index_folder(self, folder_path: str):
        return self.rag.indexer.index_folder(folder_path)

    def ask_question(self, question: str) -> str:
        return self.rag.ask(question)

    def request_stop(self):
        self._stop_requested = True

    def reset_stop_flag(self):
        self._stop_requested = False

    def _read_safe(self, file_path: str) -> str:
        safe_path = self.workspace.prepare_file(file_path)
        return extract_text(safe_path, self.tools)

    def generate_code_with_validation(self, task: str) -> str:
        self.reset_stop_flag()
        current_prompt = CODE_PROMPT.format(task=task)
        last_generated_code = ""
        start_time = time.time()

        for iteration in range(1, self.max_iterations + 1):
            if self._stop_requested: return f"--- ПРЕРВАНО ---\\n\\n{last_generated_code}"
            if time.time() - start_time > self.task_timeout: return f"--- ТАЙМАУТ ---\\n\\n{last_generated_code}"

            code = self.registry.generate_with_fallback("code_generation", current_prompt)
            last_generated_code = code

            if code.startswith("[КРИТИЧЕСКАЯ ОШИБКА]") or code.startswith("[ВНИМАНИЕ:"): return code

            is_valid, error_msg = validate_python_code(code, timeout_sec=self.code_timeout)
            if is_valid: return code

            current_prompt = f"Твой предыдущий код выдал ошибку:\\n{error_msg}\\n\\nКод:\\n{code}\\n\\nИсправь. Задача: {task}"
        return f"--- ЛИМИТ ПОПЫТОК ---\\n\\n{last_generated_code}"

    def summarize_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        return self.registry.generate_with_fallback("default_model", SUMMARIZE_PROMPT.format(text=text[:8000]))

    def check_spelling_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        return self.registry.generate_with_fallback("default_model", SPELLCHECK_PROMPT.format(text=text[:8000]))

    def structure_file(self, file_path: str) -> str:
        text = self._read_safe(file_path)
        if text.startswith("[Ошибка]"): return text
        return self.registry.generate_with_fallback("complex_reasoning", STRUCTURE_PROMPT.format(text=text[:8000]))
""",

    # 5. ОБНОВЛЕННЫЙ GUI (С прокруткой и новыми кнопками)
    "gui/app.py": """\
import customtkinter as ctk
import threading
import os
from tkinter import filedialog, messagebox
from core.agent import Agent
from gui.config_manager import add_llm_profile
from gui.tooltip import ToolTip

class AgentApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI Document Agent PRO")
        self.geometry("1200x800")
        self.agent = Agent("config.yaml")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- ЛЕВАЯ ПАНЕЛЬ (Скроллинг) ---
        self.sidebar = ctk.CTkScrollableFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="AGENT PANEL", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.pack(padx=20, pady=(20, 10))

        # 1. Базовые функции
        ctk.CTkLabel(self.sidebar, text="Базовые функции:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(10, 0), anchor="w", padx=20)

        self._add_btn("Индексировать папку", self.index_folder, "Прочитать файлы для RAG-поиска")
        self._add_btn("Проверить орфографию", self.check_spell, "Найти ошибки в файле")
        self._add_btn("Написать код", self.write_code, "Сгенерировать и проверить Python-код")

        # 2. Инструменты
        ctk.CTkLabel(self.sidebar, text="Инструменты:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)

        self._add_btn("Список файлов (CSV)", self.make_file_list_ui, "Создать список всех файлов в папке")
        self._add_btn("График в Excel", self.make_excel_chart_ui, "Создать график по данным из Excel")
        self._add_btn("Пакетное резюме", self.batch_summary_ui, "Сделать резюме для всех файлов в папке")
        self._add_btn("Сортировка файлов", self.classify_ui, "Разложить файлы по категориям")
        self._add_btn("Веб-поиск", self.web_search_ui, "Найти информацию в интернете")

        # 3. Настройки
        ctk.CTkLabel(self.sidebar, text="Настройки:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
        self._add_btn("Добавить LLM (API)", self.open_add_llm_window, "Подключить внешнюю модель", color="green")

        # Кнопка СТОП в самом низу (не в скролле)
        self.btn_stop = ctk.CTkButton(self, text="ЭКСТРЕННЫЙ СТОП", fg_color="red", hover_color="darkred", command=self.stop_agent)
        self.btn_stop.grid(row=0, column=0, sticky="sw", padx=20, pady=20)
        ToolTip(self.btn_stop, "Остановить агента, сохранив последний результат")

        # --- ПРАВАЯ ПАНЕЛЬ (Чат) ---
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
        if color: btn.configure(fg_color=color, hover_color="darkgreen")
        btn.pack(padx=20, pady=5, fill="x")
        ToolTip(btn, hint)

    def log(self, text):
        def _update():
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", text + "\\n")
            self.chat_display.see("end")
            self.chat_display.configure(state="disabled")
        self.after(0, _update)

    def run_in_thread(self, func, *args):
        def wrapper():
            try: func(*args)
            except Exception as e: self.log(f"\\n[ОШИБКА]: {str(e)}\\n")
        threading.Thread(target=wrapper, daemon=True).start()

    # --- ОБРАБОТЧИКИ КНОПОК ---
    def index_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку")
        if folder: self.run_in_thread(lambda: self.log("[ИНДЕКСАЦИЯ] " + str(self.agent.index_folder(folder))))

    def check_spell(self):
        file_path = filedialog.askopenfilename(title="Выберите файл")
        if file_path: self.run_in_thread(lambda: self.log(f"РЕЗУЛЬТАТ:\\n{self.agent.check_spelling_file(file_path)}"))

    def write_code(self):
        task = ctk.CTkInputDialog(text="Опишите задачу:", title="Код").get_input()
        if task: self.run_in_thread(lambda: self.log(self.agent.generate_code_with_validation(task)))

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
        self.log(f"\\nВы: {text}")
        self.run_in_thread(lambda: self.log(f"Агент: {self.agent.ask_question(text)}"))

    def stop_agent(self):
        self.agent.request_stop()
        self.log("\\n[СИСТЕМА] Сигнал остановки отправлен!")

    def open_add_llm_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Добавить LLM")
        win.geometry("450x400")
        win.attributes("-topmost", True)

        ctk.CTkLabel(win, text="Название профиля (например, deepseek_api):").pack(pady=(10,0))
        entry_name = ctk.CTkEntry(win, width=350)
        entry_name.pack()

        ctk.CTkLabel(win, text="Base URL:").pack(pady=(10,0))
        entry_url = ctk.CTkEntry(win, width=350)
        entry_url.pack()

        ctk.CTkLabel(win, text="API Key:").pack(pady=(10,0))
        entry_key = ctk.CTkEntry(win, width=350, show="*")
        entry_key.pack()

        ctk.CTkLabel(win, text="Имя модели (например, deepseek-chat):").pack(pady=(10,0))
        entry_model = ctk.CTkEntry(win, width=350)
        entry_model.pack()

        is_local_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(win, text="Это локальная модель?", variable=is_local_var).pack(pady=10)

        def save():
            name, url, key, model = entry_name.get(), entry_url.get(), entry_key.get(), entry_model.get()
            if not name or not url or not model:
                messagebox.showerror("Ошибка", "Заполните все обязательные поля!")
                return
            add_llm_profile(name, url, key, model, is_local_var.get())
            messagebox.showinfo("Успех", f"Модель {name} добавлена в config.yaml! Перезапустите приложение.")
            win.destroy()

        ctk.CTkButton(win, text="Сохранить", command=save).pack(pady=20)
"""
}


def create_project():
    print(f"Создание МЕГА-ПАТЧА {PROJECT_NAME}...")
    for filepath, content in FILES.items():
        clean_content = textwrap.dedent(content)
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(clean_content)
        print(f"  Обновлен: {filepath}")

    zip_name = f"{PROJECT_NAME}.zip"
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filepath in FILES.keys():
            zipf.write(filepath)
    print(f"\\nГотово! Архив {zip_name} создан.")


if __name__ == "__main__":
    create_project()