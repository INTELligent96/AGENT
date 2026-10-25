"""Read XLS/XLSX/XLSB/CSV with format detection by signature."""
from pathlib import Path


def _sniff(path: Path) -> str:
    sig = path.read_bytes()[:8]
    if sig.startswith(b"PK"):
        return "xlsx"
    if sig.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    return "unknown"


def extract_excel(path: Path) -> str:
    if path.suffix.lower() == ".csv":
        return path.read_text(encoding="utf-8", errors="replace")

    try:
        from excelreader_native import open_workbook
        wb = open_workbook(str(path))
        lines = []
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            lines.append("### Sheet: " + sheet)
            for row in ws.iter_rows(values_only=True):
                lines.append("\t".join("" if c is None else str(c) for c in row))
        return "\n".join(lines)
    except Exception as e:
        try:
            import pyexcel as p
            sheet = p.get_array(file_name=str(path))
            return "\n".join("\t".join(str(c) for c in row) for row in sheet)
        except Exception as e2:
            raise RuntimeError(
                "Could not read Excel %s: %s / %s" % (path, e, e2)
            )
