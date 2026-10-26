import os
import zipfile
import textwrap

PROJECT_NAME = "agent_word_studio"

FILES = {
    # Ядро работы со стилями
    "documents/style_engine.py": """\
import os
import re
import json
import copy
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

class WordStyleEngine:
    def __init__(self, template_path: str, output_dir="output"):
        self.template_path = template_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Загружаем шаблон, чтобы знать его стили
        self.template_doc = Document(template_path)
        self.template_styles = [s.name for s in self.template_doc.styles if s.type == 1] # 1 = Paragraph

    def get_document_styles(self, doc_path: str) -> list:
        \"\"\"Возвращает список стилей, используемых в документе.\"\"\"
        doc = Document(doc_path)
        used_styles = set()
        for p in doc.paragraphs:
            if p.style and p.style.name:
                used_styles.add(p.style.name)
        return sorted(list(used_styles))

    def _copy_styles_from_template(self, target_doc):
        \"\"\"Копирует недостающие стили из шаблона в целевой документ.\"\"\"
        for style in self.template_doc.styles:
            if style.name not in [s.name for s in target_doc.styles]:
                try:
                    target_doc.styles.add_style(style.name, style.type)
                except Exception:
                    pass # Игнорируем, если стиль уже существует

    def apply_mapping(self, doc_path: str, mapping: dict, output_name: str = "styled_doc.docx") -> str:
        \"\"\"Применяет словарь соответствий {старый_стиль: новый_стиль} к документу.\"\"\"
        doc = Document(doc_path)
        self._copy_styles_from_template(doc) # Подтягиваем стили из шаблона

        for p in doc.paragraphs:
            if p.style and p.style.name in mapping:
                new_style = mapping[p.style.name]
                try:
                    p.style = new_style
                except Exception as e:
                    print(f"Не удалось применить стиль {new_style}: {e}")

        # Работаем с таблицами
        for table in doc.tables:
            if table.style and table.style.name in mapping:
                new_style = mapping[table.style.name]
                try:
                    table.style = new_style
                except Exception:
                    pass

        out_path = self.output_dir / output_name
        doc.save(out_path)
        return str(out_path)

    def add_captions(self, doc_path: str, output_name: str = "captioned_doc.docx") -> str:
        \"\"\"Добавляет нумерацию для таблиц и рисунков без номеров.\"\"\"
        doc = Document(doc_path)
        self._copy_styles_from_template(doc)

        # Ищем стиль для подписей в шаблоне
        caption_style_name = "Caption" # По умолчанию
        for s in self.template_styles:
            if "название" in s.lower() or "подпись" in s.lower() or "caption" in s.lower():
                caption_style_name = s
                break

        # 1. Таблицы
        table_count = 0
        for i, table in enumerate(doc.tables):
            # Проверяем абзац перед таблицей
            if i > 0:
                prev_p = doc.paragraphs[i-1] if i-1 < len(doc.paragraphs) else None
                if prev_p and re.match(r'^Таблица\s+\d+', prev_p.text, re.IGNORECASE):
                    continue # Уже есть номер

            # Добавляем подпись (упрощенно: ищем по всему тексту)
            # В python-docx сложно вставить абзац СТРОГО перед таблицей, 
            # поэтому используем XML-вставку
            p = OxmlElement('w:p')
            table._element.addprevious(p)
            new_p = doc.add_paragraph() # Костыль для инициализации
            table._element.addprevious(new_p._element)

            new_p.text = f"Таблица {table_count + 1}. "
            new_p.style = caption_style_name

            # Добавляем SEQ поле для авто-нумерации в Word
            run = new_p.add_run()
            fldChar1 = OxmlElement('w:fldChar')
            fldChar1.set(qn('w:fldCharType'), 'begin')
            instrText = OxmlElement('w:instrText')
            instrText.set(qn('xml:space'), 'preserve')
            instrText.text = " SEQ Таблица \\\\* ARABIC "
            fldChar2 = OxmlElement('w:fldChar')
            fldChar2.set(qn('w:fldCharType'), 'separate')
            t = OxmlElement('w:t')
            t.text = str(table_count + 1)
            fldChar3 = OxmlElement('w:fldChar')
            fldChar3.set(qn('w:fldCharType'), 'end')

            run._r.append(fldChar1)
            run._r.append(instrText)
            run._r.append(fldChar2)
            run._r.append(t)
            run._r.append(fldChar3)

            table_count += 1

        # 2. Рисунки (Inline Shapes)
        # В python-docx сложно привязать рисунок к абзацу напрямую, 
        # ищем абзацы с текстом "Рисунок" или пустые абзацы с картинками
        # Для простоты пройдемся по абзацам и проверим наличие XML-тегов картинок
        fig_count = 0
        for p in doc.paragraphs:
            if '<w:drawing>' in p._p.xml:
                # Проверяем, есть ли уже подпись
                if re.search(r'Рисунок\s+\d+', p.text, re.IGNORECASE):
                    continue

                fig_count += 1
                # Вставляем подпись после абзаца с картинкой
                new_p = doc.add_paragraph()
                p._element.addnext(new_p._element)
                new_p.text = f"Рисунок {fig_count}. "
                new_p.style = caption_style_name

        out_path = self.output_dir / output_name
        doc.save(out_path)
        return str(out_path)
""",

    # Окно Студии Стилей
    "gui/style_manager.py": """\
import customtkinter as ctk
from tkinter import filedialog, messagebox
import json
import threading
from documents.style_engine import WordStyleEngine
from llm.registry import LLMRegistry

class StyleManagerWindow(ctk.CTkToplevel):
    def __init__(self, master, agent):
        super().__init__(master)
        self.title("Word Студия Стилей")
        self.geometry("800x600")
        self.agent = agent
        self.engine = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Верхняя панель
        top_frame = ctk.CTkFrame(self)
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        self.btn_template = ctk.CTkButton(top_frame, text="1. Выбрать шаблон (.docx)", command=self.load_template)
        self.btn_template.pack(side="left", padx=10)
        self.lbl_template = ctk.CTkLabel(top_frame, text="Шаблон не выбран", text_color="gray")
        self.lbl_template.pack(side="left", padx=10)

        self.btn_doc = ctk.CTkButton(top_frame, text="2. Выбрать документ", command=self.load_doc)
        self.btn_doc.pack(side="left", padx=(30, 10))
        self.lbl_doc = ctk.CTkLabel(top_frame, text="Документ не выбран", text_color="gray")
        self.lbl_doc.pack(side="left", padx=10)

        # Вкладки с методами
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self.tab_ai = self.tabview.add("🤖 ИИ Соответствие")
        self.tab_safe = self.tabview.add("🛡️ Безопасная замена")
        self.tab_manual = self.tabview.add("⚙️ Ручное сопоставление")
        self.tab_captions = self.tabview.add("🔢 Нумерация таблиц/рисунков")

        self._build_ai_tab()
        self._build_safe_tab()
        self._build_manual_tab()
        self._build_captions_tab()

    def load_template(self):
        path = filedialog.askopenfilename(filetypes=[("Word", "*.docx")])
        if path:
            self.engine = WordStyleEngine(path)
            self.lbl_template.configure(text=os.path.basename(path), text_color="white")
            self._update_manual_lists()

    def load_doc(self):
        self.doc_path = filedialog.askopenfilename(filetypes=[("Word", "*.docx")])
        if self.doc_path:
            self.lbl_doc.configure(text=os.path.basename(self.doc_path), text_color="white")

    def _build_ai_tab(self):
        ctk.CTkLabel(self.tab_ai, text="ИИ проанализирует стили вашего документа и сопоставит их со стилями шаблона.", wraplength=600).pack(pady=10)
        self.btn_run_ai = ctk.CTkButton(self.tab_ai, text="Запустить ИИ-сопоставление", command=self.run_ai_match)
        self.btn_run_ai.pack(pady=10)
        self.txt_ai_result = ctk.CTkTextbox(self.tab_ai, height=300)
        self.txt_ai_result.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_safe_tab(self):
        ctk.CTkLabel(self.tab_safe, text="Автоматическая замена общих стилей (Заголовки, Обычный текст, Таблицы).\nНе трогает уникальное форматирование.", wraplength=600).pack(pady=10)
        self.btn_run_safe = ctk.CTkButton(self.tab_safe, text="Выполнить безопасную замену", command=self.run_safe_match)
        self.btn_run_safe.pack(pady=10)

    def _build_manual_tab(self):
        ctk.CTkLabel(self.tab_manual, text="Выберите, какой стиль из документа заменить на стиль из шаблона.").pack(pady=5)

        self.scroll_mapping = ctk.CTkScrollableFrame(self.tab_manual, height=300)
        self.scroll_mapping.pack(fill="both", expand=True, padx=10, pady=5)

        self.btn_apply_manual = ctk.CTkButton(self.tab_manual, text="Применить ручное сопоставление", command=self.run_manual_match)
        self.btn_apply_manual.pack(pady=10)

        self.mapping_vars = {}
        self.mapping_combos = {}

    def _build_captions_tab(self):
        ctk.CTkLabel(self.tab_captions, text="Добавить нумерацию для таблиц и рисунков БЕЗ номеров.\nИспользует стили подписей из вашего шаблона.", wraplength=600).pack(pady=10)
        self.btn_run_captions = ctk.CTkButton(self.tab_captions, text="Найти и пронумеровать", command=self.run_captions)
        self.btn_run_captions.pack(pady=10)

    def _update_manual_lists(self):
        if not self.engine or not hasattr(self, 'doc_path'): return
        doc_styles = self.engine.get_document_styles(self.doc_path)
        tpl_styles = self.engine.template_styles

        # Очищаем старые
        for widget in self.scroll_mapping.winfo_children():
            widget.destroy()
        self.mapping_vars = {}
        self.mapping_combos = {}

        for i, d_style in enumerate(doc_styles):
            frame = ctk.CTkFrame(self.scroll_mapping)
            frame.pack(fill="x", pady=2)

            ctk.CTkLabel(frame, text=d_style, width=200, anchor="w").pack(side="left", padx=5)
            ctk.CTkLabel(frame, text="->").pack(side="left", padx=5)

            combo = ctk.CTkComboBox(frame, values=tpl_styles, width=200)
            combo.set(tpl_styles[0] if tpl_styles else "")
            combo.pack(side="left", padx=5)

            self.mapping_vars[d_style] = combo

    def run_ai_match(self):
        if not self.engine or not hasattr(self, 'doc_path'): 
            messagebox.showerror("Ошибка", "Сначала выберите шаблон и документ!")
            return

        doc_styles = self.engine.get_document_styles(self.doc_path)
        tpl_styles = self.engine.template_styles

        prompt = f\"\"\"
        Ты эксперт по Word. Сопоставь стили из документа со стилями из шаблона.
        Стили документа: {doc_styles}
        Стили шаблона: {tpl_styles}
        Верни ТОЛЬКО валидный JSON словарь (без markdown), где ключ - стиль документа, значение - стиль шаблона.
        Если точного совпадения нет, подбери наиболее подходящий по смыслу.
        Пример: {{"Heading 1": "ЗАГОЛОВОК 1 УРОВЕНЬ", "Normal": "Обычный"}}
        \"\"\"

        self.txt_ai_result.delete("1.0", "end")
        self.txt_ai_result.insert("end", "Агент думает...\n")

        def task():
            llm = self.agent.registry.get_model_for_task("default_model")
            res = llm.generate(prompt)
            self.after(0, lambda: self.txt_ai_result.insert("end", f"Предложенное сопоставление:\n{res}\n\nПрименяю..."))

            try:
                # Очищаем от возможных ```json
                clean_json = res.replace("```json", "").replace("```", "").strip()
                mapping = json.loads(clean_json)
                out_file = self.engine.apply_mapping(self.doc_path, mapping, f"AI_STYLED_{os.path.basename(self.doc_path)}")
                self.after(0, lambda: self.txt_ai_result.insert("end", f"Успех! Файл сохранен: {out_file}"))
            except Exception as e:
                self.after(0, lambda: self.txt_ai_result.insert("end", f"Ошибка применения: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def run_safe_match(self):
        if not self.engine or not hasattr(self, 'doc_path'): return

        # Базовые правила
        mapping = {}
        for d_style in self.engine.get_document_styles(self.doc_path):
            d_lower = d_style.lower()
            for t_style in self.engine.template_styles:
                t_lower = t_style.lower()
                if "заголовок 1" in d_lower and "заголовок 1" in t_lower:
                    mapping[d_style] = t_style
                elif "заголовок 2" in d_lower and "заголовок 2" in t_lower:
                    mapping[d_style] = t_style
                elif d_lower == "normal" or d_lower == "обычный":
                    if t_lower == "обычный" or t_lower == "normal":
                        mapping[d_style] = t_style

        out_file = self.engine.apply_mapping(self.doc_path, mapping, f"SAFE_STYLED_{os.path.basename(self.doc_path)}")
        messagebox.showinfo("Успех", f"Безопасная замена выполнена!\nФайл: {out_file}")

    def run_manual_match(self):
        if not self.engine: return
        mapping = {d: combo.get() for d, combo in self.mapping_vars.items()}
        out_file = self.engine.apply_mapping(self.doc_path, mapping, f"MANUAL_STYLED_{os.path.basename(self.doc_path)}")
        messagebox.showinfo("Успех", f"Ручное сопоставление применено!\nФайл: {out_file}")

    def run_captions(self):
        if not self.engine or not hasattr(self, 'doc_path'): return
        out_file = self.engine.add_captions(self.doc_path, f"CAPTIONED_{os.path.basename(self.doc_path)}")
        messagebox.showinfo("Успех", f"Нумерация добавлена!\nФайл: {out_file}")

import os
""",

    # Обновленный GUI приложения (добавили кнопку)
    "gui/app.py": """\
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
            self.chat_display.insert("end", text + "\\n")
            self.chat_display.see("end")
            self.chat_display.configure(state="disabled")
        self.after(0, _update)

    def run_in_thread(self, func, *args):
        def wrapper():
            try: func(*args)
            except Exception as e: self.log(f"\\n[ОШИБКА]: {str(e)}\\n")
        threading.Thread(target=wrapper, daemon=True).start()

    def open_style_studio(self):
        StyleManagerWindow(self, self.agent)

    # ... остальные методы (index_folder, check_spell и т.д.) оставляем без изменений ...
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
"""
}


def create_project():
    print(f"Создание Word Студии {PROJECT_NAME}...")
    for filepath, content in FILES.items():
        clean_content = textwrap.dedent(content)
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(clean_content)
        print(f"  Обновлен/Создан: {filepath}")

    zip_name = f"{PROJECT_NAME}.zip"
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filepath in FILES.keys():
            zipf.write(filepath)
    print(f"\\nГотово! Архив {zip_name} создан.")


if __name__ == "__main__":
    create_project()
