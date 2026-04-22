# ui/process_browser_widget.py
#
# Widget displaying saved custom processes in a tree view, grouped by folder.
# Embedded as an extra tab in the main dock.

import os
import shutil

from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QMessageBox, QFileDialog, QMenu, QInputDialog, QDialog,
)
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon, QFont

from ..core.process_runner import load_process, delete_process
from ..utils.translation import get_translations

_ROLE_FILE = Qt.UserRole          # str path for process files, None for folders
_ROLE_DIR  = Qt.UserRole + 1      # str abs path for folder items, None for files


class ProcessBrowserWidget(QWidget):
    """
    Tree-view panel listing all saved .aiprocess.json files.
    Reflects the actual filesystem directory structure with collapsible folders.
    Emits `run_requested(process_dict)` when the user clicks Run.
    """

    run_requested = pyqtSignal(object)   # emits process_dict

    def __init__(self, base_folder_getter, language: str = "fr", parent=None):
        """
        base_folder_getter: callable() → str — returns the current base folder path
        language          : "fr" or "en" for UI labels
        """
        super().__init__(parent)
        self._get_base = base_folder_getter
        self._t = get_translations(language)
        self._language = language
        self._build_ui()
        self.refresh()

    # ──────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Header
        header_row = QHBoxLayout()
        lbl = QLabel(f"<b>{self._t['process_browser_header']}</b>")
        header_row.addWidget(lbl)
        header_row.addStretch()

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(28, 28)
        refresh_btn.setToolTip(self._t['process_refresh_tooltip'])
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)

        folder_btn = QPushButton("📁")
        folder_btn.setFixedSize(28, 28)
        folder_btn.setToolTip(self._t['process_change_folder_tooltip'])
        folder_btn.clicked.connect(self._change_base_folder)
        header_row.addWidget(folder_btn)

        new_folder_btn = QPushButton("📁+")
        new_folder_btn.setFixedSize(34, 28)
        new_folder_btn.setToolTip(self._t['process_context_new_folder'])
        new_folder_btn.clicked.connect(self._create_folder_in_selected_or_root)
        header_row.addWidget(new_folder_btn)

        layout.addLayout(header_row)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._tree)

        # Action buttons
        btn_row = QHBoxLayout()
        self._run_btn = QPushButton(self._t['process_context_run'])
        self._run_btn.clicked.connect(self._on_run_clicked)
        btn_row.addWidget(self._run_btn)

        self._del_btn = QPushButton(self._t['process_context_delete'])
        self._del_btn.clicked.connect(self._on_delete_clicked)
        btn_row.addWidget(self._del_btn)

        layout.addLayout(btn_row)

        # Base folder label
        self._base_lbl = QLabel()
        self._base_lbl.setStyleSheet("color: #888; font-size: 10px;")
        self._base_lbl.setWordWrap(True)
        layout.addWidget(self._base_lbl)

    # ──────────────────────────────────────────────────────────
    # Data loading
    # ──────────────────────────────────────────────────────────

    def refresh(self):
        """Reload processes from disk and rebuild the tree from the filesystem structure."""
        self._tree.clear()
        base = self._get_base()
        self._base_lbl.setText(f"Dossier : {base}")

        if not os.path.isdir(base):
            placeholder = QTreeWidgetItem([self._t['process_none_saved']])
            placeholder.setFlags(Qt.NoItemFlags)
            self._tree.addTopLevelItem(placeholder)
            return

        has_any = self._build_dir_tree(base, self._tree, base)

        if not has_any:
            placeholder = QTreeWidgetItem([self._t['process_none_saved']])
            placeholder.setFlags(Qt.NoItemFlags)
            self._tree.addTopLevelItem(placeholder)

    def _build_dir_tree(self, dir_path: str, parent, base: str) -> bool:
        """
        Recursively build tree items for dir_path under parent (tree or folder item).
        Returns True if at least one process file was found anywhere in the subtree.
        """
        try:
            entries = sorted(os.scandir(dir_path), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return False

        has_any = False
        for entry in entries:
            if entry.is_dir():
                folder_item = QTreeWidgetItem([f"📁  {entry.name}"])
                folder_item.setFont(0, QFont("", -1, QFont.Bold))
                folder_item.setData(0, _ROLE_FILE, None)
                folder_item.setData(0, _ROLE_DIR, entry.path)
                if isinstance(parent, QTreeWidget):
                    parent.addTopLevelItem(folder_item)
                else:
                    parent.addChild(folder_item)
                subtree_has = self._build_dir_tree(entry.path, folder_item, base)
                if subtree_has:
                    has_any = True
                else:
                    # Keep empty folder visible so user can see/use it
                    pass

            elif entry.name.endswith(".aiprocess.json"):
                try:
                    p = load_process(entry.path)
                    name = p.get("name", entry.name)
                    desc = p.get("description", "")
                except Exception:
                    name = entry.name
                    desc = ""

                child = QTreeWidgetItem([f"⚙  {name}"])
                child.setData(0, _ROLE_FILE, entry.path)
                child.setData(0, _ROLE_DIR, None)
                child.setToolTip(0, desc or entry.path)
                if isinstance(parent, QTreeWidget):
                    parent.addTopLevelItem(child)
                else:
                    parent.addChild(child)
                has_any = True

        return has_any

    # ──────────────────────────────────────────────────────────
    # Actions — process files
    # ──────────────────────────────────────────────────────────

    def _on_run_clicked(self):
        item = self._tree.currentItem()
        if not item:
            return
        self._open_item(item)

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        # Folder items: toggle expand/collapse
        if item.data(0, _ROLE_DIR) is not None:
            item.setExpanded(not item.isExpanded())
            return
        self._open_item(item)

    def _open_item(self, item: QTreeWidgetItem):
        path = item.data(0, _ROLE_FILE)
        if not path or not os.path.isfile(path):
            return
        try:
            process_dict = load_process(path)
        except Exception as e:
            QMessageBox.critical(self, self._t['error'], f"{self._t['process_load_error']}\n{e}")
            return
        self.run_requested.emit(process_dict)

    def _on_delete_clicked(self):
        item = self._tree.currentItem()
        if not item:
            return
        path = item.data(0, _ROLE_FILE)
        if not path or not os.path.isfile(path):
            return
        name = item.text(0).replace("⚙  ", "")
        reply = QMessageBox.question(
            self, self._t['process_context_delete'],
            self._t['process_delete_confirm_msg'].format(name=name, path=path),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                delete_process(path)
                self.refresh()
            except Exception:
                QMessageBox.critical(self, self._t['error'], self._t['process_delete_error'])

    def _edit_item(self, item: QTreeWidgetItem):
        path = item.data(0, _ROLE_FILE)
        if not path or not os.path.isfile(path):
            return
        try:
            process_dict = load_process(path)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le traitement :\n{e}")
            return
        from .process_save_dialog import ProcessSaveDialog
        dlg = ProcessSaveDialog(
            process_dict, self._get_base(),
            source_path=path, language=self._language, parent=self,
        )
        if dlg.exec_() == QDialog.Accepted:
            self.refresh()

    # ──────────────────────────────────────────────────────────
    # Actions — folders
    # ──────────────────────────────────────────────────────────

    def _create_folder_in_selected_or_root(self):
        """Create a new subfolder inside the selected folder, or at root if none selected."""
        item = self._tree.currentItem()
        if item is not None:
            dir_path = item.data(0, _ROLE_DIR)
            if dir_path is None:
                # A process file is selected — use its parent directory
                parent_item = item.parent()
                if parent_item is not None:
                    dir_path = parent_item.data(0, _ROLE_DIR)
                else:
                    dir_path = self._get_base()
        else:
            dir_path = self._get_base()

        self._create_subfolder(dir_path)

    def _create_subfolder(self, parent_dir: str):
        name, ok = QInputDialog.getText(
            self,
            self._t['process_new_folder_title'],
            self._t['process_new_folder_prompt'],
        )
        if not ok or not name.strip():
            return
        safe = name.strip().replace("/", "_").replace("\\", "_")
        new_dir = os.path.join(parent_dir, safe)
        try:
            os.makedirs(new_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, self._t['error'], str(e))
            return
        self.refresh()

    def _delete_folder(self, item: QTreeWidgetItem):
        dir_path = item.data(0, _ROLE_DIR)
        if not dir_path or not os.path.isdir(dir_path):
            return
        name = item.text(0).replace("📁  ", "")
        reply = QMessageBox.question(
            self, self._t['process_context_delete_folder'],
            self._t['process_delete_folder_confirm'].format(name=name),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                shutil.rmtree(dir_path)
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, self._t['error'], str(e))

    # ──────────────────────────────────────────────────────────
    # Context menu
    # ──────────────────────────────────────────────────────────

    def _show_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        is_folder = item.data(0, _ROLE_DIR) is not None

        if is_folder:
            new_sub_action = menu.addAction(self._t["process_context_new_folder"])
            menu.addSeparator()
            del_folder_action = menu.addAction(self._t["process_context_delete_folder"])
            action = menu.exec_(self._tree.viewport().mapToGlobal(pos))
            if action == new_sub_action:
                self._create_subfolder(item.data(0, _ROLE_DIR))
            elif action == del_folder_action:
                self._delete_folder(item)
        else:
            file_path = item.data(0, _ROLE_FILE)
            if not file_path:
                return
            run_action  = menu.addAction(self._t["process_context_run"])
            edit_action = menu.addAction(self._t["process_context_edit"])
            menu.addSeparator()
            del_action  = menu.addAction(self._t["process_context_delete"])
            action = menu.exec_(self._tree.viewport().mapToGlobal(pos))
            if action == run_action:
                self._open_item(item)
            elif action == edit_action:
                self._edit_item(item)
            elif action == del_action:
                self._on_delete_clicked()

    # ──────────────────────────────────────────────────────────
    # Base folder
    # ──────────────────────────────────────────────────────────

    def _change_base_folder(self):
        current = self._get_base()
        new_path = QFileDialog.getExistingDirectory(
            self, self._t['process_folder_dest'], current
        )
        if new_path and new_path != current:
            self.parent_set_base_folder(new_path)

    def parent_set_base_folder(self, _path: str):
        """Override hook — connected by the parent widget to persist the setting."""
        pass
