#!/usr/bin/env python3
"""Connected-first Windows library manager for Allmiibo/Pixl.js.

THESIS: The device is the workspace; local files are inputs, never the product.
OWN-WORLD: A calm graphite utility with mint connection signals and one forest
import action, using native explorer controls instead of dashboard cards.
STORY: Connect, see the real library, make a precise change, receive proof.
FIRST VIEWPORT: Connection state in the header, device tree at full scale, one
compact command bar, and activity anchored below.
FORM: Persistent device explorer; dense where files matter, quiet elsewhere.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import traceback
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from queue import Empty, Queue
from threading import Event
from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, QThread, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from allmiibo_manager import (
    AllmiiboManager,
    ConnectionInfo,
    DeleteReport,
    ImportReport,
    RemoteItem,
    TransferReport,
    is_protected_directory_path,
)
from allmiibo_ble import (
    BluetoothDependencyError,
    DeviceCommandError,
    DeviceNotFoundError,
    ProtocolError,
)


AMIIBO_LIBRARY_URL = (
    "https://drive.google.com/drive/folders/"
    "1fNo0qv-6GnMwNWXwZ6WLZI5LQzH-jX9f"
)
DFU_UPDATE_URL = "https://thegecko.github.io/web-bluetooth-dfu"
FIRMWARE_RELEASES_URL = "https://github.com/solosky/pixl.js/releases"


def resource_path(relative_path: str) -> Path:
    """Resolve a bundled PyInstaller asset or its development path."""

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


APP_ICON_PATH = resource_path("assets/amiibo-app-icon-source.png")


@dataclass(frozen=True)
class LibraryDelta:
    """Minimal changes needed to keep the visible tree in sync."""

    upserted: tuple[RemoteItem, ...]
    removed: tuple[str, ...]


class WindowsTaskbarProgress:
    """Small dependency-free wrapper around Windows ITaskbarList3."""

    NO_PROGRESS = 0
    INDETERMINATE = 1
    NORMAL = 2
    ERROR = 4

    def __init__(self, window: QMainWindow) -> None:
        self._pointer: ctypes.c_void_p | None = None
        self._window = window
        if sys.platform != "win32":
            return
        try:
            class Guid(ctypes.Structure):
                _fields_ = [
                    ("data1", ctypes.c_uint32),
                    ("data2", ctypes.c_uint16),
                    ("data3", ctypes.c_uint16),
                    ("data4", ctypes.c_ubyte * 8),
                ]

                @classmethod
                def parse(cls, value: str) -> "Guid":
                    return cls.from_buffer_copy(uuid.UUID(value).bytes_le)

            pointer = ctypes.c_void_p()
            result = ctypes.windll.ole32.CoCreateInstance(
                ctypes.byref(Guid.parse("56FDF344-FD6D-11D0-958A-006097C9A090")),
                None,
                1,
                ctypes.byref(Guid.parse("EA1AFB91-9E28-4B86-90E9-9E9F8A5EEA84")),
                ctypes.byref(pointer),
            )
            if result < 0 or not pointer.value:
                return
            self._pointer = pointer
            self._invoke(3, ctypes.c_long)
        except Exception:
            self._pointer = None

    def _invoke(self, index: int, result_type: Any, *arguments: Any) -> Any:
        if self._pointer is None:
            return None
        vtable = ctypes.cast(
            self._pointer,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
        ).contents
        argument_types = [ctypes.c_void_p] + [type(value) for value in arguments]
        function = ctypes.WINFUNCTYPE(result_type, *argument_types)(vtable[index])
        return function(self._pointer, *arguments)

    def _set_state(self, state: int) -> None:
        try:
            self._invoke(
                10,
                ctypes.c_long,
                ctypes.c_void_p(int(self._window.winId())),
                ctypes.c_uint(state),
            )
        except Exception:
            self._pointer = None

    def indeterminate(self) -> None:
        self._set_state(self.INDETERMINATE)

    def set_value(self, current: int, total: int) -> None:
        if total <= 0:
            self.indeterminate()
            return
        try:
            self._set_state(self.NORMAL)
            self._invoke(
                9,
                ctypes.c_long,
                ctypes.c_void_p(int(self._window.winId())),
                ctypes.c_ulonglong(max(0, current)),
                ctypes.c_ulonglong(max(1, total)),
            )
        except Exception:
            self._pointer = None

    def error(self) -> None:
        self._set_state(self.ERROR)

    def clear(self) -> None:
        self._set_state(self.NO_PROGRESS)

    def close(self) -> None:
        if self._pointer is None:
            return
        try:
            self.clear()
            self._invoke(2, ctypes.c_ulong)
        finally:
            self._pointer = None


class ConnectionVisual(QWidget):
    """Small vector BLE/device illustration with a restrained search pulse."""

    def __init__(self) -> None:
        super().__init__()
        self._phase = 0.0
        self._connected = False
        self.setFixedSize(220, 150)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(45)

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self.update()

    def _advance(self) -> None:
        self._phase = (self._phase + 0.025) % 1.0
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        accent = QColor("#58d6a5" if self._connected else "#68a8ff")

        if not self._connected:
            for offset in (0.0, 0.34, 0.67):
                phase = (self._phase + offset) % 1.0
                radius = 42 + phase * 42
                color = QColor(accent)
                color.setAlphaF((1.0 - phase) * 0.22)
                painter.setPen(QPen(color, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(center, radius, radius)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#202832"))
        body = QRectF(center.x() - 39, center.y() - 52, 78, 104)
        painter.drawRoundedRect(body, 18, 18)
        painter.setBrush(QColor("#0f141a"))
        painter.drawRoundedRect(body.adjusted(8, 9, -8, -21), 11, 11)
        painter.setBrush(accent)
        painter.drawEllipse(QPointF(center.x(), center.y() + 39), 4, 4)

        painter.setPen(QPen(accent, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(center.x(), center.y() - 23), QPointF(center.x(), center.y() + 23))
        painter.drawLine(QPointF(center.x(), center.y() - 23), QPointF(center.x() + 15, center.y() - 8))
        painter.drawLine(QPointF(center.x() + 15, center.y() - 8), QPointF(center.x() - 12, center.y() + 12))
        painter.drawLine(QPointF(center.x() - 12, center.y() - 12), QPointF(center.x() + 15, center.y() + 8))
        painter.drawLine(QPointF(center.x() + 15, center.y() + 8), QPointF(center.x(), center.y() + 23))


class GlobalSelectionCheckBox(QCheckBox):
    """Tri-state display with deterministic all/none behavior on user input."""

    toggle_requested = Signal(bool)

    def nextCheckState(self) -> None:
        checked = self.checkState() != Qt.CheckState.Checked
        self.setCheckState(
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        self.toggle_requested.emit(checked)


class SelectionHeader(QHeaderView):
    """Header with a real global checkbox aligned over the selection column."""

    toggle_requested = Signal(bool)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.checkbox = GlobalSelectionCheckBox(self.viewport())
        self.checkbox.setTristate(True)
        self.checkbox.setEnabled(False)
        self.checkbox.setToolTip("Select all deletable items")
        self.checkbox.setAccessibleName("Select all deletable items")
        self.checkbox.toggle_requested.connect(
            lambda checked: self.toggle_requested.emit(checked)
        )
        self.sectionResized.connect(lambda *_: self._position_checkbox())
        self.geometriesChanged.connect(self._position_checkbox)

    def _position_checkbox(self) -> None:
        size = self.checkbox.sizeHint()
        left = self.sectionViewportPosition(0)
        width = self.sectionSize(0)
        self.checkbox.setGeometry(
            left + max(0, (width - size.width()) // 2),
            max(0, (self.height() - size.height()) // 2),
            size.width(),
            size.height(),
        )

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._position_checkbox()


class LibraryTree(QTreeWidget):
    paths_dropped = Signal(object)
    empty_area_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.DropOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    @staticmethod
    def _local_paths(event: QDragEnterEvent | QDropEvent) -> list[Path]:
        return [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        paths = self._local_paths(event)
        if paths and all(
            path.is_dir() or path.suffix.lower() in {".bin", ".zip"} for path in paths
        ):
            event.acceptProposedAction()

    def dragMoveEvent(self, event: Any) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._local_paths(event)
        if paths:
            target = self.itemAt(event.position().toPoint())
            self.clearSelection()
            self.setCurrentItem(target)
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        clicked_empty_area = (
            event.button() == Qt.MouseButton.LeftButton
            and self.itemAt(event.position().toPoint()) is None
        )
        super().mousePressEvent(event)
        if clicked_empty_area:
            self.clearSelection()
            self.setCurrentItem(None)
            self.empty_area_clicked.emit()


class ResponsiveActionBar(QWidget):
    """Keep a readable prefix of actions and place the rest in an inline menu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("actionBar")
        self.entries: list[tuple[QAction, QToolButton]] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self.more_menu = QMenu(self)
        self.more_button = QToolButton(self)
        self.more_button.setText("More")
        self.more_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.more_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.more_button.setIconSize(QSize(12, 12))
        self._set_more_expanded(False)
        self.more_button.clicked.connect(self._open_more_menu)
        self.more_menu.aboutToShow.connect(lambda: self._set_more_expanded(True))
        self.more_menu.aboutToHide.connect(lambda: self._set_more_expanded(False))
        self.more_button.setAccessibleName("More actions")
        self.more_button.setToolTip("Show additional actions")
        self.more_button.hide()
        self._layout.addWidget(self.more_button)
        self._layout.addStretch(1)

    def add_action(self, action: QAction, *, primary: bool = False) -> QToolButton:
        button = QToolButton(self)
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(QSize(22, 16))

        def update_spaced_icon() -> None:
            source = action.icon().pixmap(16, 16)
            canvas = QPixmap(22, 16)
            canvas.fill(Qt.GlobalColor.transparent)
            painter = QPainter(canvas)
            painter.drawPixmap(0, 0, source)
            painter.end()
            button.setIcon(QIcon(canvas))

        update_spaced_icon()
        action.changed.connect(update_spaced_icon)
        if primary:
            button.setObjectName("primaryToolButton")
        self.entries.append((action, button))
        self._layout.insertWidget(len(self.entries) - 1, button)
        QTimer.singleShot(0, self.reflow)
        return button

    def _set_more_expanded(self, expanded: bool) -> None:
        pixmap = (
            QStyle.StandardPixmap.SP_ArrowUp
            if expanded
            else QStyle.StandardPixmap.SP_ArrowDown
        )
        self.more_button.setIcon(self.style().standardIcon(pixmap))

    def _open_more_menu(self) -> None:
        self.more_menu.popup(
            self.more_button.mapToGlobal(QPoint(0, self.more_button.height()))
        )

    def reflow(self) -> None:
        if not self.entries:
            self.more_button.hide()
            return

        spacing = self._layout.spacing()
        available = max(0, self.width())
        widths = [button.sizeHint().width() for _, button in self.entries]
        total = sum(widths) + spacing * max(0, len(widths) - 1)
        if total <= available:
            visible_count = len(self.entries)
        else:
            reserved = self.more_button.sizeHint().width() + spacing
            used = 0
            visible_count = 0
            for width in widths:
                addition = width + (spacing if visible_count else 0)
                if visible_count and used + addition + reserved > available:
                    break
                used += addition
                visible_count += 1
            visible_count = max(1, min(visible_count, len(self.entries) - 1))

        self.more_menu.clear()
        for index, (action, button) in enumerate(self.entries):
            visible = index < visible_count
            button.setVisible(visible)
            if not visible:
                self.more_menu.addAction(action)
        self.more_button.setVisible(visible_count < len(self.entries))

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.reflow()


