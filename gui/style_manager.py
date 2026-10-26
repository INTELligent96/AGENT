import customtkinter as ctk
from tkinter import filedialog, messagebox
import json
import threading
import os
from documents.style_engine import WordStyleEngine

class StyleManagerWindow(ctk.CTkToplevel):
    def __init__(self, master, agent):
        super().__init__(master)
        self.title("Word Студия Стилей")
        self.geometry("800x600")
        self.agent = agent
        self.engine = None
        self.doc_path = None

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
        path = filedialog.askopenfilename(filetypes=[("Word", "*.docx")])
        if path:
            self.doc_path = path
            self.lbl_doc.configure(text=os.path.basename(path), text_color="white")
            self._update_manual_lists()

    def _build_ai_tab(self):
        ctk.CTkLabel(self.tab_ai, text="ИИ проанализирует стили вашего документа и сопоставит их со стилями шаблона.", wraplength=600).pack(pady=10)
        self.btn_run_ai = ctk.CTkButton(self.tab_ai, text="Запустить ИИ-сопоставление", command=self.run_ai_match)
        self.btn_run_ai.pack(pady=10)
        self.txt_ai_result = ctk.CTkTextbox(self.tab_ai, height=300)
        self.txt_ai_result.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_safe_tab(self):
        text = "Автоматическая замена общих стилей (Заголовки, Обычный текст, Таблицы).\nНе трогает уникальное форматирование."
        ctk.CTkLabel(self.tab_safe, text=text, wraplength=600).pack(pady=10)
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
        text = "Добавить нумерацию для таблиц и рисунков БЕЗ номеров.\nИспользует стили подписей из вашего шаблона."
        ctk.CTkLabel(self.tab_captions, text=text, wraplength=600).pack(pady=10)
        self.btn_run_captions = ctk.CTkButton(self.tab_captions, text="Найти и пронумеровать", command=self.run_captions)
        self.btn_run_captions.pack(pady=10)

    def _update_manual_lists(self):
        if not self.engine or not self.doc_path: return
        doc_styles = self.engine.get_document_styles(self.doc_path)
        tpl_styles = self.engine.template_styles

        for widget in self.scroll_mapping.winfo_children():
            widget.destroy()
        self.mapping_vars = {}

        for d_style in doc_styles:
            frame = ctk.CTkFrame(self.scroll_mapping)
            frame.pack(fill="x", pady=2)

            ctk.CTkLabel(frame, text=d_style, width=200, anchor="w").pack(side="left", padx=5)
            ctk.CTkLabel(frame, text="->").pack(side="left", padx=5)

            combo = ctk.CTkComboBox(frame, values=tpl_styles, width=200)
            combo.set(tpl_styles[0] if tpl_styles else "")
            combo.pack(side="left", padx=5)

            self.mapping_vars[d_style] = combo

    def run_ai_match(self):
        if not self.engine or not self.doc_path: 
            messagebox.showerror("Ошибка", "Сначала выберите шаблон и документ!")
            return

        doc_styles = self.engine.get_document_styles(self.doc_path)
        tpl_styles = self.engine.template_styles

        prompt = f"Ты эксперт по Word. Сопоставь стили из документа со стилями из шаблона.\nСтили документа: {doc_styles}\nСтили шаблона: {tpl_styles}\nВерни ТОЛЬКО валидный JSON словарь (без markdown), где ключ - стиль документа, значение - стиль шаблона.\nЕсли точного совпадения нет, подбери наиболее подходящий по смыслу.\nПример: {{\"Heading 1\": \"ЗАГОЛОВОК 1 УРОВЕНЬ\", \"Normal\": \"Обычный\"}}"

        self.txt_ai_result.delete("1.0", "end")
        self.txt_ai_result.insert("end", "Агент думает...\n")

        def task():
            llm = self.agent.registry.get_model_for_task("default_model")
            res = llm.generate(prompt)
            self.after(0, lambda: self.txt_ai_result.insert("end", f"Предложенное сопоставление:\n{res}\n\nПрименяю..."))

            try:
                clean_json = res.replace("```json", "").replace("```", "").strip()
                mapping = json.loads(clean_json)
                out_file = self.engine.apply_mapping(self.doc_path, mapping, f"AI_STYLED_{os.path.basename(self.doc_path)}")
                self.after(0, lambda: self.txt_ai_result.insert("end", f"Успех! Файл сохранен: {out_file}"))
            except Exception as e:
                self.after(0, lambda: self.txt_ai_result.insert("end", f"Ошибка применения: {e}"))

        threading.Thread(target=task, daemon=True).start()

    def run_safe_match(self):
        if not self.engine or not self.doc_path: return

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
        if not self.engine or not self.doc_path: return
        mapping = {d: combo.get() for d, combo in self.mapping_vars.items()}
        out_file = self.engine.apply_mapping(self.doc_path, mapping, f"MANUAL_STYLED_{os.path.basename(self.doc_path)}")
        messagebox.showinfo("Успех", f"Ручное сопоставление применено!\nФайл: {out_file}")

    def run_captions(self):
        if not self.engine or not self.doc_path: return
        out_file = self.engine.add_captions(self.doc_path, f"CAPTIONED_{os.path.basename(self.doc_path)}")
        messagebox.showinfo("Успех", f"Нумерация добавлена!\nФайл: {out_file}")
