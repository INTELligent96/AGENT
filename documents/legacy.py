import os
from pathlib import Path

try:
    import win32com.client
    import pythoncom
    COM_AVAILABLE = True
except ImportError:
    COM_AVAILABLE = False


class LegacyConversionError(Exception):
    pass


def _init_com():
    if COM_AVAILABLE:
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass


def _uninit_com():
    if COM_AVAILABLE:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def convert_legacy_ms_office(file_path):
    if not COM_AVAILABLE:
        raise LegacyConversionError('pywin32 не установлен. Установи: pip install pywin32')

    file_path = Path(file_path).absolute()
    ext = file_path.suffix.lower()

    if ext not in ['.doc', '.xls']:
        return str(file_path)

    _init_com()
    try:
        if ext == '.doc':
            print('Конвертация ' + file_path.name + ' в .docx через Word...')
            word = None
            doc = None
            try:
                word = win32com.client.DispatchEx('Word.Application')
                word.Visible = False
                word.DisplayAlerts = False
                doc = word.Documents.Open(str(file_path), ReadOnly=True)
                new_path = str(file_path.with_suffix('.docx'))
                doc.SaveAs2(new_path, FileFormat=16)
                doc.Close(False)
                doc = None
                return new_path
            finally:
                if doc is not None:
                    try:
                        doc.Close(False)
                    except Exception:
                        pass
                if word is not None:
                    try:
                        word.Quit()
                    except Exception:
                        pass

        elif ext == '.xls':
            print('Конвертация ' + file_path.name + ' в .xlsx через Excel...')
            excel = None
            wb = None
            try:
                excel = win32com.client.DispatchEx('Excel.Application')
                excel.Visible = False
                excel.DisplayAlerts = False
                wb = excel.Workbooks.Open(str(file_path), ReadOnly=True)
                new_path = str(file_path.with_suffix('.xlsx'))
                wb.SaveAs(new_path, FileFormat=51)
                wb.Close(False)
                wb = None
                return new_path
            finally:
                if wb is not None:
                    try:
                        wb.Close(False)
                    except Exception:
                        pass
                if excel is not None:
                    try:
                        excel.Quit()
                    except Exception:
                        pass
    except Exception as e:
        raise LegacyConversionError(str(e))
    finally:
        _uninit_com()

