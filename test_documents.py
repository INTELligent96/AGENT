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

    print("\n--- Тест 2: OCR (Tesseract) ---")
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
