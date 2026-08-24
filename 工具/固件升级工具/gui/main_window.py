"""
主界面窗口
提供固件升级/降级/循环测试的图形化操作界面
"""

import queue
import json
import logging
import subprocess
import threading
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional

# 配置文件路径（兼容源码运行和打包运行）
if getattr(sys, 'frozen', False):
    # 打包后运行：使用 exe 所在目录
    BASE_DIR = Path(sys.executable).parent
else:
    # 源码运行：使用项目根目录
    BASE_DIR = Path(__file__).parent.parent

SETTINGS_FILE = BASE_DIR / "settings.json"


# ── 日志 Handler：把日志消息投入队列，由主线程消费 ──────────────────────────
class _QueueHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self._q = log_queue

    def emit(self, record):
        self._q.put(self.format(record))


# ── 主窗口 ────────────────────────────────────────────────────────────────────
class MainWindow:
    """固件升级自动化测试主界面"""

    # 测试模式常量
    MODE_UPGRADE = "upgrade"
    MODE_DOWNGRADE = "downgrade"
    MODE_CYCLE = "cycle"
    MODE_STREAM_ONLY = "stream_only"

    # 循环方向常量
    CYCLE_START_UPGRADE = "upgrade_first"   # 先升级后降级
    CYCLE_START_DOWNGRADE = "downgrade_first"  # 先降级后升级

    PRESET_COUNTS = [1, 5, 10]

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("CrealityScan 固件升级自动化测试工具")
        self.root.resizable(True, True)

        # 通用padding
        self._pad = {"padx": 12, "pady": 6}

        # 状态变量
        self._mode = tk.StringVar(value=self.MODE_UPGRADE)
        self._upgrade_path = tk.StringVar()
        self._downgrade_path = tk.StringVar()
        self._cycle_count = tk.StringVar(value="1")
        self._cycle_start = tk.StringVar(value=self.CYCLE_START_UPGRADE)  # 循环方向
        self._log_path = tk.StringVar()  # CrealityScan 日志目录

        # 连接模式常量
        self.CONN_USB = "usb"
        self.CONN_WIFI = "wifi"
        self._connection_mode = tk.StringVar(value=self.CONN_USB)  # 默认USB模式

        # 开流验证开关
        self._with_stream = tk.BooleanVar(value=True)  # 默认含开流验证

        # 邮件配置变量
        self._sender_email = tk.StringVar()
        self._sender_password = tk.StringVar()
        self._smtp_server = tk.StringVar(value="smtp.qq.com")
        self._smtp_port = tk.StringVar(value="465")
        self._email_recipients = tk.StringVar()

        self._status_text = tk.StringVar(value="就绪")
        self._running = False
        self._stop_event = threading.Event()
        self._log_queue: queue.Queue = queue.Queue()
        self._test_thread: threading.Thread | None = None

        # 加载保存的设置
        self._load_settings()

        self._build_ui()
        self._refresh_controls()
        self.root.after(100, self._poll_log_queue)

    # ── 设置加载/保存 ─────────────────────────────────────────────────────────

    def _load_settings(self):
        """从 settings.json 加载用户设置"""
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                self._log_path.set(settings.get("log_dir", ""))
                # 加载连接模式
                conn_mode = settings.get("connection_mode", self.CONN_USB)
                self._connection_mode.set(conn_mode if conn_mode in (self.CONN_USB, self.CONN_WIFI) else self.CONN_USB)
                # 加载邮件配置
                self._sender_email.set(settings.get("sender_email", ""))
                self._sender_password.set(settings.get("sender_password", ""))
                self._smtp_server.set(settings.get("smtp_server", "smtp.qq.com"))
                self._smtp_port.set(settings.get("smtp_port", "465"))
                self._email_recipients.set(settings.get("email_recipients", ""))
        except Exception:
            pass

    def _save_settings(self):
        """保存用户设置到 settings.json"""
        try:
            settings = {
                "log_dir": self._log_path.get(),
                "connection_mode": self._connection_mode.get(),
                "sender_email": self._sender_email.get(),
                "sender_password": self._sender_password.get(),
                "smtp_server": self._smtp_server.get(),
                "smtp_port": self._smtp_port.get(),
                "email_recipients": self._email_recipients.get(),
            }
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存设置失败: {e}")

    # ── UI 构建 ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = self.root
        root.configure(bg="#f0f0f0")
        pad = self._pad

        # 标题
        title_frame = tk.Frame(root, bg="#1a73e8", height=48)
        title_frame.pack(fill=tk.X)
        tk.Label(
            title_frame,
            text="CrealityScan 固件升级自动化测试工具",
            bg="#1a73e8", fg="white",
            font=("Microsoft YaHei", 13, "bold"),
        ).pack(pady=10)

        # ── 测试模式 ──
        mode_frame = ttk.LabelFrame(root, text="测试模式", padding=8)
        mode_frame.pack(fill=tk.X, **pad)

        for text, val in [
            ("仅开流", self.MODE_STREAM_ONLY),
            ("仅升级", self.MODE_UPGRADE),
            ("仅降级", self.MODE_DOWNGRADE),
            ("升级 ↔ 降级循环", self.MODE_CYCLE),
        ]:
            ttk.Radiobutton(
                mode_frame, text=text, variable=self._mode,
                value=val, command=self._refresh_controls,
            ).pack(side=tk.LEFT, padx=16)

        # ── 固件文件 ──
        fw_frame = ttk.LabelFrame(root, text="固件文件", padding=8)
        fw_frame.pack(fill=tk.X, **pad)

        self._upgrade_entry, self._upgrade_btn = self._file_row(
            fw_frame, "升级固件:", self._upgrade_path, self._pick_upgrade
        )
        self._downgrade_entry, self._downgrade_btn = self._file_row(
            fw_frame, "降级固件:", self._downgrade_path, self._pick_downgrade
        )

        # ── 连接模式 ──
        conn_frame = ttk.LabelFrame(root, text="连接模式", padding=8)
        conn_frame.pack(fill=tk.X, **pad)

        tk.Radiobutton(
            conn_frame, text="USB", variable=self._connection_mode,
            value=self.CONN_USB, command=self._on_connection_mode_changed,
        ).pack(side=tk.LEFT, padx=12)
        tk.Radiobutton(
            conn_frame, text="WiFi", variable=self._connection_mode,
            value=self.CONN_WIFI, command=self._on_connection_mode_changed,
        ).pack(side=tk.LEFT, padx=12)

        tk.Label(
            conn_frame,
            text="（USB：不自动检测WiFi设备  |  WiFi：自动检测WiFi模组重连）",
            font=("Microsoft YaHei", 8),
            fg="#888888",
            bg="#f0f0f0",
        ).pack(side=tk.LEFT, padx=8)

        # ── 测试选项 ──
        opts_frame = ttk.LabelFrame(root, text="测试选项", padding=8)
        opts_frame.pack(fill=tk.X, **pad)

        self._with_stream_check = ttk.Checkbutton(
            opts_frame,
            text="包含开流验证",
            variable=self._with_stream,
            command=self._on_with_stream_changed,
        )
        self._with_stream_check.pack(side=tk.LEFT, padx=8)
        tk.Label(
            opts_frame,
            text="（勾选：开流+升级/降级  |  取消勾选：仅固件升级/降级）",
            font=("Microsoft YaHei", 8),
            fg="#888888",
            bg="#f0f0f0",
        ).pack(side=tk.LEFT, padx=4)

        # ── 日志配置 ──
        log_frame = ttk.LabelFrame(root, text="日志配置", padding=8)
        log_frame.pack(fill=tk.X, **pad)

        self._log_entry, self._log_btn = self._dir_row(
            log_frame, "日志目录:", self._log_path, self._pick_log_dir
        )
        tk.Label(
            log_frame,
            text="示例: C:\\Users\\用户名\\AppData\\Local\\Creality\\CrealityScan\\Logs",
            font=("Microsoft YaHei", 8),
            fg="#888888",
            bg="#f0f0f0",
        ).pack(anchor="w", padx=90)

        # ── 邮件配置（可折叠，默认隐藏） ──
        self._email_expanded = tk.BooleanVar(value=False)
        email_header_frame = tk.Frame(root, bg="#f0f0f0")
        email_header_frame.pack(fill=tk.X, **pad)

        self._email_toggle_btn = ttk.Button(
            email_header_frame, text="▼ 邮件配置（可选）",
            width=20, command=self._toggle_email_section
        )
        self._email_toggle_btn.pack(side=tk.LEFT, padx=4)

        self._email_container = ttk.LabelFrame(root, text="邮件配置", padding=8)
        # 默认隐藏，不pack

        # 邮件配置内容
        email_frame = self._email_container

        # 发件人
        email_sender_row = tk.Frame(email_frame, bg="#f0f0f0")
        email_sender_row.pack(fill=tk.X, pady=2)
        tk.Label(email_sender_row, text="发件人:", width=8, anchor="w", bg="#f0f0f0").pack(side=tk.LEFT)
        self._sender_email_entry = ttk.Entry(email_sender_row, textvariable=self._sender_email, width=28)
        self._sender_email_entry.pack(side=tk.LEFT, padx=4)

        # 密码
        email_pwd_row = tk.Frame(email_frame, bg="#f0f0f0")
        email_pwd_row.pack(fill=tk.X, pady=2)
        tk.Label(email_pwd_row, text="密码:", width=8, anchor="w", bg="#f0f0f0").pack(side=tk.LEFT)
        self._sender_password_entry = ttk.Entry(email_pwd_row, textvariable=self._sender_password, width=28, show="*")
        self._sender_password_entry.pack(side=tk.LEFT, padx=4)
        tk.Label(email_pwd_row, text="(SMTP授权码)", font=("Microsoft YaHei", 8), fg="#888888", bg="#f0f0f0").pack(side=tk.LEFT)

        # SMTP配置
        smtp_row = tk.Frame(email_frame, bg="#f0f0f0")
        smtp_row.pack(fill=tk.X, pady=2)
        tk.Label(smtp_row, text="SMTP:", width=8, anchor="w", bg="#f0f0f0").pack(side=tk.LEFT)
        self._smtp_server_entry = ttk.Entry(smtp_row, textvariable=self._smtp_server, width=20)
        self._smtp_server_entry.pack(side=tk.LEFT, padx=4)
        tk.Label(smtp_row, text="端口:", bg="#f0f0f0").pack(side=tk.LEFT, padx=(8, 2))
        self._smtp_port_entry = ttk.Entry(smtp_row, textvariable=self._smtp_port, width=6)
        self._smtp_port_entry.pack(side=tk.LEFT)

        # 收件人
        email_recipient_row = tk.Frame(email_frame, bg="#f0f0f0")
        email_recipient_row.pack(fill=tk.X, pady=2)
        tk.Label(email_recipient_row, text="收件人:", width=8, anchor="w", bg="#f0f0f0").pack(side=tk.LEFT)
        self._email_recipients_entry = ttk.Entry(email_recipient_row, textvariable=self._email_recipients, width=28)
        self._email_recipients_entry.pack(side=tk.LEFT, padx=4)
        tk.Label(email_recipient_row, text="多个用逗号分隔", font=("Microsoft YaHei", 8), fg="#888888", bg="#f0f0f0").pack(side=tk.LEFT)

        # 发送测试邮件按钮
        self._test_email_btn = ttk.Button(
            email_frame, text="发送测试邮件", command=self._send_test_email
        )
        self._test_email_btn.pack(pady=4)

        self._email_header = email_header_frame

        # ── 循环次数 ──
        cycle_frame = ttk.LabelFrame(root, text="循环次数", padding=8)
        cycle_frame.pack(fill=tk.X, **pad)

        self._cycle_frame = cycle_frame
        self._preset_btns = []
        for n in self.PRESET_COUNTS:
            btn = ttk.Button(
                cycle_frame, text=f"{n} 次", width=6,
                command=lambda v=n: self._set_count(v),
            )
            btn.pack(side=tk.LEFT, padx=4)
            self._preset_btns.append(btn)

        tk.Label(cycle_frame, text="自定义:", bg="#f0f0f0").pack(side=tk.LEFT, padx=(12, 4))
        self._custom_entry = ttk.Entry(cycle_frame, textvariable=self._cycle_count, width=6)
        self._custom_entry.pack(side=tk.LEFT)
        tk.Label(cycle_frame, text="次", bg="#f0f0f0").pack(side=tk.LEFT, padx=2)

        # 循环方向选择（下拉框）
        tk.Label(cycle_frame, text="方向:", bg="#f0f0f0").pack(side=tk.LEFT, padx=(20, 4))
        self._cycle_direction_combo = ttk.Combobox(
            cycle_frame,
            values=("先升级后降级", "先降级后升级"),
            width=14,
            state="readonly",
        )
        self._cycle_direction_combo.pack(side=tk.LEFT)
        self._cycle_direction_combo.set("先升级后降级")
        # 绑定选择事件
        self._cycle_direction_combo.bind("<<ComboboxSelected>>", self._on_cycle_direction_changed)

        # ── 操作按钮 ──
        btn_frame = tk.Frame(root, bg="#f0f0f0")
        btn_frame.pack(pady=8)

        self._start_btn = ttk.Button(
            btn_frame, text="▶  开始测试", width=16,
            command=self._on_start, style="Accent.TButton",
        )
        self._start_btn.pack(side=tk.LEFT, padx=8)

        self._stop_btn = ttk.Button(
            btn_frame, text="■  停止", width=10,
            command=self._on_stop, state=tk.DISABLED,
        )
        self._stop_btn.pack(side=tk.LEFT, padx=8)

        # ── 日志区 ──
        log_frame = ttk.LabelFrame(root, text="运行日志", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        self._log_text = tk.Text(
            log_frame, height=16, width=72,
            state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4",
            font=("Consolas", 9), wrap=tk.WORD,
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(fill=tk.BOTH, expand=True)

        # 日志颜色 tag
        self._log_text.tag_config("PASS",    foreground="#4ec9b0")
        self._log_text.tag_config("ERROR",   foreground="#f44747")
        self._log_text.tag_config("WARNING", foreground="#dcdcaa")
        self._log_text.tag_config("STEP",    foreground="#569cd6")
        self._log_text.tag_config("INFO",    foreground="#d4d4d4")

        # ── 状态栏 ──
        status_frame = tk.Frame(root, bg="#e0e0e0", height=28)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Label(
            status_frame, text="状态:", bg="#e0e0e0",
            font=("Microsoft YaHei", 9),
        ).pack(side=tk.LEFT, padx=8)

        self._status_label = tk.Label(
            status_frame, textvariable=self._status_text,
            bg="#e0e0e0", font=("Microsoft YaHei", 9, "bold"),
        )
        self._status_label.pack(side=tk.LEFT)

        self._progress = ttk.Progressbar(
            status_frame, length=180, mode="determinate",
        )
        self._progress.pack(side=tk.RIGHT, padx=12, pady=4)

    def _file_row(self, parent, label, var, cmd):
        """生成一行固件选择控件，返回 (entry, button)"""
        row = tk.Frame(parent, bg="#f0f0f0")
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=label, width=8, anchor="w", bg="#f0f0f0").pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=var, width=46, state="readonly")
        entry.pack(side=tk.LEFT, padx=4)
        btn = ttk.Button(row, text="选择", width=6, command=cmd)
        btn.pack(side=tk.LEFT)
        return entry, btn

    def _dir_row(self, parent, label, var, cmd):
        """生成一行目录选择控件，返回 (entry, button)"""
        row = tk.Frame(parent, bg="#f0f0f0")
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=label, width=8, anchor="w", bg="#f0f0f0").pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=var, width=46, state="readonly")
        entry.pack(side=tk.LEFT, padx=4)
        btn = ttk.Button(row, text="选择", width=6, command=cmd)
        btn.pack(side=tk.LEFT)
        return entry, btn

    # ── 控件联动 ─────────────────────────────────────────────────────────────

    def _on_cycle_direction_changed(self, event=None):
        """处理循环方向下拉框的选择变化"""
        direction_text = self._cycle_direction_combo.get()
        if direction_text == "先升级后降级":
            self._cycle_start.set(self.CYCLE_START_UPGRADE)
        else:
            self._cycle_start.set(self.CYCLE_START_DOWNGRADE)

    def _on_connection_mode_changed(self, event=None):
        """处理连接模式切换，保存设置"""
        self._save_settings()
        mode = self._connection_mode.get()
        mode_desc = "USB模式" if mode == self.CONN_USB else "WiFi模式"
        self._log_queue.put(f"[设置] 已切换到 {mode_desc}")

    def _on_with_stream_changed(self):
        """处理开流验证开关切换"""
        desc = "含开流" if self._with_stream.get() else "纯固件"
        self._log_queue.put(f"[设置] 测试选项: {desc}")

    def _toggle_email_section(self):
        """展开/折叠邮件配置区域"""
        if self._email_expanded.get():
            self._email_container.pack_forget()
            self._email_toggle_btn.config(text="▼ 邮件配置（可选）")
            self._email_expanded.set(False)
        else:
            self._email_container.pack(fill=tk.X, **self._pad)
            self._email_toggle_btn.config(text="▲ 邮件配置（可选）")
            self._email_expanded.set(True)

    def _refresh_controls(self):
        mode = self._mode.get()
        upgrade_state   = tk.NORMAL if mode in (self.MODE_UPGRADE, self.MODE_CYCLE) else tk.DISABLED
        downgrade_state = tk.NORMAL if mode in (self.MODE_DOWNGRADE, self.MODE_CYCLE) else tk.DISABLED
        cycle_state     = tk.NORMAL if mode == self.MODE_CYCLE else tk.DISABLED

        self._upgrade_btn.config(state=upgrade_state)
        self._downgrade_btn.config(state=downgrade_state)
        for btn in self._preset_btns:
            btn.config(state=cycle_state)
        self._custom_entry.config(state=cycle_state)
        # 循环方向下拉框只在循环模式下启用
        self._cycle_direction_combo.config(state=cycle_state)

        # 仅开流模式下禁用开流验证开关
        stream_check_state = tk.DISABLED if mode == self.MODE_STREAM_ONLY else tk.NORMAL
        self._with_stream_check.config(state=stream_check_state)

        # 清空不需要的路径
        if mode == self.MODE_UPGRADE:
            self._downgrade_path.set("")
        elif mode == self.MODE_DOWNGRADE:
            self._upgrade_path.set("")
        elif mode == self.MODE_STREAM_ONLY:
            self._upgrade_path.set("")
            self._downgrade_path.set("")

        self._refresh_start_btn()

    def _refresh_start_btn(self):
        mode = self._mode.get()
        ok = True
        if mode in (self.MODE_UPGRADE, self.MODE_CYCLE) and not self._upgrade_path.get():
            ok = False
        if mode in (self.MODE_DOWNGRADE, self.MODE_CYCLE) and not self._downgrade_path.get():
            ok = False
        if mode == self.MODE_CYCLE:
            try:
                n = int(self._cycle_count.get())
                if n < 1:
                    ok = False
            except ValueError:
                ok = False
        # 仅开流模式不需要固件路径，只要有日志目录即可
        self._start_btn.config(state=tk.NORMAL if ok and not self._running else tk.DISABLED)

    # ── 文件选择 ──────────────────────────────────────────────────────────────

    def _pick_upgrade(self):
        path = filedialog.askopenfilename(
            title="选择升级固件", filetypes=[("固件文件", "*.zip"), ("所有文件", "*.*")]
        )
        if path:
            self._upgrade_path.set(path)
            self._refresh_start_btn()

    def _pick_downgrade(self):
        path = filedialog.askopenfilename(
            title="选择降级固件", filetypes=[("固件文件", "*.zip"), ("所有文件", "*.*")]
        )
        if path:
            self._downgrade_path.set(path)
            self._refresh_start_btn()

    def _pick_log_dir(self):
        path = filedialog.askdirectory(
            title="选择 CrealityScan 日志目录",
            initialdir=self._log_path.get() or None,
        )
        if path:
            self._log_path.set(path)
            self._save_settings()

    def _set_count(self, n: int):
        self._cycle_count.set(str(n))
        self._refresh_start_btn()

    # ── 邮件发送 ───────────────────────────────────────────────────────────────

    def _send_test_email(self):
        """发送测试邮件"""
        sender_email = self._sender_email.get().strip()
        sender_password = self._sender_password.get().strip()
        smtp_server = self._smtp_server.get().strip()
        smtp_port = self._smtp_port.get().strip()
        recipients = self._email_recipients.get().strip()

        # 验证输入
        if not sender_email:
            messagebox.showwarning("提示", "请输入发件人邮箱")
            return
        if '@' not in sender_email or '.' not in sender_email.split('@')[-1]:
            messagebox.showwarning("提示", "发件人邮箱格式不正确，请输入完整的邮箱地址（如 xxx@qq.com）")
            return
        if not sender_password:
            messagebox.showwarning("提示", "请输入发件人密码（SMTP授权码）")
            return
        if not recipients:
            messagebox.showwarning("提示", "请输入收件人邮箱")
            return

        # 解析收件人
        recipient_list = [r.strip() for r in recipients.split(',') if r.strip()]
        if not recipient_list:
            messagebox.showwarning("提示", "收件人格式不正确")
            return

        # 禁用按钮，防止重复点击
        self._test_email_btn.config(state=tk.DISABLED)
        self._log_queue.put("[邮件] 正在发送测试邮件...")

        # 在后台线程发送邮件
        def _send():
            try:
                from utils.email_sender import EmailSender
                sender = EmailSender(
                    smtp_server=smtp_server,
                    smtp_port=int(smtp_port),
                    sender_email=sender_email,
                    sender_password=sender_password,
                    use_ssl=(smtp_port == "465")
                )
                success = sender.test_connection(recipient_list)
                if success:
                    self.root.after(0, lambda: self._log_queue.put("[邮件] 测试邮件发送成功 ✓"))
                    self.root.after(0, lambda: messagebox.showinfo("成功", "测试邮件发送成功！"))
                    # 保存邮件配置
                    self.root.after(0, self._save_settings)
                else:
                    self.root.after(0, lambda: self._log_queue.put("[邮件] 测试邮件发送失败 ✗"))
                    self.root.after(0, lambda: messagebox.showerror("失败", "测试邮件发送失败，请检查配置"))
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self._log_queue.put(f"[邮件] 发送失败: {error_msg}"))
                self.root.after(0, lambda: messagebox.showerror("失败", f"发送失败: {error_msg}"))
            finally:
                self.root.after(0, lambda: self._test_email_btn.config(state=tk.NORMAL))

        threading.Thread(target=_send, daemon=True).start()

    def _send_report_email(self, report_path: str, success: bool):
        """发送测试报告邮件"""
        import os

        # 调试日志：打印所有配置
        self._log_queue.put("=" * 40)
        self._log_queue.put(f"[邮件] 开始发送报告邮件...")
        self._log_queue.put(f"[邮件] report_path: {report_path}")
        self._log_queue.put(f"[邮件] report_path类型: {type(report_path)}")
        self._log_queue.put(f"[邮件] success: {success}")

        sender_email = self._sender_email.get().strip()
        sender_password = self._sender_password.get().strip()
        smtp_server = self._smtp_server.get().strip()
        smtp_port = self._smtp_port.get().strip()
        recipients = self._email_recipients.get().strip()

        # 验证发件人邮箱格式
        if '@' not in sender_email or '.' not in sender_email.split('@')[-1]:
            self._log_queue.put(f"[邮件] 发件人邮箱格式不正确: {sender_email}")
            return

        self._log_queue.put(f"[邮件] 发件人: {sender_email}")
        self._log_queue.put(f"[邮件] 收件人: {recipients}")
        self._log_queue.put(f"[邮件] SMTP: {smtp_server}:{smtp_port}")

        # 检查报告文件是否存在
        if report_path:
            self._log_queue.put(f"[邮件] 报告文件存在: {os.path.exists(report_path)}")
        else:
            self._log_queue.put("[邮件] 报告路径为空")

        # 如果没有配置收件人，不发送邮件
        if not recipients:
            self._log_queue.put("[邮件] 收件人为空，跳过发送")
            return

        recipient_list = [r.strip() for r in recipients.split(',') if r.strip()]
        if not recipient_list:
            self._log_queue.put("[邮件] 收件人列表为空，跳过发送")
            return

        self._log_queue.put(f"[邮件] 开始发送邮件到: {recipient_list}")

        def _send():
            try:
                from utils.email_sender import EmailSender
                sender = EmailSender(
                    smtp_server=smtp_server,
                    smtp_port=int(smtp_port),
                    sender_email=sender_email,
                    sender_password=sender_password,
                    use_ssl=(smtp_port == "465")
                )
                subject = "CrealityScan 测试报告 - 测试通过" if success else "CrealityScan 测试报告 - 测试失败"
                body = f"""<html>
<body>
    <h2>CrealityScan 固件升级测试报告</h2>
    <p>您好，</p>
    <p>CrealityScan 固件升级测试已完成。</p>
    <p><b>测试结果: {'通过' if success else '失败'}</b></p>
    <p>请查看下方完整测试报告（包含截图和性能图表）。</p>
    <hr>
    <p style="color: #888; font-size: 12px;">此邮件由自动化测试工具发送</p>
</body>
</html>"""
                sender.send_report(recipient_list, report_path, subject, body)
                self.root.after(0, lambda: self._log_queue.put("[邮件] 测试报告已发送到指定邮箱 ✓"))
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                self.root.after(0, lambda: self._log_queue.put(f"[邮件] 发送失败: {e}"))
                self.root.after(0, lambda: self._log_queue.put(f"[邮件] 详细错误: {error_detail}"))

        threading.Thread(target=_send, daemon=True).start()

    # ── 开始 / 停止 ───────────────────────────────────────────────────────────

    def _on_start(self):
        self._running = True
        self._stop_event.clear()
        self._start_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._progress["value"] = 0
        self._set_status("运行中...", "#1a73e8")
        self._clear_log()

        mode          = self._mode.get()
        upgrade_path  = self._upgrade_path.get()
        downgrade_path = self._downgrade_path.get()
        cycle_count   = int(self._cycle_count.get()) if mode == self.MODE_CYCLE else 1
        cycle_start   = self._cycle_start.get() if mode == self.MODE_CYCLE else None
        log_dir       = self._log_path.get() or None
        conn_mode     = self._connection_mode.get()
        with_stream   = self._with_stream.get()

        stream_desc = "含开流" if with_stream else "纯固件"
        self._log_queue.put(f"[设置] 连接模式: {'WiFi' if conn_mode == self.CONN_WIFI else 'USB'}")
        self._log_queue.put(f"[设置] 测试选项: {stream_desc}")

        self._test_thread = threading.Thread(
            target=self._run_test,
            args=(mode, upgrade_path, downgrade_path, cycle_count, cycle_start, log_dir, conn_mode, with_stream),
            daemon=True,
        )
        self._test_thread.start()

    def _on_stop(self):
        if self._running:
            self._stop_event.set()
            self._set_status("正在停止...", "#e65100")

    def _run_test(self, mode, upgrade_path, downgrade_path, cycle_count, cycle_start, log_dir, conn_mode, with_stream):
        """子线程：执行测试，完成后通知主线程"""
        try:
            from testcases.test_firmware_cycle import TestFirmwareCycle
            test = TestFirmwareCycle(
                gui_log_queue=self._log_queue,
                stop_event=self._stop_event,
                on_progress=self._on_progress_callback,
                log_dir=log_dir,  # 传递日志目录
                connection_mode=conn_mode,
                with_stream=with_stream,
            )
            success, report_path = test.run(
                mode=mode,
                upgrade_path=upgrade_path or None,
                downgrade_path=downgrade_path or None,
                cycle_count=cycle_count,
                cycle_start=cycle_start,
                with_stream=with_stream,
            )
        except Exception as e:
            success, report_path = False, None
            self._log_queue.put(f"[ERROR] 测试异常: {e}")

        # 回到主线程处理结果
        self.root.after(0, self._on_test_done, success, report_path)

    def _on_progress_callback(self, current: int, total: int):
        """子线程调用，线程安全地更新进度"""
        self.root.after(0, self._update_progress, current, total)

    def _update_progress(self, current: int, total: int):
        pct = int(current / total * 100) if total else 0
        self._progress["value"] = pct
        self._set_status(f"运行中  第 {current}/{total} 轮  {pct}%", "#1a73e8")

    def _on_test_done(self, success: bool, report_path: Optional[str]):
        self._running = False
        self._stop_btn.config(state=tk.DISABLED)
        self._refresh_start_btn()
        self._progress["value"] = 100 if success else self._progress["value"]

        # 发送测试报告邮件
        if report_path and self._email_recipients.get().strip():
            self._send_report_email(report_path, success)

        if success:
            self._set_status("测试通过 ✓", "#2e7d32")
            msg = "测试全部通过！"
            if report_path:
                msg += f"\n\n报告路径:\n{report_path}"
                if messagebox.askyesno("测试完成", msg + "\n\n是否立即打开报告？"):
                    self._open_report(report_path)
            else:
                messagebox.showinfo("测试完成", msg)
        else:
            self._set_status("测试失败 ✗", "#c62828")
            messagebox.showerror("测试失败", "测试未通过，请查看运行日志了解详情。")

    @staticmethod
    def _open_report(report_path):
        """跨平台打开 HTML 报告"""
        if sys.platform == "darwin":
            subprocess.run(["open", report_path])
        elif sys.platform == "win32":
            import os
            os.startfile(report_path)
        else:
            subprocess.run(["xdg-open", report_path])

    # ── 日志输出 ──────────────────────────────────────────────────────────────

    def _poll_log_queue(self):
        """主线程轮询日志队列，追加到文本框"""
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log_queue)

    def _append_log(self, msg: str):
        tag = "INFO"
        if "✓" in msg or "[PASS]" in msg or "成功" in msg:
            tag = "PASS"
        elif "[ERROR]" in msg or "✗" in msg or "失败" in msg:
            tag = "ERROR"
        elif "[WARNING]" in msg or "警告" in msg:
            tag = "WARNING"
        elif "【步骤】" in msg:
            tag = "STEP"

        self._log_text.config(state=tk.NORMAL)
        self._log_text.insert(tk.END, msg + "\n", tag)
        self._log_text.see(tk.END)
        self._log_text.config(state=tk.DISABLED)

    def _clear_log(self):
        self._log_text.config(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.config(state=tk.DISABLED)

    # ── 状态栏 ────────────────────────────────────────────────────────────────

    def _set_status(self, text: str, color: str = "#333333"):
        self._status_text.set(text)
        self._status_label.config(fg=color)

    # ── 启动 ──────────────────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()
