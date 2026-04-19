# ui/process_browser_widget.py
#
# Widget displaying saved custom processes in a tree view, grouped by folder.
# Embedded as an extra tab in the main dock.

import os

from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QMessageBox, QFileDialog, QMenu, QInputDialog,
)
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon, QFont

from ..core.process_runner import list_processes, load_process, delete_process


class ProcessBrowserWidget(QWidget):
    """
    Tree-view panel listing all saved .aiprocess.json files.
    Emits `run_requested(process_dict)` when the user clicks Run.
    """

    run_requested = pyqtSignal(object)   # emits process_dict

    def __init__(self, base_folder_getter, parent=None):
        """
        base_folder_getter: callable() → str — returns the current base folder path
        """
        super().__init__(parent)
        self._get_base = base_folder_getter
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
        lbl = QLabel("<b>Traitements personnalisés</b>")
        header_row.addWidget(lbl)
        header_row.addStretch()

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(28, 28)
        refresh_btn.setToolTip("Actualiser la liste")
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)

        folder_btn = QPushButton("📁")
        folder_btn.setFixedSize(28, 28)
        folder_btn.setToolTip("Changer le dossier de base")
        folder_btn.clicked.connect(self._change_base_folder)
        header_row.addWidget(folder_btn)

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
        self._run_btn = QPushButton("Ouvrir / Lancer")
        self._run_btn.clicked.connect(self._on_run_clicked)
        btn_row.addWidget(self._run_btn)

        self._del_btn = QPushButton("Supprimer")
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
        """Reload processes from disk and rebuild the tree."""
        self._tree.clear()
        base = self._get_base()
        self._base_lbl.setText(f"Dossier : {base}")

        processes = list_processes(base)

        if not processes:
            placeholder = QTreeWidgetItem(["Aucun traitement enregistré"])
            placeholder.setFlags(Qt.NoItemFlags)
            self._tree.addTopLevelItem(placeholder)
            return

        # Group by folder
        folders: dict[str, list[dict]] = {}
        for p in processes:
            folder = p.get("folder") or "General"
            folders.setdefault(folder, []).append(p)

        for folder_name in sorted(folders.keys()):
            folder_item = QTreeWidgetItem([f"📁  {folder_name}"])
            folder_item.setFont(0, QFont("", -1, QFont.Bold))
            folder_item.setData(0, Qt.UserRole, None)
            self._tree.addTopLevelItem(folder_item)

            for proc in folders[folder_name]:
                child = QTreeWidgetItem([f"⚙  {proc['name']}"])
                child.setData(0, Qt.UserRole, proc["path"])
                child.setToolTip(0, proc.get("description", "") or proc["path"])
                folder_item.addChild(child)

            folder_item.setExpanded(True)

    # ──────────────────────────────────────────────────────────
    # Actions
    # ──────────────────────────────────────────────────────────

    def _on_run_clicked(self):
        item = self._tree.currentItem()
        if not item:
            return
        self._open_item(item)

    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        self._open_item(item)

    def _open_item(self, item: QTreeWidgetItem):
        path = item.data(0, Qt.UserRole)
        if not path or not os.path.isfile(path):
            return
        try:
            process_dict = load_process(path)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le traitement :\n{e}")
            return
        self.run_requested.emit(process_dict)

    def _on_delete_clicked(self):
        item = self._tree.currentItem()
        if not item:
            return
        path = item.data(0, Qt.UserRole)
        if not path or not os.path.isfile(path):
            return
        name = item.text(0).replace("⚙  ", "")
        reply = QMessageBox.question(
            self, "Supprimer",
            f"Supprimer le traitement « {name} » ?\n{path}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                delete_process(path)
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer :\n{e}")

    def _change_base_folder(self):
        current = self._get_base()
        new_path = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier de base des traitements", current
        )
        if new_path and new_path != current:
            # Signal the parent (main dock) to update the setting
            self.parent_set_base_folder(new_path)

    def parent_set_base_folder(self, path: str):
        """Override hook — connected by the parent widget to persist the setting."""
        pass

    def _show_context_menu(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        menu = QMenu(self)
        run_action = menu.addAction("Ouvrir / Lancer")
        del_action = menu.addAction("Supprimer")
        action = menu.exec_(self._tree.viewport().mapToGlobal(pos))
        if action == run_action:
            self._open_item(item)
        elif action == del_action:
            self._on_delete_clicked()
