import asyncio
import os
import unittest
from threading import Event
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog

from allmiibo_gui import DeviceController, LibraryDelta, MainWindow
from allmiibo_manager import (
    AllmiiboManager,
    ConnectionInfo,
    DeleteReport,
    RemoteItem,
    TransferReport,
)


class LibraryInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MainWindow(start_controller=False)
        self.window._on_connected(ConnectionInfo("Allmiibo", "2.1.0", 2_000, 1_000))
        self.window._populate_library(
            [
                RemoteItem("Collection", "Collection", 0, True),
                RemoteItem("Collection/data", "data", 0, True),
                RemoteItem("fav", "fav", 0, True),
                RemoteItem("Zelda", "Zelda", 0, True),
                RemoteItem("Zelda/Link.bin", "Link.bin", 540, False),
                RemoteItem("Smash Bros", "Smash Bros", 0, True),
            ]
        )

    def tearDown(self) -> None:
        self.window.deleteLater()
        self.app.processEvents()

    def test_folders_and_bin_files_can_be_checked_except_protected_folders(self) -> None:
        self.assertFalse(self.window._selection_checkboxes["fav"].isEnabled())
        self.assertFalse(self.window._selection_checkboxes["Collection"].isEnabled())
        self.assertTrue(self.window._selection_checkboxes["Zelda"].isEnabled())
        self.assertTrue(self.window._selection_checkboxes["Zelda/Link.bin"].isEnabled())

        self.window._selection_checkboxes["Zelda/Link.bin"].setChecked(True)

        self.assertEqual(self.window._checked_delete_paths(), ["Zelda/Link.bin"])
        self.assertEqual(self.window.delete_action.text(), "Delete (1)")
        self.assertEqual(
            self.window.selection_header.checkbox.checkState(),
            Qt.CheckState.PartiallyChecked,
        )

    def test_global_checkbox_toggles_every_unprotected_item(self) -> None:
        self.assertEqual(self.window.tree.treePosition(), 1)

        self.window.selection_header.checkbox.click()

        self.assertEqual(
            set(self.window._checked_delete_paths()),
            {"Zelda", "Zelda/Link.bin", "Smash Bros"},
        )
        self.assertFalse(self.window._selection_checkboxes["fav"].isChecked())
        self.assertFalse(self.window._selection_checkboxes["Collection"].isChecked())
        self.assertEqual(
            self.window.selection_header.checkbox.checkState(),
            Qt.CheckState.Checked,
        )

        self.window.selection_header.checkbox.click()

        self.assertEqual(self.window._checked_delete_paths(), [])
        self.assertEqual(
            self.window.selection_header.checkbox.checkState(),
            Qt.CheckState.Unchecked,
        )

    def test_selecting_library_root_clears_the_previous_destination(self) -> None:
        root = self.window._tree_nodes[""]
        self.assertEqual(root.text(1), "amiibo")
        self.assertIs(self.window._tree_nodes["Zelda"].parent(), root)

        self.window.tree.setCurrentItem(self.window._tree_nodes["Zelda"])
        self.assertEqual(self.window._target_directory(), "Zelda")
        self.assertFalse(self.window.library_label.property("active"))

        self.window._select_library_root()

        self.assertEqual(self.window._selected_path(), "")
        self.assertEqual(self.window._target_directory(), "")
        self.assertTrue(self.window.library_label.property("active"))

    def test_incremental_delta_updates_only_changed_tree_items(self) -> None:
        unchanged_node = self.window._tree_nodes["Zelda"]

        self.window._apply_library_delta(
            LibraryDelta(
                upserted=(
                    RemoteItem("New", "New", 0, True),
                    RemoteItem("New/Fox.bin", "Fox.bin", 540, False),
                ),
                removed=("Smash Bros",),
            )
        )

        self.assertIs(self.window._tree_nodes["Zelda"], unchanged_node)
        self.assertNotIn("Smash Bros", self.window._tree_nodes)
        self.assertIs(
            self.window._tree_nodes["New/Fox.bin"].parent(),
            self.window._tree_nodes["New"],
        )
        self.assertEqual(self.window.count_label.text(), "2 amiibo(s) · 5 folder(s)")

    def test_bin_rename_dialog_hides_and_restores_the_extension(self) -> None:
        self.window.tree.setCurrentItem(self.window._tree_nodes["Zelda/Link.bin"])
        submissions: list[tuple[str, object]] = []
        self.window.controller.submit = lambda command, payload=None: submissions.append(
            (command, payload)
        )

        with patch.object(
            QInputDialog,
            "getText",
            return_value=("Hero", True),
        ) as dialog:
            self.window._rename()

        self.assertEqual(dialog.call_args.kwargs["text"], "Link")
        self.assertIn(".bin extension preserved", dialog.call_args.args[2])
        self.assertEqual(
            submissions,
            [("rename", ("Zelda/Link.bin", "Hero.bin"))],
        )

    def test_compact_action_bar_uses_an_inline_more_button(self) -> None:
        self.window.toolbar.resize(1080, self.window.toolbar.sizeHint().height())
        self.window.toolbar.reflow()
        wide_visible_count = sum(
            not button.isHidden() for _, button in self.window.toolbar.entries
        )

        self.window.toolbar.resize(520, self.window.toolbar.sizeHint().height())
        self.window.toolbar.reflow()
        self.app.processEvents()
        visible_buttons = [
            button for _, button in self.window.toolbar.entries if not button.isHidden()
        ]

        self.assertFalse(self.window.toolbar.more_button.isHidden())
        self.assertLess(len(visible_buttons), wide_visible_count)
        self.assertGreater(len(self.window.toolbar.more_menu.actions()), 0)
        self.assertLessEqual(
            self.window.toolbar.more_button.x()
            - (visible_buttons[-1].x() + visible_buttons[-1].width()),
            self.window.toolbar.layout().spacing() + 1,
        )
        down_icon = self.window.toolbar.more_button.icon().cacheKey()
        self.window.toolbar._set_more_expanded(True)
        self.assertNotEqual(
            self.window.toolbar.more_button.icon().cacheKey(), down_icon
        )
        self.assertGreater(self.window.toolbar.entries[0][1].iconSize().width(), 16)

    def test_group_upload_completion_notifies_and_reports_elapsed_time(self) -> None:
        notifications: list[tuple[str, str]] = []
        self.window._notify_completion = lambda title, message: notifications.append(
            (title, message)
        )

        self.window._on_operation_done(
            "upload",
            TransferReport(created=2, overwritten=1),
            90,
        )

        self.assertEqual(len(notifications), 1)
        self.assertIn("Total duration: 1 min 30 s", self.window.log.toPlainText())
        self.assertIn("1 min 30 s", self.window.activity_label.text())

    def test_single_delete_stays_silent_but_group_delete_notifies(self) -> None:
        notifications: list[tuple[str, str]] = []
        self.window._notify_completion = lambda title, message: notifications.append(
            (title, message)
        )

        self.window._on_operation_done(
            "delete", DeleteReport(("Zelda/Link.bin",), 1, 0), 1
        )
        self.assertEqual(notifications, [])

        self.window._on_operation_done(
            "delete", DeleteReport(("Zelda", "Smash Bros"), 0, 2), 2
        )
        self.assertEqual(len(notifications), 1)

    def test_connection_page_can_close_while_ble_is_busy(self) -> None:
        self.window.pages.setCurrentIndex(0)
        self.window._busy = True

        with patch("allmiibo_gui.QMessageBox.information") as information:
            closed = self.window.close()

        self.assertTrue(closed)
        information.assert_not_called()

    def test_operation_details_progress_without_overflowing_status(self) -> None:
        message = "Reading folder: " + "Very-long-folder/" * 10

        self.window._on_operation_detail(message)

        self.assertTrue(self.window.activity_label.text().endswith("…"))
        self.assertEqual(self.window.activity_label.toolTip(), message)
        self.assertIn(message, self.window.log.toPlainText())


class DeviceControllerShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_shutdown_cancels_an_active_ble_search(self) -> None:
        search_started = Event()

        async def slow_connect(_manager: AllmiiboManager) -> ConnectionInfo:
            search_started.set()
            await asyncio.sleep(60)
            raise AssertionError("The BLE scan should have been cancelled.")

        controller = DeviceController()
        with patch.object(AllmiiboManager, "connect", slow_connect):
            controller.start()
            self.assertTrue(search_started.wait(2))
            controller.shutdown()
            self.assertTrue(controller.wait(2000))


if __name__ == "__main__":
    unittest.main()
