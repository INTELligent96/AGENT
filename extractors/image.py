"""Image handling: base64 and local OCR."""
import base64
import io
from pathlib import Path


def prepare_image(path: Path, max_size: int = 1600) -> str:
    from PIL import Image
    img = Image.open(path)
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    fmt = "JPEG" if img.mode in ("RGB", "L") else "PNG"
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode()


def ocr_image_tesseract(path: Path, lang: str = "rus+eng") -> str:
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(path), lang=lang)
    except Exception as e:
        return "[OCR unavailable: %s]" % e
