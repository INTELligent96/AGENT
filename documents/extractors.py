import os
from pathlib import Path
import pymupdf as fitz
from docx import Document
import openpyxl
import pytesseract
from PIL import Image
from .legacy import convert_legacy_ms_office, LegacyConversionError, COM_AVAILABLE


def extract_pages(file_path, tools_config):
    # Возвращает список [{'text': str, 'meta': {}}]
    ext = Path(file_path).suffix.lower()

    if ext in ['.doc', '.xls']:
        if not tools_config.get('use_ms_office'):
            return [{'text': '[Ошибка] Для ' + ext + ' нужен MS Office', 'meta': {}}]
        if not COM_AVAILABLE:
            return [{'text': '[Ошибка] pywin32 не установлен', 'meta': {}}]
        orig_path = str(file_path)
        try:
            new_path = convert_legacy_ms_office(file_path)
            print('  [Legacy] Сконвертировано: ' + new_path)
            pages = extract_pages(new_path, tools_config)
            for p in pages:
                p['meta']['source'] = orig_path
                p['meta']['original_filename'] = Path(orig_path).name
                p['meta']['converted_from'] = ext
            return pages
        except LegacyConversionError as e:
            full = str(e)
            print('  [Legacy ERROR] ' + full[:300])
            return [{'text': '[Ошибка конвертации]: ' + full, 'meta': {}}]

    if ext == '.txt':
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return [{'text': f.read(), 'meta': {}}]
    elif ext == '.docx':
        return _extract_pages_docx(file_path)
    elif ext == '.xlsx':
        return _extract_pages_xlsx(file_path)
    elif ext == '.pdf':
        return _extract_pages_pdf(file_path, tools_config)
    elif ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']:
        img = Image.open(file_path)
        return [{'text': _ocr_image(img, tools_config), 'meta': {}}]
    else:
        return [{'text': '[Ошибка] Неподдерживаемый формат: ' + ext, 'meta': {}}]


def extract_text(file_path, tools_config):
    # Совместимость: возвращает строку
    pages = extract_pages(file_path, tools_config)
    parts = []
    for p in pages:
        meta = p.get('meta', {})
        marker = ''
        if 'page' in meta:
            marker = '[Стр. ' + str(meta['page']) + '] '
        elif 'section' in meta:
            marker = '[Раздел: ' + meta['section'] + '] '
        elif 'sheet' in meta:
            marker = '[Лист: ' + meta['sheet'] + '] '
        parts.append(marker + p['text'])
    return '\n'.join(parts)


def _extract_pages_pdf(file_path, tools_config):
    doc = fitz.open(file_path)
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text()
        if not text.strip():
            pix = page.get_pixmap()
            img = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
            text = _ocr_image(img, tools_config)
        if text.strip():
            pages.append({'text': text, 'meta': {'page': i + 1}})
    return pages


def _extract_pages_docx(file_path):
    doc = Document(file_path)
    pages = []
    current_path = []   # иерархия заголовков
    current_text = []

    for para in doc.paragraphs:
        try:
            style = para.style.name.lower() if para.style else ''
        except Exception:
            style = ''

        level = None
        if 'heading 1' in style or 'заголовок 1' in style:
            level = 1
        elif 'heading 2' in style or 'заголовок 2' in style:
            level = 2
        elif 'heading 3' in style or 'заголовок 3' in style:
            level = 3

        if level is not None and para.text.strip():
            if current_text:
                section_name = ' → '.join(current_path) if current_path else 'Начало'
                pages.append({'text': '\n'.join(current_text), 'meta': {'section': section_name}})
                current_text = []
            current_path = current_path[:level - 1]
            current_path.append(para.text.strip())

        if para.text.strip():
            current_text.append(para.text)

    if current_text:
        section_name = ' → '.join(current_path) if current_path else 'Начало'
        pages.append({'text': '\n'.join(current_text), 'meta': {'section': section_name}})

    for table in doc.tables:
        rows = []
        for row in table.rows:
            rows.append(' | '.join(c.text for c in row.cells))
        text = '\n'.join(rows)
        if text.strip():
            section_name = ' → '.join(current_path) if current_path else 'Начало'
            pages.append({'text': text, 'meta': {'section': section_name + ' (таблица)'}})

    return pages


def _extract_pages_xlsx(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    pages = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            row_str = ' | '.join(str(c) if c is not None else '' for c in row)
            if row_str.strip():
                rows.append(row_str)
        if rows:
            pages.append({'text': '\n'.join(rows), 'meta': {'sheet': sheet_name}})
    return pages


def _ocr_image(img, tools_config):
    tess_path = tools_config.get('tesseract_path')
    if tess_path and os.path.exists(tess_path):
        pytesseract.pytesseract.tesseract_cmd = tess_path
    try:
        return pytesseract.image_to_string(img, lang='rus+eng')
    except Exception as e:
        return '[Ошибка OCR]: ' + str(e)

