from __future__ import annotations

import json
import mimetypes
import os
import re
import smtplib
import socket
import ssl
import threading
from dataclasses import dataclass
from datetime import datetime
from email.header import Header
from email.message import EmailMessage
from email.utils import formataddr, formatdate
from pathlib import Path
from typing import Iterable, Optional, Sequence

from PyQt5 import QtCore  # type: ignore
from jens_runtime import iter_existing_resource_roots


_SETTINGS_REL_PATH = Path("config") / "notification_settings.json"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SMTP_HOST_ENV = "JENS_SMTP_HOST"
_SMTP_PORT_ENV = "JENS_SMTP_PORT"
_SMTP_USER_ENV = "JENS_SMTP_USER"
_SMTP_PASSWORD_ENV = "JENS_SMTP_PASSWORD"
_SMTP_USE_SSL_ENV = "JENS_SMTP_USE_SSL"
_SMTP_USE_STARTTLS_ENV = "JENS_SMTP_USE_STARTTLS"
_SMTP_TIMEOUT_ENV = "JENS_SMTP_TIMEOUT_SEC"
_DOTENV_NAME = ".env"
_SMTP_FROM_DISPLAY_NAME = "jens—pc端软件ui自动化测试平台"


@dataclass
class NotificationSettings:
    recipient_email: str = ""
    label: str = ""


@dataclass
class NotificationAvailability:
    enabled: bool
    reason: str = ""


@dataclass
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    use_ssl: bool
    use_starttls: bool
    timeout_sec: float


@dataclass
class TaskRunSummary:
    task_json_name: str
    status: str
    started_at: str = ""
    finished_at: str = ""
    failed_step_name: str = ""
    screenshot_path: str = ""
    report_path: str = ""
    run_dir: str = ""


def notification_settings_path(project_root: Path) -> Path:
    return project_root / _SETTINGS_REL_PATH


def load_notification_settings(project_root: Path) -> NotificationSettings:
    fp = notification_settings_path(project_root)
    try:
        raw = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return NotificationSettings()
    if not isinstance(raw, dict):
        return NotificationSettings()
    return NotificationSettings(
        recipient_email=str(raw.get("recipient_email") or "").strip(),
        label=str(raw.get("label") or "").strip(),
    )


def save_notification_settings(project_root: Path, settings: NotificationSettings) -> Path:
    fp = notification_settings_path(project_root)
    fp.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "recipient_email": settings.recipient_email.strip(),
        "label": settings.label.strip(),
    }
    fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return fp


def is_valid_email(text: str) -> bool:
    return bool(_EMAIL_RE.match((text or "").strip()))


def required_smtp_env_names() -> list[str]:
    return [_SMTP_HOST_ENV, _SMTP_PORT_ENV, _SMTP_USER_ENV, _SMTP_PASSWORD_ENV]


def load_project_dotenv(project_root: Path) -> None:
    candidate_roots: list[Path] = [Path(project_root)]
    for root in iter_existing_resource_roots():
        if root not in candidate_roots:
            candidate_roots.append(root)

    for root in candidate_roots:
        env_path = root / _DOTENV_NAME
        if not env_path.exists() or not env_path.is_file():
            continue

        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(key, value)
        return


def load_smtp_config_from_env() -> tuple[Optional[SmtpConfig], str]:
    values = {name: str(os.environ.get(name) or "").strip() for name in required_smtp_env_names()}
    missing = [name for name, value in values.items() if not value]
    if missing:
        return None, f"缺少环境变量：{', '.join(missing)}"

    try:
        port = int(values[_SMTP_PORT_ENV])
        if port <= 0:
            raise ValueError
    except Exception:
        return None, f"{_SMTP_PORT_ENV} 必须是正整数"

    raw_ssl = str(os.environ.get(_SMTP_USE_SSL_ENV) or "").strip().lower()
    raw_starttls = str(os.environ.get(_SMTP_USE_STARTTLS_ENV) or "").strip().lower()
    use_ssl = (port == 465) if not raw_ssl else raw_ssl in {"1", "true", "yes", "on"}
    use_starttls = (port == 587 and not use_ssl) if not raw_starttls else raw_starttls in {"1", "true", "yes", "on"}
    if use_ssl:
        use_starttls = False

    try:
        timeout_sec = float(str(os.environ.get(_SMTP_TIMEOUT_ENV) or "8").strip() or "8")
    except Exception:
        timeout_sec = 8.0
    timeout_sec = max(2.0, timeout_sec)

    return (
        SmtpConfig(
            host=values[_SMTP_HOST_ENV],
            port=port,
            user=values[_SMTP_USER_ENV],
            password=values[_SMTP_PASSWORD_ENV],
            use_ssl=use_ssl,
            use_starttls=use_starttls,
            timeout_sec=timeout_sec,
        ),
        "",
    )


