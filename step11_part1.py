import os
import zipfile

# Все файлы будем писать как списки строк и склеивать через \n.
# Так внутри ответа не будет ни одной тройной кавычки.

BASE_PY = "\n".join([
    "from abc import ABC, abstractmethod",
    "",
    "class BasePlugin(ABC):",
    "    # Базовый класс для всех плагинов.",
    "    # Чтобы создать плагин:",
    "    # 1. Создай файл в папке plugins/ (например, my_tool.py)",
    "    # 2. Унаследуй класс от BasePlugin",
    "    # 3. Заполни name, description, keywords",
    "    # 4. Реализуй execute()",
    "    # 5. Перезапусти агента - плагин подхватится автоматически.",
    "",
    "    name = \"unknown_plugin\"",
    "    description = \"\"",
    "    keywords = []",
    "    gui_enabled = False",
    "    gui_button_text = \"\"",
    "    dangerous = False",
    "",
    "    @abstractmethod",
    "    def execute(self, user_text: str, agent) -> str:",
    "        # Выполняет плагин и возвращает строку-результат.",
    "        # :param user_text: Полный текст запроса пользователя",
    "        # :param agent: Экземпляр Agent (доступ к registry, workspace, output_dir, _read_safe)",
    "        # :return: Строка с результатом",
    "        raise NotImplementedError",
])

LOADER_PY = "\n".join([
    "import importlib.util",
    "import inspect",
    "from pathlib import Path",
    "from plugins.base import BasePlugin",
    "",
    "",
    "def load_plugins(plugins_dir=\"plugins\"):",
    "    # Сканирует папку plugins/ и возвращает словарь {name: instance}.",
    "    plugins = {}",
    "    plugins_path = Path(plugins_dir)",
    "",
    "    if not plugins_path.exists():",
    "        print(\"[Плагины] Папка не найдена, пропуск.\")",
    "        return plugins",
    "",
    "    skip_files = [\"__init__.py\", \"base.py\", \"loader.py\"]",
    "",
    "    for file in sorted(plugins_path.glob(\"*.py\")):",
    "        if file.name in skip_files or file.name.startswith(\"_\"):",
    "            continue",
    "",
    "        try:",
    "            spec = importlib.util.spec_from_file_location(file.stem, file)",
    "            module = importlib.util.module_from_spec(spec)",
    "            spec.loader.exec_module(module)",
    "",
    "            found = False",
    "            for cls_name, obj in inspect.getmembers(module, inspect.isclass):",
    "                if issubclass(obj, BasePlugin) and obj is not BasePlugin:",
    "                    if obj.__module__ == module.__name__:",
    "                        instance = obj()",
    "                        if instance.name in plugins:",
    "                            print(\"[Плагины] Дубликат: \" + instance.name + \" - пропуск.\")",
    "                            continue",
    "                        plugins[instance.name] = instance",
    "                        print(\"[Плагины] Загружен: \" + instance.name + \" (\" + file.name + \")\")",
    "                        found = True",
    "",
    "            if not found:",
    "                print(\"[Плагины] В \" + file.name + \" не найдено классов-наследников BasePlugin.\")",
    "",
    "        except Exception as e:",
    "            print(\"[Плагины] Ошибка в \" + file.name + \": \" + str(e))",
    "",
    "    print(\"[Плагины] Всего загружено: \" + str(len(plugins)))",
    "    return plugins",
])

WORD_COUNT_PY = "\n".join([
    "import os",
    "from plugins.base import BasePlugin",
    "",
    "",
    "class WordCountPlugin(BasePlugin):",
    "    # Пример плагина: считает статистику по документу.",
    "",
    "    name = \"word_count\"",
    "    description = \"Считает количество слов, символов и абзацев в документе\"",
    "    keywords = [\"посчитай слова\", \"статистика документа\", \"сколько слов\", \"сколько символов\", \"подсчет слов\"]",
    "    gui_enabled = True",
    "    gui_button_text = \"Статистика документа\"",
    "    dangerous = False",
    "",
    "    def execute(self, user_text: str, agent) -> str:",
    "        file_path = agent._extract_path_from_text(user_text)",
    "        if not file_path:",
    "            return \"Укажите файл: 'посчитай слова в D:/Documents/file.docx'\"",
    "",
    "        text = agent._read_safe(file_path)",
    "        if text.startswith(\"[Ошибка]\"):",
    "            return text",
    "",
    "        words = len(text.split())",
    "        chars = len(text)",
    "        chars_clean = len(text.replace(\" \", \"\").replace(\"\\n\", \"\").replace(\"\\t\", \"\"))",
    "        paragraphs = len([p for p in text.split(\"\\n\\n\") if p.strip()])",
    "",
    "        lines = [",
    "            \"Статистика файла: \" + os.path.basename(file_path),",
    "            \"- Слов: \" + str(words),",
    "            \"- Символов (всего): \" + str(chars),",
    "            \"- Символов (без пробелов): \" + str(chars_clean),",
    "            \"- Абзацев: \" + str(paragraphs),",
    "        ]",
    "        return \"\\n\".join(lines)",
])

README_MD = "\n".join([
    "# Система плагинов",
    "",
    "Плагин - это Python-файл, который добавляет агенту новый инструмент.",
    "",
    "## Быстрый старт",
    "",
    "1. Создай файл в `plugins/`, например `my_plugin.py`.",
    "2. Напиши код:",
    "",
    "```python",
    "from plugins.base import BasePlugin",
    "",
    "class MyPlugin(BasePlugin):",
    "    name = \"my_plugin\"",
    "    description = \"Что делает плагин\"",
    "    keywords = [\"запусти my_plugin\", \"сделай что-то\"]",
    "    gui_enabled = True",
    "    gui_button_text = \"Моя кнопка\"",
    "    dangerous = False",
    "",
    "    def execute(self, user_text, agent):",
    "        return \"Результат\"",
    "```",
    "",
    "3. Перезапусти агент. Плагин появится в чате (по ключевым словам) и в GUI (если `gui_enabled = True`).",
    "",
    "## Что доступно в `agent`",
    "",
    "- `agent.registry.generate_with_fallback(task, prompt)` - вызвать LLM.",
    "- `agent._read_safe(path)` - прочитать файл (с защитой оригинала).",
    "- `agent._extract_path_from_text(text)` - вытащить путь из текста.",
    "- `agent.output_dir` - папка для результатов.",
    "- `agent.config` - словарь с конфигом.",
    "- `agent.tools` - настройки Tesseract/MS Office.",
    "",
    "## Безопасность",
    "",
    "- Если `dangerous = True`, в чате агент спросит подтверждение.",
    "- Плагин не должен писать в оригинальные файлы. Используй `agent.output_dir`.",
])


def main():
    files = {
        "plugins/__init__.py": "",
        "plugins/base.py": BASE_PY,
        "plugins/loader.py": LOADER_PY,
        "plugins/word_count.py": WORD_COUNT_PY,
        "plugins/README.md": README_MD,
    }

    for path, content in files.items():
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("[OK] " + path)

    # Создаём архив
    with zipfile.ZipFile("step11_part1.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for path in files.keys():
            z.write(path)

    print("\nГотово! Создан step11_part1.zip")
    print("Распакуй поверх проекта. Файлы плагинов появятся в папке plugins/.")


if __name__ == "__main__":
    main()