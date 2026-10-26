import os

NL = "\n"

OLD_SIDEBAR = (
    '        self.sidebar = ctk.CTkScrollableFrame(self, width=250, corner_radius=0)' + NL +
    '        self.sidebar.grid(row=0, column=0, sticky="nsew")'
)

NEW_SIDEBAR = (
    '        self.sidebar = ctk.CTkScrollableFrame(self, width=250, corner_radius=0)' + NL +
    '        self.sidebar.grid(row=0, column=0, sticky="nsew")' + NL +
    NL +
    '        self.footer = ctk.CTkFrame(self, width=250, corner_radius=0)' + NL +
    '        self.footer.grid(row=1, column=0, sticky="ew")'
)

OLD_STOP = (
    '        self.btn_stop = ctk.CTkButton(self, text="ЭКСТРЕННЫЙ СТОП", fg_color="red", hover_color="darkred", command=self.stop_agent)' + NL +
    '        self.btn_stop.grid(row=0, column=0, sticky="sw", padx=20, pady=20)'
)

NEW_STOP = (
    '        self.btn_stop = ctk.CTkButton(self.footer, text="ЭКСТРЕННЫЙ СТОП", fg_color="red", hover_color="darkred", command=self.stop_agent)' + NL +
    '        self.btn_stop.pack(padx=15, pady=15, fill="x")'
)

OLD_CHAT = (
    '        self.chat_frame = ctk.CTkFrame(self)' + NL +
    '        self.chat_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)'
)

NEW_CHAT = (
    '        self.chat_frame = ctk.CTkFrame(self)' + NL +
    '        self.chat_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=10, pady=10)'
)


def patch(path, old, new):
    if not os.path.exists(path):
        print("[SKIP] Нет файла: " + path)
        return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        print("[WARN] Не найден фрагмент в " + path)
        return
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[OK] Патчен: " + path)


def main():
    path = "gui/app.py"
    patch(path, OLD_SIDEBAR, NEW_SIDEBAR)
    patch(path, OLD_STOP, NEW_STOP)
    patch(path, OLD_CHAT, NEW_CHAT)
    print("")
    print("Готово! Запускай: python main.py")
    print("Кнопка СТОП теперь в отдельном футере, не накладывается.")


if __name__ == "__main__":
    main()