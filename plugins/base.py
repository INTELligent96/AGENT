from abc import ABC, abstractmethod

class BasePlugin(ABC):
    # Базовый класс для всех плагинов.
    # Чтобы создать плагин:
    # 1. Создай файл в папке plugins/ (например, my_tool.py)
    # 2. Унаследуй класс от BasePlugin
    # 3. Заполни name, description, keywords
    # 4. Реализуй execute()
    # 5. Перезапусти агента - плагин подхватится автоматически.

    name = "unknown_plugin"
    description = ""
    keywords = []
    gui_enabled = False
    gui_button_text = ""
    dangerous = False

    @abstractmethod
    def execute(self, user_text: str, agent) -> str:
        # Выполняет плагин и возвращает строку-результат.
        # :param user_text: Полный текст запроса пользователя
        # :param agent: Экземпляр Agent (доступ к registry, workspace, output_dir, _read_safe)
        # :return: Строка с результатом
        raise NotImplementedError