class DeviceController(QThread):
    connection_state = Signal(str, str)
    connected = Signal(object)
    device_info_updated = Signal(object)
    disconnected = Signal(str)
    library_loaded = Signal(object)
    library_changed = Signal(object)
    busy_changed = Signal(bool, str)
    operation_detail = Signal(str)
    progress = Signal(int, int, str, str)
    operation_done = Signal(str, object, float)
    operation_error = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._commands: Queue[tuple[str, Any]] = Queue()
        self._shutdown_requested = Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._serve_task: asyncio.Task[None] | None = None
        self._current_stage = ""
        self._progress_active = False

    def submit(self, command: str, payload: Any = None) -> None:
        self._commands.put((command, payload))

    def reconnect(self) -> None:
        self.submit("connect")

    def shutdown(self) -> None:
        self._shutdown_requested.set()
        self.submit("shutdown")
        loop = self._loop
        task = self._serve_task
        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass

    def run(self) -> None:
        try:
            asyncio.run(self._serve())
        except asyncio.CancelledError:
            pass

    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._serve_task = asyncio.current_task()
        manager = AllmiiboManager()
        retry_delay = 4.0
        try:
            if self._shutdown_requested.is_set():
                return
            if await self._connect(manager):
                retry_delay = 4.0
            while True:
                try:
                    command, payload = await asyncio.to_thread(
                        self._commands.get,
                        True,
                        12.0 if manager.connected else retry_delay,
                    )
                except Empty:
                    if manager.connected:
                        try:
                            await manager.ping()
                        except Exception as error:
                            await manager.close()
                            self.disconnected.emit(
                                f"Connection lost: {self._friendly_error(error)}"
                            )
                            retry_delay = 4.0
                    elif await self._connect(manager):
                        retry_delay = 4.0
                    else:
                        retry_delay = min(retry_delay * 1.7, 30.0)
                    continue

                if command == "shutdown":
                    return
                if command == "connect":
                    retry_delay = 4.0
                    await self._connect(manager)
                    continue
                if not manager.connected:
                    self.operation_error.emit(
                        "Allmiibo not connected",
                        "Reconnect the device before continuing.",
                    )
                    continue

                await self._dispatch(manager, command, payload)
        finally:
            await manager.close()
            self._serve_task = None
            self._loop = None

    async def _connect(self, manager: AllmiiboManager) -> bool:
        self._progress_active = False
        self.busy_changed.emit(True, "Scanning the existing folder structure…")
        self.connection_state.emit(
            "searching", "Enable Bluetooth Transmission on the Allmiibo."
        )
        heartbeat: asyncio.Task[None] | None = None
        try:
            info = await manager.connect()
            self.connected.emit(info)
            self._emit_detail("BLE connection established.")
            heartbeat = asyncio.create_task(self._heartbeat())
            await self._refresh(manager, force_library=True)
            return True
        except Exception as error:
            await manager.close()
            self.disconnected.emit(self._friendly_error(error))
            return False
        finally:
            await self._stop_heartbeat(heartbeat)
            self.busy_changed.emit(False, "")

    def _emit_detail(self, message: str) -> None:
        self._current_stage = message
        self.operation_detail.emit(message)

    async def _heartbeat(self) -> None:
        started = asyncio.get_running_loop().time()
        while True:
            await asyncio.sleep(5)
            if self._progress_active:
                continue
            elapsed = int(asyncio.get_running_loop().time() - started)
            stage = self._current_stage or "Communicating with the Allmiibo…"
            self.operation_detail.emit(
                f"Still working ({elapsed} s) — {stage}"
            )

    @staticmethod
    async def _stop_heartbeat(task: asyncio.Task[None] | None) -> None:
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _refresh(
        self,
        manager: AllmiiboManager,
        *,
        force_library: bool,
    ) -> None:
        self._emit_detail("1/3 — Reading storage capacity…")
        info = await manager.refresh_info()
        self._emit_detail(
            "2/3 — Scanning every folder on the Allmiibo…"
            if force_library
            else "2/3 — Reading the updated in-memory index…"
        )
        items = await manager.list_library(
            force_refresh=force_library,
            status_callback=self._emit_detail,
        )
        self._emit_detail("3/3 — Updating the displayed folder tree…")
        self.device_info_updated.emit(info)
        self.library_loaded.emit(items)

    async def _publish_library_delta(
        self,
        manager: AllmiiboManager,
        previous: dict[str, RemoteItem],
    ) -> None:
        self._emit_detail("Updating available storage…")
        info = await manager.refresh_info()
        items = await manager.list_library()
        current = {item.relative_path: item for item in items}
        delta = LibraryDelta(
            upserted=tuple(
                item
                for path, item in current.items()
                if previous.get(path) != item
            ),
            removed=tuple(path for path in previous if path not in current),
        )
        self._emit_detail(
            "Incremental update: "
            f"{len(delta.upserted)} added or changed, "
            f"{len(delta.removed)} removed — no full scan."
        )
        self.device_info_updated.emit(info)
        self.library_changed.emit(delta)

    def _emit_progress(self, current: int, total: int, action: str, path: str) -> None:
        self._progress_active = True
        self.progress.emit(current, total, action, path)

    async def _dispatch(
        self, manager: AllmiiboManager, command: str, payload: Any
    ) -> None:
        labels = {
            "refresh": "Refreshing the library…",
            "upload": "Uploading files…",
            "import": "Updating the full library…",
            "mkdir": "Creating folder…",
            "rename": "Renaming…",
            "delete": "Deleting…",
        }
        label = labels.get(command, "Operation in progress…")
        if command == "upload":
            _, target = payload
            destination = "Library"
            if target:
                destination += " › " + target.replace("/", " › ")
            label = f"Uploading to {destination}…"
        self._current_stage = label
        self._progress_active = False
        self.busy_changed.emit(True, label)
        started = asyncio.get_running_loop().time()
        heartbeat = asyncio.create_task(self._heartbeat())
        try:
            result: Any = None
            previous = {
                item.relative_path: item
                for item in await manager.list_library()
            }
            if command == "refresh":
                self._emit_detail(
                    "Full refresh requested: the device will be scanned folder by folder."
                )
                await self._refresh(manager, force_library=True)
            elif command == "upload":
                sources, target = payload
                result = await manager.upload(
                    sources,
                    target,
                    progress_callback=self._emit_progress,
                    status_callback=self._emit_detail,
                )
            elif command == "import":
                result = await manager.import_archive(
                    payload,
                    progress_callback=self._emit_progress,
                    status_callback=self._emit_detail,
                )
            elif command == "mkdir":
                parent, name = payload
                result = await manager.create_folder(
                    parent, name, status_callback=self._emit_detail
                )
            elif command == "rename":
                relative, name = payload
                result = await manager.rename(
                    relative, name, status_callback=self._emit_detail
                )
            elif command == "delete":
                targets = payload if isinstance(payload, list) else [payload]
                result = await manager.delete_many(
                    targets, status_callback=self._emit_detail
                )
            else:
                raise ValueError(f"Unknown command: {command}")

            if command != "refresh":
                await self._publish_library_delta(manager, previous)
            elapsed = asyncio.get_running_loop().time() - started
            self.operation_done.emit(command, result, elapsed)
        except Exception as error:
            details = traceback.format_exc()
            self.operation_error.emit(self._friendly_error(error), details)
            try:
                await manager.ping()
            except Exception:
                await manager.close()
                self.disconnected.emit(
                    "The connection to the Allmiibo was interrupted."
                )
        finally:
            await self._stop_heartbeat(heartbeat)
            self.busy_changed.emit(False, "")

    @staticmethod
    def _friendly_error(error: Exception) -> str:
        if isinstance(error, (FileExistsError, FileNotFoundError, ValueError)):
            return str(error)
        if isinstance(error, BluetoothDependencyError):
            return "The application Bluetooth component is unavailable. Reinstall Allmiibo Manager."
        if isinstance(error, DeviceNotFoundError):
            return "No Allmiibo was detected. Enable Bluetooth Transmission and move the device closer."
        if isinstance(error, DeviceCommandError):
            return "The Allmiibo rejected the operation. Check its screen, then try again."
        if isinstance(error, ProtocolError):
            return "The Allmiibo response is incomplete. Keep it powered on while reconnecting."
        if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
            return "The Allmiibo is not responding. Move it closer to the PC and keep its screen on."
        if isinstance(error, OSError):
            return "Bluetooth is unavailable. Enable it in Windows, then try again."
        return "The operation could not be completed. Review the details, then try again."


