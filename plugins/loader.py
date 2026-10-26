import importlib.util
import inspect
from pathlib import Path
from plugins.base import BasePlugin


def load_plugins(plugins_dir="plugins"):
    # Сканирует папку plugins/ и возвращает словарь {name: instance}.
    plugins = {}
    plugins_path = Path(plugins_dir)

    if not plugins_path.exists():
        print("[Плагины] Папка не найдена, пропуск.")
        return plugins

    skip_files = ["__init__.py", "base.py", "loader.py"]

    for file in sorted(plugins_path.glob("*.py")):
        if file.name in skip_files or file.name.startswith("_"):
            continue

        try:
            spec = importlib.util.spec_from_file_location(file.stem, file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            found = False
            for cls_name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    if obj.__module__ == module.__name__:
                        instance = obj()
                        if instance.name in plugins:
                            print("[Плагины] Дубликат: " + instance.name + " - пропуск.")
                            continue
                        plugins[instance.name] = instance
                        print("[Плагины] Загружен: " + instance.name + " (" + file.name + ")")
                        found = True

            if not found:
                print("[Плагины] В " + file.name + " не найдено классов-наследников BasePlugin.")

        except Exception as e:
            print("[Плагины] Ошибка в " + file.name + ": " + str(e))

    print("[Плагины] Всего загружено: " + str(len(plugins)))
    return plugins