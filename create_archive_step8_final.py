import os
import zipfile
import textwrap

PROJECT_NAME = "agent_step8_final"

FILES = {
    # 1. Исправленные подсказки
    "gui/tooltip.py": """\
import customtkinter as ctk

class ToolTip:
    def __init__(self, widget, text, delay=500, auto_hide=4000):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.show_job = None
        self.hide_job = None
        self.delay = delay
        self.auto_hide = auto_hide

        self.widget.bind("<Enter>", self.schedule_show)
        self.widget.bind("<Leave>", self.hide_tooltip)
        self.widget.bind("<Button-1>", self.hide_tooltip)
        self.widget.bind("<FocusOut>", self.hide_tooltip)

    def schedule_show(self, event=None):
        self.cancel_jobs()
        self.show_job = self.widget.after(self.delay, self.show_tooltip)

    def show_tooltip(self):
        if self.tooltip_window or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except Exception:
            return

        self.tooltip_window = ctk.CTkToplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        self.tooltip_window.attributes("-topmost", True)

        label = ctk.CTkLabel(
            self.tooltip_window, text=self.text, fg_color="#2b2b2b", text_color="white", corner_radius=6, font=("Arial", 12)
        )
        label.pack(ipadx=6, ipady=3)
        self.hide_job = self.widget.after(self.auto_hide, self.hide_tooltip)

    def hide_tooltip(self, event=None):
        self.cancel_jobs()
        if self.tooltip_window:
            try: self.tooltip_window.destroy()
            except Exception: pass
            self.tooltip_window = None

    def cancel_jobs(self):
        if self.show_job:
            try: self.widget.after_cancel(self.show_job)
            except Exception: pass
            self.show_job = None
        if self.hide_job:
            try: self.widget.after_cancel(self.hide_job)
            except Exception: pass
            self.hide_job = None
""",

    # 2. Модуль для длинных документов (Checkpoints)
    "tools/long_doc.py": """\
import os
from pathlib import Path
from llm.registry import LLMRegistry
from documents.extractors import extract_text
from core.prompts import SUMMARIZE_PROMPT

class LongDocumentProcessor:
    def __init__(self, agent_config: dict, tools_config: dict, registry: LLMRegistry, output_dir="output"):
        self.config = agent_config
        self.tools = tools_config
        self.registry = registry
        self.output_dir = Path(output_dir) / "checkpoints"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        rag_cfg = self.config.get("rag", {})
        self.chunk_size = rag_cfg.get("chunk_size", 3000) # Для резюме берем куски побольше

    def process(self, file_path: str) -> str:
        \"\"\"Читает большой файл, режет на куски и делает резюме с сохранением чекпоинтов.\"\"\"
        file_path = Path(file_path)
        print(f"\\n[LongDoc] Начинаю обработку файла: {file_path.name}")

        text = extract_text(str(file_path), self.tools)
        if text.startswith("[Ошибка]"):
            return text

        # Создаем папку для чекпоинтов конкретно этого файла
        doc_dir = self.output_dir / file_path.stem
        doc_dir.mkdir(parents=True, exist_ok=True)

        # Простой сплиттер по предложениям, чтобы не рвать мысли
        chunks = []
        current_chunk = ""
        for sentence in text.replace('\\n', ' ').split('. '):
            if len(current_chunk) + len(sentence) > self.chunk_size:
                chunks.append(current_chunk)
                current_chunk = sentence
            else:
                current_chunk += sentence + ". "
        if current_chunk:
            chunks.append(current_chunk)

        print(f"[LongDoc] Файл разбит на {len(chunks)} частей.")

        summaries = []
        for i, chunk in enumerate(chunks):
            checkpoint_file = doc_dir / f"part_{i}.txt"

            # Если чекпоинт уже есть (прервались в прошлый раз), читаем с диска!
            if checkpoint_file.exists():
                print(f"[LongDoc] Часть {i+1}/{len(chunks)} уже обработана. Загружаю с диска.")
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    summaries.append(f.read())
                continue

            print(f"[LongDoc] Резюмирую часть {i+1}/{len(chunks)}...")
            prompt = SUMMARIZE_PROMPT.format(text=chunk)
            summary = self.registry.generate_with_fallback("default_model", prompt)

            # Сохраняем чекпоинт
            with open(checkpoint_file, "w", encoding="utf-8") as f:
                f.write(summary)
            summaries.append(summary)

        # Финальное резюме (склеиваем куски)
        print("[LongDoc] Генерация финального резюме...")
        final_text = "\\n\\n".join(summaries)
        final_prompt = SUMMARIZE_PROMPT.format(text=final_text)
        final_summary = self.registry.generate_with_fallback("default_model", final_prompt)

        # Сохраняем итог
        final_file = self.output_dir / f"FINAL_{file_path.stem}.txt"
        with open(final_file, "w", encoding="utf-8") as f:
            f.write(final_summary)

        return f"Готово! Итоговое резюме сохранено в {final_file}"
""",

    # 3. Обновленный Агент
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
from tools.long_doc import LongDocumentProcessor
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

    # --- ДЛИННЫЕ ДОКУМЕНТЫ ---
    def process_long_document(self, file_path: str) -> str:
        processor = LongDocumentProcessor(self.config, self.tools, self.registry, self.output_dir)
        return processor.process(file_path)

    # --- НОВЫЕ ИНСТРУМЕНТЫ ---
    def make_file_list(self, folder_path: str, recursive: bool) -> str:
        return generate_file_list(folder_path, recursive, self.output_dir)

    def make_excel_chart(self, file_path: str) -> str:
        return create_excel_chart(file_path, self.output_dir)

    def classify_files(self, folder_path: str) -> str:
        folder = Path(folder_path)
        sorted_dir = Path(self.output_dir) / f"sorted_{folder.name}"
        sorted_dir.mkdir(parents=True, exist_ok=True)

        files = [f for f in folder.iterdir() if f.is_file()]
        for f in files:
            text = extract_text(str(f), self.tools)[:2000]
            prompt = f"Определи категорию документа (одним словом: Договор, Счет, Отчет, Письмо, Прочее). Текст: {text}"
            category = self.registry.generate_with_fallback("default_model", prompt).strip()
            category = category.split()[0].replace('.', '').replace('"', '').replace("'", "")

            cat_dir = sorted_dir / category
            cat_dir.mkdir(exist_ok=True)
            shutil.copy2(f, cat_dir / f.name)
        return str(sorted_dir)

    def batch_summarize(self, folder_path: str) -> str:
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

    # 4. GUI (Добавили кнопку длинных документов)
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

        self.sidebar = ctk.CTkScrollableFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="AGENT PANEL", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo_label.pack(padx=20, pady=(20, 10))

        ctk.CTkLabel(self.sidebar, text="Базовые функции:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(10, 0), anchor="w", padx=20)
        self._add_btn("Индексировать папку", self.index_folder, "Прочитать файлы для RAG-поиска")
        self._add_btn("Проверить орфографию", self.check_spell, "Найти ошибки в файле")
        self._add_btn("Написать код", self.write_code, "Сгенерировать и проверить Python-код")
        self._add_btn("Полный разбор документа", self.process_long_doc, "Резюме больших книг/PDF с чекпоинтами", color="#8A2BE2")

        ctk.CTkLabel(self.sidebar, text="Инструменты:", font=("Arial", 14, "bold"), text_color="gray").pack(pady=(20, 0), anchor="w", padx=20)
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
            self.chat_display.insert("end", text + "\\n")
            self.chat_display.see("end")
            self.chat_display.configure(state="disabled")
        self.after(0, _update)

    def run_in_thread(self, func, *args):
        def wrapper():
            try: func(*args)
            except Exception as e: self.log(f"\\n[ОШИБКА]: {str(e)}\\n")
        threading.Thread(target=wrapper, daemon=True).start()

    def index_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку")
        if folder: self.run_in_thread(lambda: self.log("[ИНДЕКСАЦИЯ] " + str(self.agent.index_folder(folder))))

    def check_spell(self):
        file_path = filedialog.askopenfilename(title="Выберите файл")
        if file_path: self.run_in_thread(lambda: self.log(f"РЕЗУЛЬТАТ:\\n{self.agent.check_spelling_file(file_path)}"))

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
""",

    # 5. МЕГА-ТЕСТ (Проверяет абсолютно всё)
    "test_all_features.py": """\
import os
import shutil
from pathlib import Path
from core.agent import Agent
from documents.writers import create_simple_docx

def setup_test_env():
    test_dir = Path("TEST_ENV")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    # 1. Текстовый файл
    (test_dir / "doc1.txt").write_text("Компания Рога и Копыта основана в 1995 году. Директор - Иван.", encoding="utf-8")

    # 2. Word файл
    create_simple_docx("Это договор аренды помещения. Сумма: 50 000 рублей.", str(test_dir / "doc2.docx"))

    # 3. Excel файл с данными для графика
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Месяц", "Продажи"])
    ws.append(["Январь", 100])
    ws.append(["Февраль", 150])
    ws.append(["Март", 200])
    wb.save(test_dir / "sales.xlsx")

    # 4. Большой файл для чекпоинтов
    big_text = " ".join(["Это очень длинный текст для проверки чекпоинтов."] * 100)
    (test_dir / "big_book.txt").write_text(big_text, encoding="utf-8")

    return test_dir

def main():
    print("=== ЗАПУСК ПОЛНОГО ТЕСТА АГЕНТА ===")
    print("ВНИМАНИЕ: Тест делает много запросов к LLM. Убедитесь, что LM Studio работает!\\n")

    test_dir = setup_test_env()
    print(f"Создана тестовая папка: {test_dir.absolute()}\\n")

    agent = Agent("config.yaml")

    # 1. Тест чтения и орфографии
    print("--- 1. Проверка орфографии ---")
    res = agent.check_spelling_file(str(test_dir / "doc1.txt"))
    print(f"Результат: {res[:100]}...\\n")

    # 2. Тест RAG (Индексация и Вопрос)
    print("--- 2. RAG Индексация и Вопрос ---")
    agent.index_folder(str(test_dir))
    answer = agent.ask_question("В каком году основана компания?")
    print(f"Ответ: {answer}\\n")

    # 3. Тест написания кода
    print("--- 3. Генерация кода ---")
    code = agent.generate_code_with_validation("Напиши функцию сложения двух чисел.")
    print(f"Код:\\n{code}\\n")

    # 4. Тест длинных документов (Checkpoints)
    print("--- 4. Полный разбор длинного документа (Checkpoints) ---")
    res_long = agent.process_long_document(str(test_dir / "big_book.txt"))
    print(f"Результат: {res_long}\\n")

    # 5. Тест списка файлов
    print("--- 5. Создание списка файлов ---")
    csv_file = agent.make_file_list(str(test_dir), recursive=True)
    print(f"Список сохранен: {csv_file}\\n")

    # 6. Тест графика Excel
    print("--- 6. График в Excel ---")
    chart_file = agent.make_excel_chart(str(test_dir / "sales.xlsx"))
    print(f"График сохранен: {chart_file}\\n")

    # 7. Тест сортировки
    print("--- 7. Сортировка файлов ---")
    sorted_dir = agent.classify_files(str(test_dir))
    print(f"Отсортировано в: {sorted_dir}\\n")

    # 8. Тест веб-поиска
    print("--- 8. Веб-поиск ---")
    web_res = agent.web_search("Кто президент России?")
    print(f"Поиск: {web_res[:150]}...\\n")

    print("=== ТЕСТ ЗАВЕРШЕН УСПЕШНО ===")
    print(f"Все результаты сохранены в папке 'output'. Проверь её!")

if __name__ == "__main__":
    main()
"""
}


def create_project():
    print(f"Создание финального патча {PROJECT_NAME}...")
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