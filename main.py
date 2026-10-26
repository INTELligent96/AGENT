import customtkinter as ctk
import yaml
from tkinter import messagebox


def startup_check():
    # Проверяет зависимости ДО запуска GUI, чтобы избежать непонятных ошибок.
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        return
    startup = cfg.get("startup", {})
    if not startup.get("check_dependencies", True):
        return

    from tools.requirements_checker import check_and_report, install_packages
    auto = startup.get("auto_install", False)
    missing, ok = check_and_report(auto_install=auto)
    if missing and not ok:
        msg = "Не хватает библиотек:\n\n" + "\n".join(missing)
        msg += "\n\nУстановить их сейчас? (потребуется интернет)"
        answer = messagebox.askyesno("Отсутствуют зависимости", msg)
        if answer:
            install_packages(missing)


if __name__ == "__main__":
    startup_check()
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    from gui.app import AgentApp
    app = AgentApp()
    app.mainloop()
