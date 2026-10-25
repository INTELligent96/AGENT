import pandas as pd
import xlsxwriter
from pathlib import Path
import os

def create_excel_chart(file_path: str, output_dir: str = "output") -> str:
    """Читает Excel, строит график по первым двум колонкам и сохраняет."""
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
