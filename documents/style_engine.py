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
        """Возвращает список стилей, используемых в документе."""
        doc = Document(doc_path)
        used_styles = set()
        for p in doc.paragraphs:
            if p.style and p.style.name:
                used_styles.add(p.style.name)
        return sorted(list(used_styles))

    def _copy_styles_from_template(self, target_doc):
        """Копирует недостающие стили из шаблона в целевой документ."""
        for style in self.template_doc.styles:
            if style.name not in [s.name for s in target_doc.styles]:
                try:
                    target_doc.styles.add_style(style.name, style.type)
                except Exception:
                    pass # Игнорируем, если стиль уже существует

    def apply_mapping(self, doc_path: str, mapping: dict, output_name: str = "styled_doc.docx") -> str:
        """Применяет словарь соответствий {старый_стиль: новый_стиль} к документу."""
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
        """Добавляет нумерацию для таблиц и рисунков без номеров."""
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
            instrText.text = " SEQ Таблица \\* ARABIC "
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
