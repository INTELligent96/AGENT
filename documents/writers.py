from docx import Document
from docxtpl import DocxTemplate
import os

def create_simple_docx(text: str, output_path: str):
    """Создает простой Word-документ из текста."""
    doc = Document()
    doc.add_paragraph(text)
    doc.save(output_path)

def render_template(template_path: str, context: dict, output_path: str):
    """
    Заполняет твой шаблон .docx (с сохранением стилей).
    В шаблоне должны быть метки вроде {{ title }} или {{ text }}.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Шаблон {template_path} не найден!")

    tpl = DocxTemplate(template_path)
    tpl.render(context)
    tpl.save(output_path)
    return output_path
