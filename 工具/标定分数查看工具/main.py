import tkinter as tk
from datetime import datetime
from tkinter import ttk

from parser import get_latest_log_file, parse_log_file


class CalibrationScoreApp(tk.Tk):
    WINDOW_WIDTH = 420
    WINDOW_HEIGHT = 360

    COLORS = {
        "bg": "#f3f0e8",
        "panel": "#fffdf7",
        "field": "#f0ede5",
        "line": "#d0cabd",
        "ink": "#102022",
        "muted": "#6c716d",
        "accent": "#087c73",
        "accent_dark": "#055c55",
        "danger": "#b24a35",
        "status": "#dceee9",
    }

    def __init__(self):
        super().__init__()

        self.title("标定分数查看工具")
        self.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")
        self.resizable(False, False)
        self.configure(bg=self.COLORS["bg"])

        self.labels: dict[str, tk.Text] = {}
        self.status_var = tk.StringVar(value="等待读取")
        self.time_var = tk.StringVar(value="--:--:--")
        self.score_text: tk.Text | None = None

        self._configure_style()
        self._center_window()
        self._create_widgets()
        self.refresh_data()

    def _configure_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background=self.COLORS["bg"])
        style.configure(
            "Title.TLabel",
            background=self.COLORS["bg"],
            foreground=self.COLORS["ink"],
            font=("Microsoft YaHei UI", 14, "bold"),
        )
        style.configure(
            "Meta.TLabel",
            background=self.COLORS["bg"],
            foreground=self.COLORS["muted"],
            font=("Microsoft YaHei UI", 8),
        )
        style.configure(
            "Status.TLabel",
            background=self.COLORS["status"],
            foreground=self.COLORS["accent_dark"],
            font=("Microsoft YaHei UI", 8, "bold"),
            padding=(8, 4),
        )
        style.configure(
            "Refresh.TButton",
            background=self.COLORS["accent"],
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=0,
            focuscolor=self.COLORS["accent"],
            font=("Microsoft YaHei UI", 10, "bold"),
            padding=(14, 7),
        )
        style.map(
            "Refresh.TButton",
            background=[
                ("active", self.COLORS["accent_dark"]),
                ("pressed", self.COLORS["accent_dark"]),
                ("disabled", self.COLORS["line"]),
            ],
            foreground=[("disabled", self.COLORS["muted"])],
        )

    def _center_window(self):
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - self.WINDOW_WIDTH) // 2
        y = (screen_height - self.WINDOW_HEIGHT) // 2
        self.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}+{x}+{y}")

    def _create_widgets(self):
        root = ttk.Frame(self, style="App.TFrame", padding=(14, 10, 14, 10))
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="App.TFrame")
        header.pack(fill="x")

        title_area = ttk.Frame(header, style="App.TFrame")
        title_area.pack(side="left", fill="x", expand=True)
        ttk.Label(title_area, text="标定分数查看工具", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_area, text="CrealityScan 最新日志", style="Meta.TLabel").pack(anchor="w", pady=(1, 0))

        action_area = ttk.Frame(header, style="App.TFrame")
        action_area.pack(side="right", anchor="n")
        ttk.Label(action_area, textvariable=self.status_var, style="Status.TLabel").pack(anchor="e")
        self.refresh_btn = ttk.Button(
            action_area,
            text="刷新",
            style="Refresh.TButton",
            command=self.refresh_data,
        )
        self.refresh_btn.pack(anchor="e", pady=(5, 0))

        score_panel = tk.Frame(
            root,
            bg=self.COLORS["panel"],
            highlightbackground=self.COLORS["line"],
            highlightthickness=1,
            bd=0,
            height=78,
        )
        score_panel.pack(fill="x", pady=(8, 6))
        score_panel.pack_propagate(False)

        tk.Label(
            score_panel,
            text="标定分数",
            bg=self.COLORS["panel"],
            fg=self.COLORS["muted"],
            font=("Microsoft YaHei UI", 8, "bold"),
        ).pack(anchor="w", padx=12, pady=(6, 0))

        score_row = tk.Frame(score_panel, bg=self.COLORS["panel"])
        score_row.pack(anchor="w", padx=12, pady=(0, 6), fill="x", expand=True)

        self.score_text = tk.Text(
            score_row,
            height=1,
            relief="flat",
            bd=0,
            bg=self.COLORS["panel"],
            fg=self.COLORS["accent"],
            insertbackground=self.COLORS["accent"],
            selectbackground="#b9d8d2",
            selectforeground=self.COLORS["ink"],
            font=("Cascadia Mono SemiBold", 30, "bold"),
            padx=0,
            pady=0,
        )
        self.score_text.pack(side="left", fill="x", expand=True)

        copy_btn = tk.Button(
            score_row,
            text="复制",
            bg=self.COLORS["accent"],
            fg="#ffffff",
            relief="flat",
            bd=0,
            font=("Microsoft YaHei UI", 8, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._copy_score,
        )
        copy_btn.pack(side="right", padx=(8, 0))

        info_panel = tk.Frame(
            root,
            bg=self.COLORS["panel"],
            highlightbackground=self.COLORS["line"],
            highlightthickness=1,
            bd=0,
        )
        info_panel.pack(fill="x")

        fields = [
            ("设备", "device_name"),
            ("SN", "sn_code"),
            ("标定板", "calibration_board"),
            ("固件", "firmware_version"),
            ("日志", "log_file"),
        ]
        for label, key in fields:
            self._create_field_row(info_panel, label, key)

        footer = ttk.Frame(root, style="App.TFrame")
        footer.pack(fill="x", pady=(4, 0))
        ttk.Label(footer, textvariable=self.time_var, style="Meta.TLabel").pack(side="left")

    def _create_field_row(self, parent: tk.Frame, label: str, key: str):
        row = tk.Frame(parent, bg=self.COLORS["panel"])
        row.pack(fill="x", padx=10, pady=(7 if not self.labels else 0, 5))

        tk.Label(
            row,
            text=label,
            bg=self.COLORS["panel"],
            fg=self.COLORS["muted"],
            width=6,
            anchor="w",
            font=("Microsoft YaHei UI", 8, "bold"),
        ).pack(side="left")

        text_widget = tk.Text(
            row,
            height=1,
            relief="flat",
            bd=0,
            bg=self.COLORS["field"],
            fg=self.COLORS["ink"],
            insertbackground=self.COLORS["accent"],
            selectbackground="#b9d8d2",
            selectforeground=self.COLORS["ink"],
            font=("Cascadia Mono", 8, "bold"),
            padx=7,
            pady=2,
            wrap="none",
        )
        text_widget.pack(side="left", fill="x", expand=True)
        self.labels[key] = text_widget

    def refresh_data(self):
        self.refresh_btn.state(["disabled"])
        self.status_var.set("读取中")
        self.update_idletasks()

        log_file = get_latest_log_file()
        if log_file is None:
            self._show_error("未找到日志文件")
            self.refresh_btn.state(["!disabled"])
            return

        data = parse_log_file(log_file)
        self.update_display(data)

        self.time_var.set(f"上次刷新 {datetime.now().strftime('%H:%M:%S')}")
        self.status_var.set("已读取")
        self.refresh_btn.state(["!disabled"])

    def update_display(self, data: dict):
        for key, text_widget in self.labels.items():
            self._set_text(text_widget, data.get(key, "N/A"))

        score = data.get("calibration_score", "N/A")
        self._set_text(self.score_text, score if score != "N/A" else "--")
        self._update_score_color(score)

    def _copy_score(self):
        if self.score_text is None:
            return
        score = self.score_text.get("1.0", "end-1c").strip()
        if score and score != "--":
            self.clipboard_clear()
            self.clipboard_append(score)
            self.status_var.set("已复制")
            self.after(1500, lambda: self.status_var.set("已读取"))

    def _update_score_color(self, score: str):
        if self.score_text is None:
            return
        color = self.COLORS["accent"] if score != "N/A" else self.COLORS["danger"]
        self.score_text.configure(fg=color)

    def _show_error(self, message: str):
        for text_widget in self.labels.values():
            self._set_text(text_widget, "N/A")
        self._set_text(self.score_text, "--")
        self.status_var.set("未读取")
        self.time_var.set(f"上次尝试 {datetime.now().strftime('%H:%M:%S')} - {message}")
        self._update_score_color("N/A")

    @staticmethod
    def _set_text(widget: tk.Text, value: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)


if __name__ == "__main__":
    app = CalibrationScoreApp()
    app.mainloop()