def check_notification_availability() -> NotificationAvailability:
    cfg, err = load_smtp_config_from_env()
    if not cfg:
        return NotificationAvailability(enabled=False, reason=err)
    try:
        with socket.create_connection((cfg.host, cfg.port), timeout=cfg.timeout_sec):
            pass
    except OSError as e:
        return NotificationAvailability(enabled=False, reason=f"无法连接 SMTP 服务器 {cfg.host}:{cfg.port}（{e}）")
    return NotificationAvailability(enabled=True, reason="通知功能可用")


def load_task_run_summary(run_dir: str, task_json_name: str, reason: str = "") -> TaskRunSummary:
    run_path = Path(run_dir) if run_dir else Path()
    report_path = run_path / "report.html" if run_dir else Path()
    summary = TaskRunSummary(
        task_json_name=task_json_name,
        status=("stopped" if reason == "stopped" else "unknown"),
        report_path=str(report_path) if report_path.exists() else "",
        run_dir=run_dir or "",
    )

    if not run_dir:
        return summary

    result_path = run_path / "result.json"
    if not result_path.exists():
        summary.status = "failed" if reason == "failed" else summary.status
        return summary

    try:
        raw = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception:
        summary.status = "failed" if reason == "failed" else summary.status
        return summary

    if not isinstance(raw, dict):
        summary.status = "failed" if reason == "failed" else summary.status
        return summary

    summary.started_at = str(raw.get("started_at") or "").strip()
    summary.finished_at = str(raw.get("finished_at") or "").strip()
    summary.status = "failed"
    if reason == "stopped":
        summary.status = "stopped"
    elif bool(raw.get("all_passed")):
        summary.status = "passed"

    step_results = raw.get("step_results")
    if isinstance(step_results, list):
        for item in step_results:
            if not isinstance(item, dict):
                continue
            if str(item.get("status") or "").lower() != "failed":
                continue
            summary.failed_step_name = str(item.get("name") or item.get("id") or "").strip()
            if item.get("screenshot"):
                summary.screenshot_path = str(item.get("screenshot") or "").strip()
            else:
                extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
                summary.screenshot_path = str(extra.get("snapshot") or "").strip()
            break

    return summary


def _status_text(status: str) -> str:
    mapping = {
        "passed": "通过",
        "failed": "失败",
        "stopped": "已停止",
        "skipped": "已跳过",
        "unknown": "未知",
    }
    return mapping.get(status, status or "未知")


def _build_failure_body(summary: TaskRunSummary) -> str:
    lines = [
        "自动化测试失败通知",
        "",
        f"任务文件: {summary.task_json_name}",
        f"任务状态: {_status_text(summary.status)}",
        f"开始时间: {summary.started_at or '-'}",
        f"结束时间: {summary.finished_at or '-'}",
        f"失败步骤: {summary.failed_step_name or '-'}",
        f"截图路径: {summary.screenshot_path or '-'}",
        f"报告路径: {summary.report_path or '-'}",
        f"产物目录: {summary.run_dir or '-'}",
    ]
    return "\n".join(lines)


def _build_success_body(summary: TaskRunSummary) -> str:
    lines = [
        "自动化测试成功通知",
        "",
        f"任务文件: {summary.task_json_name}",
        f"任务状态: {_status_text(summary.status)}",
        f"开始时间: {summary.started_at or '-'}",
        f"结束时间: {summary.finished_at or '-'}",
        f"报告路径: {summary.report_path or '-'}",
        f"产物目录: {summary.run_dir or '-'}",
    ]
    return "\n".join(lines)


def _build_queue_complete_body(
    queue_started_at: str,
    queue_finished_at: str,
    task_summaries: Sequence[TaskRunSummary],
) -> str:
    lines = [
        "自动化测试队列执行结束",
        "",
        f"开始时间: {queue_started_at or '-'}",
        f"结束时间: {queue_finished_at or '-'}",
        "",
        "任务状态汇总:",
    ]
    for idx, summary in enumerate(task_summaries, start=1):
        lines.append(f"{idx}. {summary.task_json_name} - {_status_text(summary.status)}")
        if summary.failed_step_name:
            lines.append(f"   失败步骤: {summary.failed_step_name}")
        if summary.report_path:
            lines.append(f"   报告路径: {summary.report_path}")
    return "\n".join(lines)


def _attachment_name(task_json_name: str, source_path: Path) -> str:
    stem = Path(task_json_name).stem or source_path.stem
    suffix = source_path.suffix or ".bin"
    return f"{stem}{suffix}"


def _add_attachment(msg: EmailMessage, path: Path, display_name: str) -> None:
    ctype, _ = mimetypes.guess_type(display_name)
    if ctype:
        maintype, subtype = ctype.split("/", 1)
    else:
        maintype, subtype = "application", "octet-stream"
    data = path.read_bytes()
    msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=display_name)


