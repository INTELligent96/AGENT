import customtkinter as ctk

class ToolTip:
    def __init__(self, widget, text, delay=500, auto_hide=4000):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.show_job = None
        self.hide_job = None
        self.delay = delay
        self.auto_hide = auto_hide

        self.widget.bind("<Enter>", self.schedule_show)
        self.widget.bind("<Leave>", self.hide_tooltip)
        self.widget.bind("<Button-1>", self.hide_tooltip)
        self.widget.bind("<FocusOut>", self.hide_tooltip)

    def schedule_show(self, event=None):
        self.cancel_jobs()
        self.show_job = self.widget.after(self.delay, self.show_tooltip)

    def show_tooltip(self):
        if self.tooltip_window or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except Exception:
            return

        self.tooltip_window = ctk.CTkToplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        self.tooltip_window.attributes("-topmost", True)

        label = ctk.CTkLabel(
            self.tooltip_window, text=self.text, fg_color="#2b2b2b", text_color="white", corner_radius=6, font=("Arial", 12)
        )
        label.pack(ipadx=6, ipady=3)
        self.hide_job = self.widget.after(self.auto_hide, self.hide_tooltip)

    def hide_tooltip(self, event=None):
        self.cancel_jobs()
        if self.tooltip_window:
            try: self.tooltip_window.destroy()
            except Exception: pass
            self.tooltip_window = None

    def cancel_jobs(self):
        if self.show_job:
            try: self.widget.after_cancel(self.show_job)
            except Exception: pass
            self.show_job = None
        if self.hide_job:
            try: self.widget.after_cancel(self.hide_job)
            except Exception: pass
            self.hide_job = None
