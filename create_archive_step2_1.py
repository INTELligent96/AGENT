import os
import zipfile
import textwrap

PROJECT_NAME = "agent_documents_ms_office"

FILES = {
    "config.yaml": """\
llm_profiles:
  local_coder:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen-qwen2.5-coder-14b-instruct"
  local_logic:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "deepseek-r1-0528-qwen3-8b-abliterated"
  local_fast:
    type: "openai_compat"
    base_url: "http://localhost:1235/v1"
    api_key: "lm-studio"
    model_name: "qwen2.5-7b-instruct-uncensored"

routing:
  default_model: "local_fast"
  code_generation: "local_coder"
  complex_reasoning: "local_logic"

tools:
  # Твой путь к Tesseract (диск K)
  tesseract_path: "K:/Program Files/Tesseract-OCR/tesseract.exe"
  # Флаг, что используем MS Office вместо LibreOffice
  use_ms_office: true 
""",

    "documents/__init__.py": "",

    "documents/legacy.py": """\
import os
from pathlib import Path
import win32com.client

def convert_legacy_ms_office(file_path: str) -> str:
    \"\"\"
    Конвертирует .doc -> .docx и .xls -> .xlsx через MS Office COM.
    Возвращает путь к новому файлу.
    \"\"\"
    file_path = Path(file_path).absolute()
    ext = file_path.suffix.lower()

    if ext == '.doc':
        print(f"Конвертация {file_path.name} в .docx через Word...")
        try:
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(str(file_path))
            new_path = str(file_path.with_suffix('.docx'))
            # 16 = wdFormatXMLDocument (.docx)
            doc.SaveAs2(new_path, FileFormat=16)
            doc.Close()
            word.Quit()
            return new_path
        except Exception as e:
            print(f"Ошибка Word COM: {e}")
            return str(file_path)

    elif ext == '.xls':
        print(f"Конвертация {file_path.name} в .xlsx через Excel...")
        try:
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            wb = excel.Workbooks.Open(str(file_path))
            new_path = str(file_path.with_suffix('.xlsx'))
            # 51 = xlOpenXMLWorkbook (.xlsx)
            wb.SaveAs(new_path, FileFormat=51)
            wb.Close()
            excel.Quit()
            return new_path
        except Exception as e:
            print(f"Ошибка Excel COM: {e}")
            return str(file_path)

    return str(file_path)
""",

    "documents/extractors.py": """\
import os
from pathlib import Path
import fitz  # PyMuPDF
from docx import Document
import openpyxl
import pytesseract
from PIL import Image
from .legacy import convert_legacy_ms_office

def extract_text(file_path: str, tools_config: dict) -> str:
    ext = Path(file_path).suffix.lower()

    # Легаси форматы (MS Office)
    if ext in ['.doc', '.xls']:
        if tools_config.get("use_ms_office"):
            file_path = convert_legacy_ms_office(file_path)
            ext = Path(file_path).suffix.lower()
        else:
            return f"[Ошибка] Для файлов {ext} требуется MS Office или включите LibreOffice."

    if ext == '.txt':
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    elif ext == '.docx':
        return extract_docx(file_path)
    elif ext == '.xlsx':
        return extract_excel(file_path)
    elif ext == '.pdf':
        return extract_pdf(file_path, tools_config)
    elif ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']:
        return extract_image(file_path, tools_config)
    else:
        return f"[Ошибка] Неподдерживаемый формат: {ext}"

def extract_docx(file_path: str) -> str:
    doc = Document(file_path)
    text = [para.text for para in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            text.append(" | ".join(cell.text for cell in row.cells))
    return "\\n".join(text)

def extract_excel(file_path: str) -> str:
    wb = openpyxl.load_workbook(file_path, data_only=True)
    text = []
    for sheet in wb.sheetnames:
        text.append(f"--- Лист: {sheet} ---")
        ws = wb[sheet]
        for row in ws.iter_rows(values_only=True):
            row_str = " | ".join(str(cell) if cell is not None else "" for cell in row)
            if row_str.strip():
                text.append(row_str)
    return "\\n".join(text)

def extract_pdf(file_path: str, tools_config: dict) -> str:
    doc = fitz.open(file_path)
    text = []
    for i, page in enumerate(doc):
        page_text = page.get_text()
        if page_text.strip():
            text.append(page_text)
        else:
            pix = page.get_pixmap()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text.append(ocr_image(img, tools_config))
    return "\\n".join(text)

def extract_image(file_path: str, tools_config: dict) -> str:
    img = Image.open(file_path)
    return ocr_image(img, tools_config)

def ocr_image(img: Image.Image, tools_config: dict) -> str:
    tess_path = tools_config.get("tesseract_path")
    if tess_path and os.path.exists(tess_path):
        pytesseract.pytesseract.tesseract_cmd = tess_path
    try:
        return pytesseract.image_to_string(img, lang='rus+eng')
    except Exception as e:
        return f"[Ошибка OCR] Проверь Tesseract: {e}"
""",

    "test_documents.py": """\
import yaml
import os
from documents.extractors import extract_text
from documents.writers import create_simple_docx

def main():
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    tools = config.get("tools", {})

    print("--- Тест 1: Создание и чтение Word (.docx) ---")
    test_file = "test_output.docx"
    create_simple_docx("Привет! Это тестовый документ для проверки.", test_file)
    text = extract_text(test_file, tools)
    print("Успешно прочитан текст:", text)

    print("\\n--- Тест 2: OCR (Tesseract) ---")
    if os.path.exists(tools.get('tesseract_path', '')):
        print(f"Tesseract найден по пути: {tools['tesseract_path']}")
        # Для теста создадим картинку с текстом
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (300, 50), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Test OCR Russian: Привет", fill=(0, 0, 0))
        img.save("test_ocr.png")
        print("Распознанный текст с картинки:", extract_text("test_ocr.png", tools))
    else:
        print(f"[Ошибка] Tesseract не найден: {tools.get('tesseract_path')}")

if __name__ == "__main__":
    main()
"""
}


def create_project():
    print(f"Создание проекта {PROJECT_NAME}...")
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
