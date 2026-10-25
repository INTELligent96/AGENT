import os
from pathlib import Path
import csv

def generate_file_list(folder_path: str, recursive: bool = True, output_dir: str = "output") -> str:
    """Генерирует список файлов в папке и сохраняет в CSV."""
    Path(output_dir).mkdir(exist_ok=True)
    folder = Path(folder_path)

    files_data = []
    if recursive:
        for f in folder.rglob('*'):
            if f.is_file():
                files_data.append([f.name, str(f.parent), f.stat().st_size, f.suffix])
    else:
        for f in folder.glob('*'):
            if f.is_file():
                files_data.append([f.name, str(f.parent), f.stat().st_size, f.suffix])

    out_file = Path(output_dir) / f"file_list_{folder.name}.csv"
    with open(out_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(["Имя файла", "Папка", "Размер (байт)", "Расширение"])
        writer.writerows(files_data)

    return str(out_file)
