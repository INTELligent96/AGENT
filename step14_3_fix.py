import os
import re


NL = "\n"


NEW_FUNC = NL.join([
    "    def ask_question(self, question):",
    "        return self.rag.ask(question, history=self.chat_history, last_folder=self.last_folder)",
])


def replace_function(content, func_name, new_body):
    # Ищем "    def <func_name>" и заменяем всё до следующего "    def " на том же уровне
    pattern = re.compile(r"(    def " + re.escape(func_name) + r"\([^)]*\):.*?)(?=\n    def |\Z)", re.DOTALL)
    m = pattern.search(content)
    if not m:
        return content, False
    return content[:m.start()] + new_body + "\n" + content[m.end():], True


def main():
    path = "core/agent.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Заменяем ask_question
    content, ok = replace_function(content, "ask_question", NEW_FUNC)
    print(("[OK] " if ok else "[WARN] ") + "agent: ask_question заменена")

    # 2. На всякий случай проверяем, что last_folder есть в __init__
    if "self.last_folder" not in content:
        content = content.replace(
            "self.pending_tool = None",
            "self.pending_tool = None\n        self.last_folder = None",
            1,
        )
        print("[OK] agent: добавлен self.last_folder в __init__")
    else:
        print("[SKIP] self.last_folder уже есть")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print("")
    print("Готово! Запускай: python main.py")


if __name__ == "__main__":
    main()