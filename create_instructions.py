import textwrap


def generate_manual():
    txt_content = """
================================================================
            AI DOCUMENT AGENT PRO - ПОЛНАЯ ИНСТРУКЦИЯ
================================================================

----------------------------------------------------------------
1. ЧТО ЭТО И ЗАЧЕМ
----------------------------------------------------------------
AI Document Agent PRO — локальный ИИ-агент для работы с документами:
- Word (.docx, .doc), Excel (.xlsx, .xls), PDF, изображения (OCR).
- Поиск по локальным документам (RAG).
- Суммаризация, структурирование, проверка орфографии.
- Создание и изменение Word-документов с сохранением ваших стилей.
- Автоматическая нумерация таблиц и рисунков.
- Написание Python-кода с проверкой и итерациями.
- Построение графиков в Excel.
- Сортировка файлов по категориям.
- Веб-поиск (DuckDuckGo).

Работает полностью локально (через LM Studio), но может подключать внешние API (DeepSeek, Qwen, OpenAI и т.д.).

----------------------------------------------------------------
2. ТРЕБОВАНИЯ К СИСТЕМЕ
----------------------------------------------------------------
- ОС: Windows 10 или 11
- Python: 3.10 (рекомендуется)
- LM Studio: Последняя версия, порт 1235
- Tesseract OCR: С языками rus + eng
- MS Office: Word + Excel (для конвертации .doc/.xls)
- RAM: Минимум 16 ГБ (лучше 32 ГБ)

----------------------------------------------------------------
3. УСТАНОВКА С НУЛЯ
----------------------------------------------------------------
Шаг 1. Скопируй проект в удобную папку, например D:\\DEEPSEEK\\AGENT.
Шаг 2. Установи Python-библиотеки (открой терминал в папке проекта):
  pip install customtkinter python-docx openpyxl PyMuPDF pytesseract Pillow docxtpl xlrd pandas pywin32 chromadb sentence-transformers lxml ddgs xlsxwriter requests pyyaml
Шаг 3. Установи Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
  При установке обязательно отметь «Additional language data» -> Russian и English.
Шаг 4. Пропиши путь к Tesseract в config.yaml:
  tools:
    tesseract_path: "K:/Program Files/Tesseract-OCR/tesseract.exe"
Шаг 5. Установи LM Studio, загрузи модели и включи Local Server на порту 1235.

----------------------------------------------------------------
4. ПЕРВЫЙ ЗАПУСК
----------------------------------------------------------------
1. Убедись, что LM Studio запущен и модели загружены.
2. Проверь имена моделей в config.yaml (блок llm_profiles). Они должны точно совпадать с LM Studio.
3. Запусти агента: python main.py

----------------------------------------------------------------
5. СТРУКТУРА ПРОЕКТА
----------------------------------------------------------------
AGENT/
  main.py               # Точка входа (GUI)
  config.yaml           # Все настройки
  core/                 # Ядро (agent.py, router.py, self_check.py)
  llm/                  # Управление LLM (registry.py, openai_compat.py)
  documents/            # Работа с документами (extractors, writers, style_engine)
  tools/                # Инструменты (validator, file_manager, excel_tools, web_search)
  rag/                  # RAG-подсистема (indexer, qa)
  gui/                  # Интерфейс (app.py, style_manager.py, tooltip.py)
  workspace/            # Копии файлов для безопасной работы
  output/               # Все результаты работы агента
  chroma_db/            # Векторная база RAG (не удалять!)

----------------------------------------------------------------
6. ИНТЕРФЕЙС
----------------------------------------------------------------
Левая панель:
- Тумблеры критика: «Включить критика» и «Всегда (даже для кода)».
- Базовые функции: индексация, орфография, код, длинные документы.
- Word Студия: работа со стилями.
- Данные: CSV-список, Excel-график, пакетное резюме, сортировка.
- Настройки: добавление API-моделей.
- Красная кнопка СТОП внизу — экстренная остановка.

Правая панель (чат):
- Поле ввода для команд на естественном языке.
- Логи: агент показывает каждый шаг ([Роутер], [Инструмент], [Критик]).

Примеры команд в чате:
- "сделай резюме D:/Docs/report.docx"
- "проверь ошибки в файле D:/Docs/letter.txt"
- "напиши код для сортировки списка"
- "построй график в D:/Data/sales.xlsx"
- "найди в интернете новости Python"
- "разложи файлы в D:/Docs/inbox"
- "о чём договор аренды?"

----------------------------------------------------------------
7. РОУТЕР И КРИТИК
----------------------------------------------------------------
Роутер — понимает ваши команды в чате. Сначала ищет ключевые слова, если не находит — спрашивает LLM. 
Критик — вторая модель, которая проверяет ответ первой. Оценивает по шкале 1-10. Если меньше 8 — заставляет переписать. 
Включается/выключается тумблерами в левом меню.

----------------------------------------------------------------
8. WORD СТУДИЯ
----------------------------------------------------------------
Открывается кнопкой «Студия стилей Word». 
1. Выберите шаблон (.docx) со своими стилями.
2. Выберите документ, который нужно преобразовать.
Вкладки:
- ИИ Соответствие: LLM сама сопоставит стили.
- Безопасная замена: жесткие правила (Heading 1 -> Заголовок 1).
- Ручное сопоставление: вы сами выбираете стили из списков.
- Нумерация: добавит "Таблица 1", "Рисунок 1" (с авто-полями Word) для тех таблиц/рисунков, у которых нет названий.

----------------------------------------------------------------
9. ДОБАВЛЕНИЕ API
----------------------------------------------------------------
Нажмите кнопку «Добавить LLM (API)». Заполните: название, URL, ключ, имя модели. 
Снимите галочку «Локальная», если это внешний сервис. Сохраните. Перезапустите агент.

----------------------------------------------------------------
10. ЧАСТЫЕ ПРОБЛЕМЫ
----------------------------------------------------------------
- 500 Server Error: Модель упала. Проверьте Context Length в LM Studio (>= 4096). Агент сам попробует уменьшить токены или переключиться.
- Модель не найдена: Имя в config.yaml не совпадает с LM Studio.
- Tesseract не видит русский: Переустановите с пакетами rus и eng.
- Агент не отвечает: LM Studio не запущен или порт не 1235.
- Медленно работает: Отключите критика, используйте 7B модели для простых задач.

================================================================
                Готово! Агент полностью настроен.
================================================================
"""

    html_content = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>AI Document Agent PRO - Инструкция</title>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; padding: 20px; background-color: #f4f7f6; }
        h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
        h2 { color: #2980b9; margin-top: 30px; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; }
        h3 { color: #16a085; }
        p { margin-bottom: 15px; }
        ul, ol { margin-bottom: 15px; padding-left: 20px; }
        li { margin-bottom: 5px; }
        code { background-color: #ecf0f1; color: #c0392b; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; }
        pre { background-color: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 8px; overflow-x: auto; font-family: Consolas, monospace; }
        pre code { background-color: transparent; color: inherit; padding: 0; }
        .alert { background-color: #ffeaa7; border-left: 5px solid #fdcb6e; padding: 15px; margin-bottom: 20px; border-radius: 4px; }
        .danger { background-color: #ff7675; color: white; border-left: 5px solid #d63031; padding: 15px; margin-bottom: 20px; border-radius: 4px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        th, td { border: 1px solid #bdc3c7; padding: 10px; text-align: left; }
        th { background-color: #ecf0f1; font-weight: bold; }
        .toc { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 30px; }
        .toc a { text-decoration: none; color: #3498db; }
        .toc a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>🤖 AI Document Agent PRO</h1>
    <div class="toc">
        <h3>Содержание</h3>
        <ul>
            <li><a href="#sec1">1. Что это и зачем</a></li>
            <li><a href="#sec2">2. Требования к системе</a></li>
            <li><a href="#sec3">3. Установка с нуля</a></li>
            <li><a href="#sec4">4. Первый запуск</a></li>
            <li><a href="#sec5">5. Интерфейс</a></li>
            <li><a href="#sec6">6. Роутер и Критик</a></li>
            <li><a href="#sec7">7. Word Студия</a></li>
            <li><a href="#sec8">8. Добавление API</a></li>
            <li><a href="#sec9">9. Частые проблемы</a></li>
        </ul>
    </div>

    <h2 id="sec1">1. Что это и зачем</h2>
    <p>Локальный ИИ-агент для работы с документами Word, Excel, PDF и картинками.</p>
    <ul>
        <li>Поиск по локальным документам (RAG).</li>
        <li>Суммаризация, проверка орфографии, написание кода.</li>
        <li>Создание документов Word с сохранением ваших стилей.</li>
        <li>Автоматическая нумерация таблиц и рисунков.</li>
        <li>Сортировка файлов, графики в Excel, веб-поиск.</li>
    </ul>

    <h2 id="sec2">2. Требования к системе</h2>
    <table>
        <tr><th>Компонент</th><th>Требование</th></tr>
        <tr><td>ОС</td><td>Windows 10 / 11</td></tr>
        <tr><td>Python</td><td>3.10</td></tr>
        <tr><td>LM Studio</td><td>Порт 1235</td></tr>
        <tr><td>Tesseract OCR</td><td>Языки rus + eng</td></tr>
        <tr><td>MS Office</td><td>Word + Excel</td></tr>
        <tr><td>RAM</td><td>От 16 ГБ</td></tr>
    </table>

    <h2 id="sec3">3. Установка с нуля</h2>
    <div class="alert">
        <strong>Внимание:</strong> Установите все библиотеки через <code>pip install</code>, а также Tesseract OCR и LM Studio.
    </div>
    <pre><code>pip install customtkinter python-docx openpyxl PyMuPDF pytesseract Pillow docxtpl xlrd pandas pywin32 chromadb sentence-transformers lxml ddgs xlsxwriter requests pyyaml</code></pre>
    <p>Путь к Tesseract прописывается в <code>config.yaml</code> в блоке <code>tools</code>.</p>

    <h2 id="sec5">5. Интерфейс</h2>
    <p><strong>Левая панель:</strong> кнопки инструментов, тумблеры критика, настройки API.</p>
    <p><strong>Правая панель:</strong> чат для общения с агентом на естественном языке (например: <em>"сделай резюме D:/Docs/report.docx"</em>).</p>

    <h2 id="sec6">6. Роутер и Критик</h2>
    <p><strong>Роутер</strong> — понимает ваши команды. Ищет ключевые слова (например, "напиши код"), если не находит — спрашивает LLM.</p>
    <p><strong>Критик</strong> — проверяет ответы ИИ. Оценивает по шкале 1-10. Если оценка ниже 8, заставляет ИИ переписать ответ. Включается галочками в меню.</p>

    <h2 id="sec7">7. Word Студия</h2>
    <p>Кнопка «Студия стилей Word». Позволяет:</p>
    <ul>
        <li>Автоматически перенести ваши стили из шаблона в документ.</li>
        <li>Сопоставить стили через ИИ.</li>
        <li>Добавить нумерацию "Таблица 1", "Рисунок 1" для тех объектов, у которых нет названий.</li>
    </ul>

    <h2 id="sec9">9. Частые проблемы</h2>
    <table>
        <tr><th>Проблема</th><th>Решение</th></tr>
        <tr><td>500 Server Error</td><td>Увеличьте Context Length в LM Studio (>= 4096)</td></tr>
        <tr><td>Модель не найдена</td><td>Проверьте имя в config.yaml</td></tr>
        <tr><td>Медленно работает</td><td>Отключите критика, используйте 7B модель</td></tr>
    </table>

    <div class="danger">
        <strong>Безопасность:</strong> Агент никогда не изменяет оригинальные файлы. Все результаты сохраняются в папке <code>output/</code>.
    </div>

</body>
</html>
"""

    with open("ИНСТРУКЦИЯ.txt", "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(txt_content))

    with open("ИНСТРУКЦИЯ.html", "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(html_content))

    print("✅ Созданы два файла:")
    print("1. ИНСТРУКЦИЯ.txt — обычный текст (можно открыть в Блокноте)")
    print("2. ИНСТРУКЦИЯ.html — красивая веб-страница (двойной клик откроет в браузере)")


if __name__ == "__main__":
    generate_manual()