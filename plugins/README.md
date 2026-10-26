# Система плагинов

Плагин - это Python-файл, который добавляет агенту новый инструмент.

## Быстрый старт

1. Создай файл в `plugins/`, например `my_plugin.py`.
2. Напиши код:

```python
from plugins.base import BasePlugin

class MyPlugin(BasePlugin):
    name = "my_plugin"
    description = "Что делает плагин"
    keywords = ["запусти my_plugin", "сделай что-то"]
    gui_enabled = True
    gui_button_text = "Моя кнопка"
    dangerous = False

    def execute(self, user_text, agent):
        return "Результат"
```

3. Перезапусти агент. Плагин появится в чате (по ключевым словам) и в GUI (если `gui_enabled = True`).

## Что доступно в `agent`

- `agent.registry.generate_with_fallback(task, prompt)` - вызвать LLM.
- `agent._read_safe(path)` - прочитать файл (с защитой оригинала).
- `agent._extract_path_from_text(text)` - вытащить путь из текста.
- `agent.output_dir` - папка для результатов.
- `agent.config` - словарь с конфигом.
- `agent.tools` - настройки Tesseract/MS Office.

## Безопасность

- Если `dangerous = True`, в чате агент спросит подтверждение.
- Плагин не должен писать в оригинальные файлы. Используй `agent.output_dir`.