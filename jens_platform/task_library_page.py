from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets  # type: ignore

from jens_platform.case_store import load_task_json, save_task_json
from jens_platform.dialogs import TaskManagerDialog, _open_path, show_error


class TaskLibraryPage(QtWidgets.QWidget):
    """任务库工作区页面：集中管理 tasks/*.json，按扫描模组分类。"""

    statusMessage = QtCore.pyqtSignal(str)
    enqueueRequested = QtCore.pyqtSignal(list)  # list[Path]
    loadRequested = QtCore.pyqtSignal(str)  # 单个任务路径
    tasksChanged = QtCore.pyqtSignal()

    def __init__(self, project_root: Path, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._project_root = project_root
        self._all: list[Path] = []
        self._category_by_path: dict[Path, str] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QtWidgets.QFrame()
        top_bar.setObjectName("topBar")
        top = QtWidgets.QHBoxLayout(top_bar)
        top.setContentsMargins(22, 12, 22, 12)
        heading = QtWidgets.QVBoxLayout()
        heading.setSpacing(2)
        title = QtWidgets.QLabel("任务库")
        title.setObjectName("pageTitle")
        subtitle = QtWidgets.QLabel("管理 tasks/*.json，按扫描模组分类")
        subtitle.setObjectName("pageSubtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        top.addLayout(heading, 1)
        self.btn_add = QtWidgets.QPushButton("添加任务")
        self.btn_add.setObjectName("secondaryBtn")
        self.btn_add.clicked.connect(self._add_tasks)
        top.addWidget(self.btn_add)
        self.btn_refresh = QtWidgets.QPushButton("刷新")
        self.btn_refresh.setObjectName("secondaryBtn")
        self.btn_refresh.clicked.connect(self.refresh)
        top.addWidget(self.btn_refresh)
        self.btn_open_dir = QtWidgets.QPushButton("打开 tasks 目录")
        self.btn_open_dir.setObjectName("secondaryBtn")
        self.btn_open_dir.clicked.connect(self._open_tasks_dir)
        top.addWidget(self.btn_open_dir)
        root.addWidget(top_bar)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(22, 18, 22, 20)
        content_layout.setSpacing(10)

        self.lab_summary = QtWidgets.QLabel("正在读取任务…")
        self.lab_summary.setObjectName("mutedText")
        content_layout.addWidget(self.lab_summary)

        self.edit_filter = QtWidgets.QLineEdit()
        self.edit_filter.setPlaceholderText("搜索任务（按文件名或分类）")
        self.edit_filter.textChanged.connect(self._apply_filter)
        content_layout.addWidget(self.edit_filter)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(22)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(self._emit_load)
        self.tree.itemSelectionChanged.connect(self._refresh_action_state)
        content_layout.addWidget(self.tree, 1)

        self.lab_empty = QtWidgets.QLabel("任务库中没有匹配的任务。可清除搜索条件，或点击“添加任务”导入 JSON。")
        self.lab_empty.setObjectName("mutedText")
        self.lab_empty.setAlignment(QtCore.Qt.AlignCenter)
        self.lab_empty.setWordWrap(True)
        self.lab_empty.setMinimumHeight(64)
        self.lab_empty.hide()
        content_layout.addWidget(self.lab_empty)

        actions = QtWidgets.QHBoxLayout()
        self.btn_delete = QtWidgets.QPushButton("删除")
        self.btn_delete.setObjectName("dangerBtn")
        self.btn_delete.clicked.connect(self._delete_selected)
        actions.addWidget(self.btn_delete)
        actions.addStretch(1)
        self.btn_enqueue = QtWidgets.QPushButton("加入主界面")
        self.btn_enqueue.setObjectName("primaryBtn")
        self.btn_enqueue.clicked.connect(self._emit_enqueue)
        actions.addWidget(self.btn_enqueue)
        self.btn_load = QtWidgets.QPushButton("加载到编辑器")
        self.btn_load.setObjectName("secondaryBtn")
        self.btn_load.clicked.connect(self._emit_load)
        actions.addWidget(self.btn_load)
        content_layout.addLayout(actions)

        root.addWidget(content, 1)
        self._refresh_action_state()

    def _tasks_dir(self) -> Path:
        d = self._project_root / "tasks"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _task_category(self, task_path: Path) -> str:
        return TaskManagerDialog._task_category(task_path)

    def refresh(self) -> None:
        self._all = []
        self._category_by_path = {}
        d = self._tasks_dir()
        try:
            fps = [p for p in d.glob("*.json") if p.is_file() and p.name.lower() != "_queue.json"]
            fps.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            self._all = fps
            self._category_by_path = {p: self._task_category(p) for p in fps}
        except OSError:
            self._all = []
            self._category_by_path = {}
        self._apply_filter()
        self.lab_summary.setText(f"共 {len(self._all)} 个任务 · 按扫描模组分类")

    def _apply_filter(self) -> None:
        text = self.edit_filter.text().strip().lower()
        self.tree.clear()
        grouped: dict[str, list[Path]] = {}
        for p in self._all:
            name = p.name
            category = self._category_by_path.get(p, "测试任务")
            if text and text not in name.lower() and text not in category.lower():
                continue
            grouped.setdefault(category, []).append(p)

        order = {name: index for index, name in enumerate(TaskManagerDialog._CATEGORY_ORDER)}
        first_task_item = None
        for category in sorted(grouped, key=lambda name: (order.get(name, len(order)), name.lower())):
            paths = grouped[category]
            group_item = QtWidgets.QTreeWidgetItem([f"{category}（{len(paths)}）"])
            group_item.setFlags(group_item.flags() & ~QtCore.Qt.ItemIsSelectable)
            group_font = group_item.font(0)
            group_font.setBold(True)
            group_item.setFont(0, group_font)
            group_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#355278")))
            group_item.setBackground(0, QtGui.QBrush(QtGui.QColor("#edf4ff")))
            group_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
            group_item.setToolTip(0, f"{category}：{len(paths)} 个任务")
            self.tree.addTopLevelItem(group_item)

            for path in paths:
                task_item = QtWidgets.QTreeWidgetItem([path.name])
                task_item.setToolTip(0, str(path))
                task_item.setData(0, QtCore.Qt.UserRole, str(path))
                task_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                group_item.addChild(task_item)
                if first_task_item is None:
                    first_task_item = task_item
            group_item.setExpanded(True)

        if first_task_item is not None:
            self.tree.setCurrentItem(first_task_item)
        has_results = first_task_item is not None
        self.tree.setVisible(has_results)
        self.lab_empty.setVisible(not has_results)
        self._refresh_action_state()

    def _selected_paths(self) -> list[Path]:
        out: list[Path] = []
        for it in self.tree.selectedItems():
            raw = it.data(0, QtCore.Qt.UserRole)
            if isinstance(raw, str) and raw:
                out.append(Path(raw))
        return out

    def _refresh_action_state(self) -> None:
        selected = self._selected_paths()
        self.btn_delete.setEnabled(bool(selected))
        self.btn_enqueue.setEnabled(bool(selected))
        self.btn_load.setEnabled(len(selected) == 1)

    def _emit_enqueue(self) -> None:
        paths = self._selected_paths()
        if not paths:
            self.lab_summary.setText("请先选择至少一个任务。")
            return
        self.enqueueRequested.emit(paths)
        self.statusMessage.emit(f"已加入队列：{len(paths)} 个任务")

    def _emit_load(self, *_) -> None:
        paths = self._selected_paths()
        if not paths:
            self.lab_summary.setText("请先选择至少一个任务。")
            return
        if len(paths) != 1:
            self.lab_summary.setText("加载到编辑器时只能选择一个任务。")
            return
        self.loadRequested.emit(str(paths[0]))

    def _safe_task_stem(self, name: str) -> str:
        s = (name or "task").strip() or "task"
        s = re.sub(r'[<>:"/\\|?*]+', "_", s)
        s = re.sub(r"\s+", " ", s)
        s = s.strip().strip(".")
        if not s:
            s = "task"
        return s[:80]

    def _unique_task_path(self, stem: str) -> Path:
        base = self._tasks_dir()
        stem = self._safe_task_stem(stem)
        cand = base / f"{stem}.json"
        if not cand.exists():
            return cand
        i = 2
        while True:
            p = base / f"{stem}_{i}.json"
            if not p.exists():
                return p
            i += 1

    def _add_tasks(self) -> None:
        base = self._tasks_dir()
        fps, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "选择任务 JSON（可多选）",
            str(base),
            "JSON (*.json)",
        )
        if not fps:
            return

        added: list[Path] = []
        failed: list[str] = []
        for fp in fps:
            src = Path(fp)
            try:
                model = load_task_json(src)
                stem = (model.name or model.case_id or src.stem).strip() or src.stem
                dst = self._unique_task_path(stem)
                try:
                    if src.resolve() == dst.resolve():
                        continue
                except Exception:
                    pass
                save_task_json(self._project_root, model, path=dst)
                added.append(dst)
            except Exception as e:
                failed.append(f"{src.name}: {e}")

        if failed and not added:
            show_error(self, "添加任务失败", "\n".join(failed[:12]))
            return

        self.refresh()
        if added:
            self.statusMessage.emit(f"已添加 {len(added)} 个任务")
            self.tasksChanged.emit()

    def _delete_selected(self) -> None:
        fps = self._selected_paths()
        if not fps:
            return
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("确认删除")
        box.setText(f"确定删除 {len(fps)} 个任务文件吗？此操作不可恢复。")
        box.setStandardButtons(QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Ok)
        if box.exec_() != QtWidgets.QMessageBox.Ok:
            return

        ok = 0
        for p in fps:
            try:
                p.unlink(missing_ok=True)
                ok += 1
            except TypeError:
                try:
                    if p.exists():
                        p.unlink()
                        ok += 1
                except Exception:
                    pass
            except Exception:
                pass

        self.refresh()
        self.statusMessage.emit(f"已删除 {ok}/{len(fps)} 个任务")
        if ok:
            self.tasksChanged.emit()

    def _open_tasks_dir(self) -> None:
        _open_path(str(self._tasks_dir()))

    def activate(self) -> None:
        self.refresh()
