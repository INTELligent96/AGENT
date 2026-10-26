import os
from plugins.base import BasePlugin


class WordCountPlugin(BasePlugin):
    # Пример плагина: считает статистику по документу.

    name = "word_count"
    description = "Считает количество слов, символов и абзацев в документе"
    keywords = ["посчитай слова", "статистика документа", "сколько слов", "сколько символов", "подсчет слов"]
    gui_enabled = True
    gui_button_text = "Статистика документа"
    dangerous = False

    def execute(self, user_text: str, agent) -> str:
        file_path = agent._extract_path_from_text(user_text)
        if not file_path:
            return "Укажите файл: 'посчитай слова в D:/Documents/file.docx'"

        text = agent._read_safe(file_path)
        if text.startswith("[Ошибка]"):
            return text

        words = len(text.split())
        chars = len(text)
        chars_clean = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
        paragraphs = len([p for p in text.split("\n\n") if p.strip()])

        lines = [
            "Статистика файла: " + os.path.basename(file_path),
            "- Слов: " + str(words),
            "- Символов (всего): " + str(chars),
            "- Символов (без пробелов): " + str(chars_clean),
            "- Абзацев: " + str(paragraphs),
        ]
        return "\n".join(lines)