def _send_email(
    cfg: SmtpConfig,
    recipient_email: str,
    subject: str,
    body: str,
    attachments: Iterable[tuple[Path, str]],
) -> None:
    msg = EmailMessage()
    msg["From"] = formataddr((str(Header(_SMTP_FROM_DISPLAY_NAME, "utf-8")), cfg.user))
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)

    for path, display_name in attachments:
        if path.exists() and path.is_file():
            _add_attachment(msg, path, display_name)

    if cfg.use_ssl:
        server = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=cfg.timeout_sec)
    else:
        server = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout_sec)

    with server:
        server.ehlo()
        if cfg.use_starttls:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        server.login(cfg.user, cfg.password)
        server.send_message(msg)


class NotificationDispatcher(QtCore.QObject):
    status = QtCore.pyqtSignal(str, str)  # level, message

    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self._project_root = Path(project_root)
        load_project_dotenv(self._project_root)
        self._settings = load_notification_settings(self._project_root)

    @property
    def settings(self) -> NotificationSettings:
        return self._settings

    def set_recipient_email(self, email: str) -> None:
        self._settings.recipient_email = (email or "").strip()
        save_notification_settings(self._project_root, self._settings)

    def set_label(self, label: str) -> None:
        self._settings.label = (label or "").strip()
        save_notification_settings(self._project_root, self._settings)

    def refresh_availability(self) -> NotificationAvailability:
        return check_notification_availability()

    def send_failure_email(self, summary: TaskRunSummary) -> None:
        label = self._settings.label.strip()
        if label:
            subject = f"{label}-pc端软件ui自动化测试失败"
        else:
            subject = f"自动化测试失败通知 - {summary.task_json_name}"
        body = _build_failure_body(summary)
        attachments: list[tuple[Path, str]] = []
        if summary.report_path:
            report_path = Path(summary.report_path)
            attachments.append((report_path, _attachment_name(summary.task_json_name, report_path)))
        self._send_async(subject, body, attachments, f"失败通知[{summary.task_json_name}]")

    def send_success_email(self, summary: TaskRunSummary) -> None:
        label = self._settings.label.strip()
        if label:
            subject = f"{label}-pc端软件ui自动化测试成功"
        else:
            subject = f"自动化测试成功通知 - {summary.task_json_name}"
        body = _build_success_body(summary)
        attachments: list[tuple[Path, str]] = []
        if summary.report_path:
            report_path = Path(summary.report_path)
            attachments.append((report_path, _attachment_name(summary.task_json_name, report_path)))
        self._send_async(subject, body, attachments, f"成功通知[{summary.task_json_name}]")

    def send_queue_complete_email(
        self,
        queue_started_at: str,
        queue_finished_at: str,
        task_summaries: Sequence[TaskRunSummary],
    ) -> None:
        subject = f"自动化测试队列完成通知 - {len(task_summaries)} 个任务"
        body = _build_queue_complete_body(queue_started_at, queue_finished_at, task_summaries)
        attachments: list[tuple[Path, str]] = []
        for summary in task_summaries:
            if not summary.report_path:
                continue
            report_path = Path(summary.report_path)
            attachments.append((report_path, _attachment_name(summary.task_json_name, report_path)))
        self._send_async(subject, body, attachments, f"队列完成通知[{len(task_summaries)}]")

    def send_tool_result_email(
        self,
        tool_name: str,
        status: str,
        report_path: str = "",
    ) -> None:
        subject = f"{tool_name}完成通知 - {_status_text(status)}"
        body = "\n".join(
            [
                f"{tool_name}执行结束",
                "",
                f"执行状态: {_status_text(status)}",
                f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"测试报告: {report_path or '-'}",
            ]
        )
        attachments: list[tuple[Path, str]] = []
        if report_path:
            report = Path(report_path)
            attachments.append((report, report.name))
        self._send_async(subject, body, attachments, f"工具通知[{tool_name}]")

    def _send_async(
        self,
        subject: str,
        body: str,
        attachments: Sequence[tuple[Path, str]],
        label: str,
    ) -> None:
        recipient_email = self._settings.recipient_email.strip()
        if not is_valid_email(recipient_email):
            self.status.emit("warning", f"邮件通知未发送：收件邮箱无效（{label}）")
            return

        def _worker() -> None:
            cfg, err = load_smtp_config_from_env()
            if not cfg:
                self.status.emit("warning", f"邮件通知已禁用：{err}")
                return
            try:
                with socket.create_connection((cfg.host, cfg.port), timeout=cfg.timeout_sec):
                    pass
            except OSError as e:
                self.status.emit("warning", f"邮件通知已禁用：无法连接 SMTP 服务器（{e}）")
                return
            try:
                _send_email(cfg, recipient_email, subject, body, attachments)
            except Exception as e:
                self.status.emit("error", f"邮件发送失败：{label}，{e}")
                return
            self.status.emit("success", f"邮件发送成功：{label}")

        threading.Thread(target=_worker, name="notification-email", daemon=True).start()