class MainWindow(QMainWindow):
    def __init__(self, *, start_controller: bool = True) -> None:
        super().__init__()
        self._busy = False
        self._connected = False
        self._device_info: ConnectionInfo | None = None
        self._items: dict[str, RemoteItem] = {}
        self._tree_nodes: dict[str, QTreeWidgetItem] = {}
        self._selection_checkboxes: dict[str, QCheckBox] = {}
        self._protected_delete_paths: set[str] = set()
        self._actions: list[QAction] = []
        self._notification_tray: QSystemTrayIcon | None = None

        self.setWindowTitle("Allmiibo Manager")
        if APP_ICON_PATH.is_file():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(1080, 720)
        self.setMinimumSize(720, 520)
        self.setAcceptDrops(True)
        self._build_ui()
        self._apply_style()
        self.taskbar_progress = WindowsTaskbarProgress(self)

        self.controller = DeviceController()
        self.controller.connection_state.connect(self._on_connection_state)
        self.controller.connected.connect(self._on_connected)
        self.controller.device_info_updated.connect(self._update_device_info)
        self.controller.disconnected.connect(self._on_disconnected)
        self.controller.library_loaded.connect(self._populate_library)
        self.controller.library_changed.connect(self._apply_library_delta)
        self.controller.busy_changed.connect(self._set_busy)
        self.controller.operation_detail.connect(self._on_operation_detail)
        self.controller.progress.connect(self._on_progress)
        self.controller.operation_done.connect(self._on_operation_done)
        self.controller.operation_error.connect(self._on_operation_error)
        if start_controller:
            QTimer.singleShot(0, self.controller.start)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 18, 24, 20)
        root.setSpacing(14)
        self.setCentralWidget(central)

        header = QHBoxLayout()
        brand = QVBoxLayout()
        brand.setSpacing(0)
        title = QLabel("Allmiibo Manager")
        title.setObjectName("brand")
        subtitle = QLabel("Your library, directly on the device")
        subtitle.setObjectName("muted")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch()
        self.storage_label = QLabel("")
        self.storage_label.setObjectName("muted")
        self.connection_chip = QLabel(" Scanning… ")
        self.connection_chip.setObjectName("connectionChip")
        header.addWidget(self.storage_label)
        header.addWidget(self.connection_chip)
        root.addLayout(header)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.pages.addWidget(self._build_connection_page())
        self.pages.addWidget(self._build_library_page())

    def _build_connection_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)
        self.connection_visual = ConnectionVisual()
        self.connection_title = QLabel("Scanning the existing folder structure")
        self.connection_title.setObjectName("connectionTitle")
        self.connection_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_body = QLabel(
            "Open Bluetooth Transmission on the device.\n"
            "The application will connect and scan your folders automatically."
        )
        self.connection_body.setObjectName("muted")
        self.connection_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.retry_button = QPushButton("Search again")
        self.retry_button.setObjectName("primaryButton")
        self.retry_button.clicked.connect(self.controller_reconnect)
        self.retry_button.hide()
        resource_links = QHBoxLayout()
        resource_links.setSpacing(8)
        library_button = QPushButton("Amiibo library (Drive) ↗")
        library_button.setObjectName("linkButton")
        library_button.clicked.connect(self._open_library_source)
        dfu_button = QPushButton("Update firmware (DFU) ↗")
        dfu_button.setObjectName("linkButton")
        dfu_button.clicked.connect(self._open_dfu_update)
        releases_button = QPushButton("Download firmware ↗")
        releases_button.setObjectName("linkButton")
        releases_button.clicked.connect(self._open_firmware_releases)
        resource_links.addWidget(library_button)
        resource_links.addWidget(dfu_button)
        resource_links.addWidget(releases_button)
        layout.addStretch()
        layout.addWidget(self.connection_visual, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.connection_title)
        layout.addWidget(self.connection_body)
        layout.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(resource_links)
        layout.addStretch()
        return page

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        guide = QFrame()
        guide.setObjectName("guide")
        guide_layout = QVBoxLayout(guide)
        guide_layout.setContentsMargins(14, 10, 12, 10)
        guide_layout.setSpacing(4)
        library_row = QHBoxLayout()
        guide_label = QLabel(
            "Complete library: download the Google Drive folder as a ZIP, "
            "then import it."
        )
        guide_label.setWordWrap(True)
        guide_link = QPushButton("Open Drive ↗")
        guide_link.setObjectName("linkButton")
        guide_link.clicked.connect(self._open_library_source)
        library_row.addWidget(guide_label, 1)
        library_row.addWidget(guide_link)
        firmware_row = QHBoxLayout()
        firmware_note = QLabel("Kirby Air Riders requires Pixl.js firmware 2.16+.")
        firmware_note.setObjectName("guideNote")
        firmware_note.setWordWrap(True)
        dfu_link = QPushButton("DFU update ↗")
        dfu_link.setObjectName("linkButton")
        dfu_link.clicked.connect(self._open_dfu_update)
        releases_link = QPushButton("Releases ↗")
        releases_link.setObjectName("linkButton")
        releases_link.clicked.connect(self._open_firmware_releases)
        firmware_row.addWidget(firmware_note, 1)
        firmware_row.addWidget(dfu_link)
        firmware_row.addWidget(releases_link)
        guide_layout.addLayout(library_row)
        guide_layout.addLayout(firmware_row)
        layout.addWidget(guide)

        self.toolbar = ResponsiveActionBar()
        self.import_action = self._add_action(
            "Import ZIP",
            QStyle.StandardPixmap.SP_DialogOpenButton,
            self._choose_archive,
            primary=True,
        )
        self.add_action = self._add_action(
            "Add files", QStyle.StandardPixmap.SP_FileIcon, self._choose_files
        )
        self.folder_action = self._add_action(
            "Add folder", QStyle.StandardPixmap.SP_DirIcon, self._choose_folder
        )
        self.new_folder_action = self._add_action(
            "New folder",
            QStyle.StandardPixmap.SP_FileDialogNewFolder,
            self._create_folder,
        )
        self.rename_action = self._add_action(
            "Rename", QStyle.StandardPixmap.SP_FileDialogDetailedView, self._rename
        )
        self.delete_action = self._add_action(
            "Delete", QStyle.StandardPixmap.SP_TrashIcon, self._delete
        )
        self.refresh_action = self._add_action(
            "Refresh", QStyle.StandardPixmap.SP_BrowserReload, self._refresh
        )
        self.refresh_action.setToolTip(
            "Scan the entire device again. This operation may take several minutes."
        )
        layout.addWidget(self.toolbar)

        explorer = QFrame()
        explorer.setObjectName("explorer")
        explorer_layout = QVBoxLayout(explorer)
        explorer_layout.setContentsMargins(0, 0, 0, 0)
        explorer_layout.setSpacing(0)
        breadcrumb = QHBoxLayout()
        breadcrumb.setContentsMargins(14, 10, 14, 10)
        self.library_label = QLabel("Library")
        self.library_label.setObjectName("sectionTitle")
        self.library_label.setProperty("active", True)
        self.library_label.setToolTip(
            "Root destination selected. Click empty space to return here."
        )
        self.count_label = QLabel("Loading…")
        self.count_label.setObjectName("muted")
        breadcrumb.addWidget(self.library_label)
        breadcrumb.addStretch()
        breadcrumb.addWidget(self.count_label)
        explorer_layout.addLayout(breadcrumb)

        self.tree = LibraryTree()
        self.selection_header = SelectionHeader(self.tree)
        self.selection_header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.tree.setHeader(self.selection_header)
        self.tree.setHeaderLabels(["", "Name", "Type", "Size"])
        self.tree.setTreePosition(1)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tree.header().resizeSection(0, 46)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tree.header().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.selection_header.toggle_requested.connect(self._toggle_all_items)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        self.tree.paths_dropped.connect(self._handle_paths)
        self.tree.empty_area_clicked.connect(self._select_library_root)
        explorer_layout.addWidget(self.tree, 1)
        self.empty_label = QLabel(
            "The library is empty. Add a .bin file or import the ZIP from Drive."
        )
        self.empty_label.setObjectName("emptyState")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()
        explorer_layout.addWidget(self.empty_label)
        layout.addWidget(explorer, 1)

        activity = QFrame()
        activity.setObjectName("activity")
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(14, 10, 14, 10)
        activity_layout.setSpacing(7)
        activity_header = QHBoxLayout()
        self.activity_label = QLabel("Ready")
        self.activity_label.setObjectName("status")
        self.log_toggle = QPushButton("Details")
        self.log_toggle.setObjectName("linkButton")
        self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self._toggle_log)
        activity_header.addWidget(self.activity_label, 1)
        activity_header.addWidget(self.log_toggle)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(135)
        self.log.document().setMaximumBlockCount(1500)
        self.log.hide()
        activity_layout.addLayout(activity_header)
        activity_layout.addWidget(self.progress_bar)
        activity_layout.addWidget(self.log)
        layout.addWidget(activity)
        return page

    def _add_action(
        self,
        label: str,
        icon: QStyle.StandardPixmap,
        callback: Any,
        *,
        primary: bool = False,
    ) -> QAction:
        action = QAction(self.style().standardIcon(icon), label, self)
        action.triggered.connect(callback)
        self.toolbar.add_action(action, primary=primary)
        self._actions.append(action)
        return action

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #0f1318; color: #edf2f6;
                font-family: "Segoe UI Variable", "Segoe UI"; font-size: 13px; }
            QLabel { background: transparent; }
            QLabel#brand { font-size: 22px; font-weight: 700; }
            QLabel#connectionTitle { font-size: 24px; font-weight: 700; }
            QLabel#sectionTitle { font-size: 14px; font-weight: 650;
                color: #99a4af; }
            QLabel#sectionTitle[active="true"] { color: #79e1b8; }
            QLabel#muted { color: #99a4af; }
            QLabel#connectionChip { background: #202832; color: #99a4af;
                border-radius: 11px; padding: 4px 10px; font-weight: 600; }
            QLabel#connectionChip[connected="true"] { background: #18392f;
                color: #79e1b8; }
            QFrame#guide { background: #17233a; border-radius: 10px; }
            QLabel#guideNote { color: #bed8ff; }
            QFrame#explorer { background: #151a20; border: 1px solid #28313b;
                border-radius: 12px; }
            QFrame#activity { background: #151a20; border-radius: 10px; }
            QWidget#actionBar { background: transparent; border: none; }
            QToolButton, QPushButton { background: #222a33; color: #edf2f6;
                border: 1px solid #34404b; border-radius: 7px; padding: 8px 11px; }
            QToolButton:hover, QPushButton:hover { background: #2a3540;
                border-color: #34404b; }
            QToolButton#primaryToolButton { background: #176548; color: #ffffff;
                border: none; font-weight: 700; }
            QToolButton#primaryToolButton:hover { background: #1f7a59; }
            QToolButton:disabled, QPushButton:disabled { color: #65717c;
                background: #171c22; border-color: #252c33; }
            QPushButton#primaryButton { background: #176548; color: #ffffff;
                border: none; font-weight: 700; padding: 10px 16px; }
            QPushButton#primaryButton:hover { background: #1f7a59; }
            QPushButton#linkButton { background: transparent; border: none;
                color: #82b8ff; padding: 5px; }
            QPushButton#linkButton:hover { color: #68a8ff; text-decoration: underline; }
            QTreeWidget, QTextEdit { background: #101419; border: none;
                alternate-background-color: #131920; selection-background-color: #244c40;
                selection-color: #f4fff9; }
            QTreeWidget::item { min-height: 28px; }
            QTreeWidget::item:hover { background: #1b242c; }
            QWidget#selectionCell, QCheckBox { background: transparent; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QHeaderView::section { background: #202832; color: #99a4af;
                border: none; border-bottom: 1px solid #303a44; padding: 8px; }
            QLabel#emptyState { color: #87939e; padding: 30px; }
            QLabel#status { color: #c9d2da; }
            QProgressBar { background: #0d1115; border: none; border-radius: 5px;
                height: 10px; text-align: center; color: transparent; }
            QProgressBar::chunk { background: #58d6a5; border-radius: 5px; }
            QMenu { background: #202832; border: 1px solid #34404b; padding: 5px; }
            QMenu::item { padding: 7px 28px 7px 10px; border-radius: 5px; }
            QMenu::item:selected { background: #2a3540; }
            """
        )

    @Slot()
    def controller_reconnect(self) -> None:
        self.retry_button.hide()
        self.controller.reconnect()

    @Slot(str, str)
    def _on_connection_state(self, state: str, message: str) -> None:
        self.pages.setCurrentIndex(0)
        self.connection_visual.set_connected(state == "connected")
        self.connection_title.setText(
            "Scanning the existing folder structure"
            if state == "searching"
            else "Connection"
        )
        self.connection_body.setText(message)
        self.connection_chip.setText(" Scanning… ")

    @Slot(object)
    def _on_connected(self, info: ConnectionInfo) -> None:
        self._connected = True
        self._device_info = info
        self.connection_visual.set_connected(True)
        self.connection_chip.setProperty("connected", True)
        self.connection_chip.setText(f" ● {info.device_name} ")
        self.connection_chip.style().unpolish(self.connection_chip)
        self.connection_chip.style().polish(self.connection_chip)
        self._update_device_info(info)
        self.pages.setCurrentIndex(1)
        self.retry_button.hide()
        self._update_action_state()

    @Slot(object)
    def _update_device_info(self, info: ConnectionInfo) -> None:
        self._device_info = info
        self.storage_label.setText(
            f"{self._format_size(info.free_size)} available out of "
            f"{self._format_size(info.total_size)} · firmware {info.firmware_version}"
        )

    @Slot(str)
    def _on_disconnected(self, message: str) -> None:
        self._connected = False
        self.taskbar_progress.clear()
        self._device_info = None
        self.connection_chip.setProperty("connected", False)
        self.connection_chip.setText(" Offline ")
        self.connection_chip.style().unpolish(self.connection_chip)
        self.connection_chip.style().polish(self.connection_chip)
        self.storage_label.clear()
        self.pages.setCurrentIndex(0)
        self.connection_visual.set_connected(False)
        self.connection_title.setText("Allmiibo not found")
        self.connection_body.setText(
            message
            + "\n\nAnother attempt will start automatically in a few seconds."
        )
        self.retry_button.show()
        self._update_action_state()

    @Slot(object)
    def _populate_library(self, items: list[RemoteItem]) -> None:
        selected_path = self._selected_path()
        checked_paths = set(self._checked_delete_paths())
        self._items = {item.relative_path: item for item in items}
        self._recompute_protected_paths()
        self.tree.blockSignals(True)
        self.tree.clear()
        self._selection_checkboxes = {}

        root_item = QTreeWidgetItem(["", "amiibo", "Folder", ""])
        root_item.setData(0, Qt.ItemDataRole.UserRole, "")
        root_item.setIcon(1, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        self.tree.addTopLevelItem(root_item)
        root_checkbox = QCheckBox()
        root_checkbox.setEnabled(False)
        root_checkbox.setAccessibleName("amiibo root, cannot be deleted")
        root_checkbox.setToolTip("The amiibo root cannot be deleted.")
        self._set_checkbox_widget(root_item, root_checkbox)
        self._tree_nodes = {"": root_item}

        try:
            for remote in sorted(
                items,
                key=lambda item: (
                    len(PurePosixPath(item.relative_path).parts),
                    not item.is_directory,
                    item.name.casefold(),
                ),
            ):
                self._insert_remote_node(remote, checked_paths)
            selected_item = self._tree_nodes.get(selected_path, root_item)
            self.tree.setCurrentItem(selected_item)
        finally:
            self.tree.blockSignals(False)

        root_item.setExpanded(True)
        self.tree.expandToDepth(1)
        self._update_library_summary()
        self._set_library_root_active(self._selected_path() == "")
        self._update_action_state()

    def _recompute_protected_paths(self) -> None:
        protected_folders = {
            PurePosixPath(item.relative_path)
            for item in self._items.values()
            if item.is_directory and is_protected_directory_path(item.relative_path)
        }
        self._protected_delete_paths = {
            item.relative_path
            for item in self._items.values()
            if item.is_directory
            and any(
                protected == PurePosixPath(item.relative_path)
                or PurePosixPath(item.relative_path) in protected.parents
                for protected in protected_folders
            )
        }

    def _set_checkbox_widget(
        self, tree_item: QTreeWidgetItem, checkbox: QCheckBox
    ) -> None:
        checkbox_cell = QWidget()
        checkbox_cell.setObjectName("selectionCell")
        checkbox_layout = QHBoxLayout(checkbox_cell)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        checkbox_layout.addWidget(checkbox)
        self.tree.setItemWidget(tree_item, 0, checkbox_cell)

    def _insert_remote_node(
        self, remote: RemoteItem, checked_paths: set[str] | None = None
    ) -> QTreeWidgetItem:
        existing = self._tree_nodes.get(remote.relative_path)
        if existing is not None:
            existing.setText(1, remote.name)
            existing.setText(2, "Folder" if remote.is_directory else "Amiibo")
            existing.setText(3, "" if remote.is_directory else self._format_size(remote.size))
            existing.setIcon(
                1,
                self.style().standardIcon(
                    QStyle.StandardPixmap.SP_DirIcon
                    if remote.is_directory
                    else QStyle.StandardPixmap.SP_FileIcon
                ),
            )
            return existing

        relative = PurePosixPath(remote.relative_path)
        parent_key = "" if relative.parent == PurePosixPath(".") else relative.parent.as_posix()
        parent = self._tree_nodes.get(parent_key, self._tree_nodes[""])
        tree_item = QTreeWidgetItem(
            [
                "",
                remote.name,
                "Folder" if remote.is_directory else "Amiibo",
                "" if remote.is_directory else self._format_size(remote.size),
            ]
        )
        tree_item.setData(0, Qt.ItemDataRole.UserRole, remote.relative_path)
        tree_item.setIcon(
            1,
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_DirIcon
                if remote.is_directory
                else QStyle.StandardPixmap.SP_FileIcon
            ),
        )
        sort_key = (not remote.is_directory, remote.name.casefold())
        insert_at = parent.childCount()
        for index in range(parent.childCount()):
            sibling_path = str(parent.child(index).data(0, Qt.ItemDataRole.UserRole))
            sibling = self._items.get(sibling_path)
            if sibling and sort_key < (not sibling.is_directory, sibling.name.casefold()):
                insert_at = index
                break
        parent.insertChild(insert_at, tree_item)

        protected = remote.relative_path in self._protected_delete_paths
        checkbox = QCheckBox()
        checkbox.setChecked(bool(checked_paths and remote.relative_path in checked_paths))
        checkbox.setEnabled(not protected)
        checkbox.setAccessibleName(
            f"{remote.name}, protected folder"
            if protected
            else f"Select {remote.name} for deletion"
        )
        checkbox.setToolTip(
            "This folder is protected because it is fav, data, or one of their parents."
            if protected
            else (
                "Select this folder and its contents for deletion."
                if remote.is_directory
                else "Select this file for deletion."
            )
        )
        checkbox.toggled.connect(lambda _checked: self._update_action_state())
        self._set_checkbox_widget(tree_item, checkbox)
        self._selection_checkboxes[remote.relative_path] = checkbox
        self._tree_nodes[remote.relative_path] = tree_item
        return tree_item

    @Slot(object)
    def _apply_library_delta(self, delta: LibraryDelta) -> None:
        selected_path = self._selected_path()
        checked_paths = set(self._checked_delete_paths())
        self.tree.blockSignals(True)
        try:
            for path in sorted(
                delta.removed,
                key=lambda value: len(PurePosixPath(value).parts),
                reverse=True,
            ):
                tree_item = self._tree_nodes.pop(path, None)
                self._selection_checkboxes.pop(path, None)
                self._items.pop(path, None)
                if tree_item is not None and tree_item.parent() is not None:
                    tree_item.parent().removeChild(tree_item)

            for remote in delta.upserted:
                self._items[remote.relative_path] = remote
            self._recompute_protected_paths()
            for remote in sorted(
                delta.upserted,
                key=lambda item: (
                    len(PurePosixPath(item.relative_path).parts),
                    not item.is_directory,
                    item.name.casefold(),
                ),
            ):
                self._insert_remote_node(remote, checked_paths)

            for path, checkbox in self._selection_checkboxes.items():
                protected = path in self._protected_delete_paths
                if protected:
                    checkbox.setChecked(False)
                checkbox.setEnabled(not protected and self._connected and not self._busy)

            selected_item = self._tree_nodes.get(selected_path)
            if selected_item is None:
                selected_item = self._tree_nodes[""]
            self.tree.setCurrentItem(selected_item)
        finally:
            self.tree.blockSignals(False)

        self._update_library_summary()
        self._set_library_root_active(self._selected_path() == "")
        self._update_action_state()

    def _update_library_summary(self) -> None:
        folders = sum(item.is_directory for item in self._items.values())
        files = len(self._items) - folders
        self.count_label.setText(f"{files} amiibo(s) · {folders} folder(s)")
        self.empty_label.setVisible(not self._items)
        self.tree.setVisible(True)

    @Slot(bool, str)
    def _set_busy(self, busy: bool, label: str) -> None:
        self._busy = busy
        if busy:
            self.activity_label.setText(label)
            self.progress_bar.setRange(0, 0)
            self.progress_bar.show()
            self.taskbar_progress.indeterminate()
        elif self.progress_bar.maximum() == 0:
            self.progress_bar.hide()
            self.activity_label.setText("Ready")
            self.taskbar_progress.clear()
        self._update_action_state()

    @Slot(int, int, str, str)
    def _on_progress(self, current: int, total: int, action: str, path: str) -> None:
        self.progress_bar.setRange(0, total or 1)
        self.progress_bar.setValue(current)
        self.progress_bar.show()
        self.taskbar_progress.set_value(current, total)
        self.activity_label.setText(f"{action.capitalize()} · {PurePosixPath(path).name}")
        self.log.append(f"{current}/{total}  {action:<10}  {path}")
        self._scroll_log_to_end()

    @Slot(str)
    def _on_operation_detail(self, message: str) -> None:
        compact_message = message if len(message) <= 96 else message[:93] + "…"
        self.activity_label.setText(compact_message)
        self.activity_label.setToolTip(message)
        self.log.append(message)
        self._scroll_log_to_end()

    def _scroll_log_to_end(self) -> None:
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot(str, object, float)
    def _on_operation_done(self, command: str, result: Any, elapsed: float) -> None:
        messages = {
            "refresh": "Library refreshed",
            "mkdir": "Folder created",
            "rename": "Item renamed",
        }
        if command == "delete" and isinstance(result, DeleteReport):
            messages[command] = (
                f"{result.removed_files} file(s) and "
                f"{result.removed_folders} folder(s) deleted"
            )
            self.log.append("")
            self.log.append("Deletion result")
            self.log.append(f"Items removed: {result.total}")
            self.log.append(f"Files: {result.removed_files}")
            self.log.append(f"Folders: {result.removed_folders}")
            self.log.append("Processed targets:")
            for path in result.requested:
                self.log.append(f"  • {path}")
        elif command == "upload":
            messages[command] = (
                f"{result.created} added, {result.overwritten} overwritten, "
                f"{result.identical} already present"
            )
            self.log.append("")
            self.log.append("Upload summary")
            self.log.append(f"New files: {result.created}")
            self.log.append(f"Files overwritten: {result.overwritten}")
            self.log.append(f"Identical files skipped: {result.identical}")
            self.log.append(f"Folders created: {result.folders_created}")
        elif command == "import" and isinstance(result, ImportReport):
            sync = result.synchronization
            extraction = result.extraction
            messages[command] = (
                f"Import complete: {sync.created} added, "
                f"{sync.overwritten} overwritten, {sync.identical} identical"
            )
            self.log.append("")
            self.log.append("ZIP preparation summary")
            self.log.append(f"Files extracted: {extraction.extracted}")
            self.log.append(f"Duplicates overwritten: {extraction.overwritten}")
            self.log.append(f"Identical duplicates skipped: {extraction.identical}")
            self.log.append(f"Entries skipped: {extraction.skipped}")
            self.log.append("")
            self.log.append("BLE synchronization summary")
            self.log.append(f"New files: {sync.created}")
            self.log.append(f"Files overwritten: {sync.overwritten}")
            self.log.append(f"Identical files skipped: {sync.identical}")
            self.log.append(f"Folders created: {sync.folders_created}")
            self.log.append("Temporary data deleted automatically.")
        message = messages.get(command, "Operation complete")
        duration = self._format_duration(elapsed)
        self.activity_label.setText(f"{message} · {duration}")
        self.activity_label.setToolTip("")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.show()
        self.taskbar_progress.set_value(100, 100)
        self.log.append(message)
        self.log.append(f"Total duration: {duration}")
        if (
            command == "import"
            or (
                command == "delete"
                and isinstance(result, DeleteReport)
                and len(result.requested) > 1
            )
            or (
                command == "upload"
                and isinstance(result, TransferReport)
                and result.created + result.overwritten + result.identical > 1
            )
        ):
            self._notify_completion("Allmiibo Manager", message)
        QTimer.singleShot(5000, self._settle_activity)

    @Slot(str, str)
    def _on_operation_error(self, message: str, details: str) -> None:
        self.activity_label.setText("Operation failed")
        self.activity_label.setToolTip(message)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        self.taskbar_progress.error()
        self.log.append(details)
        QMessageBox.critical(
            self,
            "Unable to complete the operation",
            message
            + "\n\nRefresh the library before trying again. "
            "Technical details remain available in the log.",
        )
        QTimer.singleShot(5000, self._settle_activity)

    def _settle_activity(self) -> None:
        if not self._busy:
            self.progress_bar.hide()
            self.activity_label.setText("Ready")
            self.taskbar_progress.clear()

    def _notify_completion(self, title: str, message: str) -> None:
        QApplication.beep()
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if self._notification_tray is None:
            self._notification_tray = QSystemTrayIcon(self.windowIcon(), self)
            self._notification_tray.setToolTip("Allmiibo Manager")
        self._notification_tray.show()
        self._notification_tray.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )
        QTimer.singleShot(6000, self._notification_tray.hide)

    def _selected_path(self) -> str:
        item = self.tree.currentItem()
        return str(item.data(0, Qt.ItemDataRole.UserRole)) if item else ""

    def _checked_delete_paths(self) -> list[str]:
        return [
            path
            for path, checkbox in self._selection_checkboxes.items()
            if path not in self._protected_delete_paths
            and checkbox.isChecked()
        ]

    @Slot(bool)
    def _toggle_all_items(self, checked: bool) -> None:
        if not self._connected or self._busy:
            return
        for path, checkbox in self._selection_checkboxes.items():
            if path not in self._protected_delete_paths:
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
        self._update_action_state()

    def _update_global_checkbox(self, enabled: bool) -> None:
        checkboxes = [
            checkbox
            for path, checkbox in self._selection_checkboxes.items()
            if path not in self._protected_delete_paths
        ]
        self.selection_header.checkbox.setEnabled(enabled and bool(checkboxes))
        checked_count = sum(checkbox.isChecked() for checkbox in checkboxes)
        if not checkboxes or checked_count == 0:
            state = Qt.CheckState.Unchecked
        elif checked_count == len(checkboxes):
            state = Qt.CheckState.Checked
        else:
            state = Qt.CheckState.PartiallyChecked
        self.selection_header.checkbox.setCheckState(state)

        for path, checkbox in self._selection_checkboxes.items():
            checkbox.setEnabled(
                enabled and path not in self._protected_delete_paths
            )

    @Slot()
    def _on_tree_selection_changed(self) -> None:
        self._set_library_root_active(not bool(self._selected_path()))
        self._update_action_state()

    @Slot()
    def _select_library_root(self) -> None:
        self.tree.clearSelection()
        self.tree.setCurrentItem(self._tree_nodes.get(""))
        self._set_library_root_active(True)
        self._update_action_state()

    def _set_library_root_active(self, active: bool) -> None:
        self.library_label.setProperty("active", active)
        self.library_label.style().unpolish(self.library_label)
        self.library_label.style().polish(self.library_label)

    def _target_directory(self) -> str:
        selected = self._selected_path()
        if not selected:
            return ""
        remote = self._items.get(selected)
        if remote is not None and remote.is_directory:
            return selected
        parent = PurePosixPath(selected).parent
        return "" if parent == PurePosixPath(".") else parent.as_posix()

    @Slot()
    def _choose_archive(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choose the ZIP downloaded from Google Drive",
            "",
            "ZIP archives (*.zip)",
        )
        if filename:
            self._confirm_import(Path(filename))

    def _confirm_import(self, archive: Path) -> None:
        answer = QMessageBox.question(
            self,
            "Update the entire library",
            f"Import {archive.name}?\n\n"
            "New amiibos will be added, different files overwritten, and identical "
            "files skipped. Your other files will be preserved.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
        )
        if answer == QMessageBox.StandardButton.Ok:
            self.log.clear()
            self.log.append("Import ZIP")
            self.log.append(f"Archive: {archive.name}")
            self.log.append(
                "Rule: add new files, overwrite different files, and skip "
                "identical files."
            )
            self.log.append("Files found only on the device are preserved.")
            self.log.append("Preparing files in Windows temporary storage…")
            self.controller.submit("import", archive)

    @Slot()
    def _choose_files(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "Add amiibos", "", "Amiibo files (*.bin)"
        )
        if filenames:
            self._upload_paths([Path(filename) for filename in filenames])

    @Slot()
    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Add an amiibo folder"
        )
        if folder:
            self._upload_paths([Path(folder)])

    @Slot(object)
    def _handle_paths(self, paths: list[Path]) -> None:
        if not self._connected or self._busy:
            QMessageBox.information(
                self,
                "Allmiibo unavailable",
                "Wait for the connection or the current operation to finish.",
            )
            return
        archives = [path for path in paths if path.suffix.lower() == ".zip"]
        if archives:
            if len(paths) != 1:
                QMessageBox.warning(
                    self,
                    "Ambiguous selection",
                    "Drop only one ZIP archive at a time.",
                )
                return
            self._confirm_import(archives[0])
            return
        self._upload_paths(paths)

    def _upload_paths(self, paths: list[Path]) -> None:
        target = self._target_directory()
        destination = "Library"
        if target:
            destination += " › " + target.replace("/", " › ")
        self.log.clear()
        self.activity_label.setText(f"Preparing upload to {destination}…")
        self.log.append(f"Destination: {destination}")
        self.controller.submit("upload", (paths, target))

    @Slot()
    def _create_folder(self) -> None:
        name, accepted = QInputDialog.getText(
            self, "New folder", "Folder name:"
        )
        if accepted and name.strip():
            target = self._target_directory()
            destination = "Library" if not target else target
            self.log.clear()
            self.log.append("Folder creation")
            self.log.append(f"Parent: {destination}")
            self.log.append(f"Requested name: {name.strip()}")
            self.controller.submit("mkdir", (target, name))

    @Slot()
    def _rename(self) -> None:
        relative = self._selected_path()
        if not relative:
            return
        current = PurePosixPath(relative).name
        is_bin = current.lower().endswith(".bin")
        editable_name = current[:-4] if is_bin else current
        prompt = (
            "File name (.bin extension preserved):"
            if is_bin
            else "New name:"
        )
        name, accepted = QInputDialog.getText(
            self, "Rename", prompt, text=editable_name
        )
        if accepted and name.strip():
            requested_name = name.strip() + ".bin" if is_bin else name.strip()
            if requested_name != current:
                self.log.clear()
                self.log.append("Rename requested")
                self.log.append(f"Source: {relative}")
                self.log.append(f"New name: {requested_name}")
                self.controller.submit("rename", (relative, requested_name))

    @Slot()
    def _delete(self) -> None:
        checked = self._checked_delete_paths()
        selected = self._selected_path()
        targets = checked or ([selected] if selected else [])
        if not targets:
            return
        blocked = [path for path in targets if path in self._protected_delete_paths]
        if blocked:
            QMessageBox.information(
                self,
                "Protected folder",
                "The fav and data folders, and any folder containing them, "
                "can never be deleted.",
            )
            return

        if len(targets) == 1:
            remote = self._items[targets[0]]
            kind = (
                "the folder and all its contents"
                if remote.is_directory
                else "the file"
            )
            question = f'Delete {kind} "{remote.name}"?'
        else:
            names = [self._items[path].name for path in targets]
            preview = "\n".join(f"• {name}" for name in names[:6])
            if len(names) > 6:
                preview += f"\n• … and {len(names) - 6} more"
            question = (
                f"Delete the {len(targets)} selected items?\n"
                "The contents of selected folders will also be deleted."
                f"\n\n{preview}"
            )
        answer = QMessageBox.warning(
            self,
            "Confirm deletion",
            question + "\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.log.clear()
            self.log.append("Deletion requested")
            self.log.append(f"Selected targets: {len(targets)}")
            for path in targets:
                remote = self._items[path]
                kind = "Folder" if remote.is_directory else "File"
                self.log.append(f"  • [{kind}] {path}")
            if any(self._items[path].is_directory for path in targets):
                self.log.append(
                    "Selected folders automatically include all their contents."
                )
            self.controller.submit("delete", targets)

    @Slot()
    def _refresh(self) -> None:
        self.log.clear()
        self.log.append("Full library refresh")
        self.log.append(
            "Every folder will be scanned over BLE. Subsequent actions will use "
            "the updated in-memory index."
        )
        self.controller.submit("refresh")

    @Slot(QPoint)
    def _show_context_menu(self, point: Any) -> None:
        if self._busy or not self._connected:
            return
        item = self.tree.itemAt(point)
        self.tree.clearSelection()
        self.tree.setCurrentItem(item)
        menu = QMenu(self)
        add_action = menu.addAction("Add here…")
        new_folder_action = menu.addAction("New folder…")
        rename_action = menu.addAction("Rename…")
        delete_action = menu.addAction("Delete…")
        if item is None:
            rename_action.setEnabled(False)
            delete_action.setEnabled(False)
        else:
            relative = self._selected_path()
            remote = self._items.get(relative)
            rename_action.setEnabled(
                remote is not None
                and not (
                    remote.is_directory
                    and is_protected_directory_path(remote.relative_path)
                )
            )
            delete_action.setEnabled(
                bool(relative) and relative not in self._protected_delete_paths
            )
        action = menu.exec(self.tree.viewport().mapToGlobal(point))
        if action == add_action:
            self._choose_files()
        elif action == new_folder_action:
            self._create_folder()
        elif action == rename_action:
            self._rename()
        elif action == delete_action:
            self._delete()

    @Slot()
    def _update_action_state(self) -> None:
        enabled = self._connected and not self._busy
        selected = self._selected_path()
        remote = self._items.get(selected)
        checked_count = len(self._checked_delete_paths())
        selected_deletable = bool(
            selected and selected not in self._protected_delete_paths
        )
        selected_renameable = bool(
            remote
            and not (
                remote.is_directory
                and is_protected_directory_path(remote.relative_path)
            )
        )
        for action in (
            self.import_action,
            self.add_action,
            self.folder_action,
            self.new_folder_action,
            self.refresh_action,
        ):
            action.setEnabled(enabled)
        self.rename_action.setEnabled(enabled and selected_renameable)
        self.delete_action.setText(
            f"Delete ({checked_count})" if checked_count else "Delete"
        )
        self.delete_action.setEnabled(
            enabled and (checked_count > 0 or selected_deletable)
        )
        self._update_global_checkbox(enabled)
        self.toolbar.reflow()

    @Slot(bool)
    def _toggle_log(self, visible: bool) -> None:
        self.log.setVisible(visible)
        self.log_toggle.setText("Hide" if visible else "Details")

    @Slot()
    def _open_library_source(self) -> None:
        QDesktopServices.openUrl(QUrl(AMIIBO_LIBRARY_URL))

    @Slot()
    def _open_dfu_update(self) -> None:
        QDesktopServices.openUrl(QUrl(DFU_UPDATE_URL))

    @Slot()
    def _open_firmware_releases(self) -> None:
        QDesktopServices.openUrl(QUrl(FIRMWARE_RELEASES_URL))

    @staticmethod
    def _format_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KiB", "MiB", "GiB"):
            if value < 1024 or unit == "GiB":
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return f"{size} B"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total = max(0, round(seconds))
        if total < 60:
            return f"{total} s"
        minutes, remaining = divmod(total, 60)
        if minutes < 60:
            return f"{minutes} min {remaining:02d} s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours} h {minutes:02d} min"

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        paths = LibraryTree._local_paths(event)
        if paths and all(
            path.is_dir() or path.suffix.lower() in {".bin", ".zip"} for path in paths
        ):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = LibraryTree._local_paths(event)
        if paths:
            self._handle_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event: Any) -> None:
        connection_page_visible = self.pages.currentIndex() == 0
        if self._busy and not connection_page_visible:
            QMessageBox.information(
                self,
                "Operation in progress",
                "Wait for the operation to finish before closing the application.",
            )
            event.ignore()
            return
        self.controller.shutdown()
        if not self.controller.wait(5000):
            event.ignore()
            QMessageBox.warning(
                self,
                "Disconnecting",
                "The Bluetooth connection is closing. Try again in a few seconds.",
            )
            return
        self.taskbar_progress.close()
        event.accept()


def main() -> int:
    if "--self-test" in sys.argv:
        os._exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("Allmiibo Manager")
    app.setOrganizationName("Allmiibo")
    if APP_ICON_PATH.is_file():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
