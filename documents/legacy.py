import os
from pathlib import Path
import win32com.client

def convert_legacy_ms_office(file_path: str) -> str:
    """
    Конвертирует .doc -> .docx и .xls -> .xlsx через MS Office COM.
    Возвращает путь к новому файлу.
    """
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
