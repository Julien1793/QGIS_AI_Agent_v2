# ui/process_save_dialog.py
#
# Dialog shown after an agent run to let the user save the recorded steps
# as a reusable custom process (.aiprocess.json).
#
# Features:
#   - Name + description fields
#   - Folder picker (free text, creates the folder automatically)
#   - Variable table: detected params with editable label + type selector
#   - Per-step code editor for run_pyqgis_code steps
#   - Preview of the final JSON

import json
import os

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QPlainTextEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QComboBox, QTabWidget,
    QWidget, QHeaderView, QMessageBox, QFileDialog, QSplitter,
    QDialogButtonBox,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont

try:
    from qgis.gui import QgsCodeEditorPython
    _HAS_CODE_EDITOR = True
except Exception:
    _HAS_CODE_EDITOR = False

from ..core.process_recorder import ProcessRecorder
from ..core.process_runner import save_process


_VAR_TYPES = ["layer", "field", "file", "crs", "value", "code"]
_VAR_TYPE_LABELS = {
    "layer": "Couche",
    "field": "Champ",
    "file": "Fichier",
    "crs": "SCR",
    "value": "Valeur",
    "code": "Code PyQGIS",
}


class ProcessSaveDialog(QDialog):
    """
    Modal dialog to review, edit and save a recorded agent run as a
    reusable custom process.
    """

    def __init__(self, recorder: ProcessRecorder, base_folder: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enregistrer comme traitement personnalisé")
        self.setMinimumSize(700, 560)
        self.recorder = recorder
        self.base_folder = base_folder

        # Detect variables from the recorder
        self._variables = recorder.detect_variables()
        self._steps = list(recorder.steps)

        self._build_ui()
        self._populate_variables()
        self._populate_steps()

    # ──────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        tabs = QTabWidget()
        root.addWidget(tabs)

        tabs.addTab(self._build_info_tab(), "Informations")
        tabs.addTab(self._build_variables_tab(), "Variables")
        tabs.addTab(self._build_steps_tab(), "Étapes / Code")
        tabs.addTab(self._build_preview_tab(), "Aperçu JSON")

        self._tabs = tabs
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Standard OK / Cancel buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _build_info_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Ex : Reprojection + Export")
        form.addRow("Nom du traitement :", self._name_edit)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Description courte (optionnelle)…")
        self._desc_edit.setMaximumHeight(80)
        form.addRow("Description :", self._desc_edit)

        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Ex : Vecteur/Géotraitement")
        folder_layout.addWidget(self._folder_edit)
        folder_browse_btn = QPushButton("Parcourir…")
        folder_browse_btn.setFixedWidth(90)
        folder_browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(folder_browse_btn)
        form.addRow("Dossier projet :", folder_row)

        info = QLabel(
            f"<i>Les traitements sont enregistrés dans :<br>"
            f"<code>{self.base_folder}</code></i>"
        )
        info.setWordWrap(True)
        form.addRow("", info)

        return w

    def _build_variables_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(6)

        note = QLabel(
            "Variables détectées automatiquement.\n"
            "Vous pouvez modifier les labels et les types."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self._var_table = QTableWidget(0, 4)
        self._var_table.setHorizontalHeaderLabels(["ID", "Label utilisateur", "Type", "Valeur par défaut"])
        self._var_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._var_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._var_table.setColumnWidth(0, 110)
        self._var_table.setColumnWidth(2, 110)
        self._var_table.verticalHeader().setVisible(False)
        layout.addWidget(self._var_table)

        add_btn = QPushButton("+ Ajouter une variable")
        add_btn.clicked.connect(self._add_variable_row)
        del_btn = QPushButton("Supprimer la sélection")
        del_btn.clicked.connect(self._delete_selected_variable)
        btn_row = QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return w

    def _build_steps_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        note = QLabel(
            "Étapes enregistrées. Pour les blocs de code PyQGIS, vous pouvez éditer "
            "le code directement (il remplacera la valeur par défaut de la variable)."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self._steps_container = QVBoxLayout()
        scroll_widget = QWidget()
        scroll_widget.setLayout(self._steps_container)

        from qgis.PyQt.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        self._code_editors: dict[int, object] = {}  # step_idx → editor widget
        return w

    def _build_preview_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self._preview_edit = QPlainTextEdit()
        self._preview_edit.setReadOnly(True)
        font = QFont("Courier New", 9)
        self._preview_edit.setFont(font)
        layout.addWidget(self._preview_edit)
        return w

    # ──────────────────────────────────────────────────────────
    # Populate
    # ──────────────────────────────────────────────────────────

    def _populate_variables(self):
        self._var_table.setRowCount(0)
        for var in self._variables:
            self._append_variable_row(var)

    def _append_variable_row(self, var: dict):
        row = self._var_table.rowCount()
        self._var_table.insertRow(row)

        id_item = QTableWidgetItem(var.get("id", ""))
        id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
        id_item.setData(Qt.UserRole, var)
        self._var_table.setItem(row, 0, id_item)

        label_item = QTableWidgetItem(var.get("label", ""))
        self._var_table.setItem(row, 1, label_item)

        type_combo = QComboBox()
        for vt in _VAR_TYPES:
            type_combo.addItem(_VAR_TYPE_LABELS.get(vt, vt), vt)
        current_type = var.get("type", "value")
        idx = _VAR_TYPES.index(current_type) if current_type in _VAR_TYPES else 4
        type_combo.setCurrentIndex(idx)
        self._var_table.setCellWidget(row, 2, type_combo)

        default_item = QTableWidgetItem(str(var.get("default", "")))
        self._var_table.setItem(row, 3, default_item)

    def _populate_steps(self):
        # Clear previous widgets
        while self._steps_container.count():
            item = self._steps_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._code_editors.clear()

        for idx, step in enumerate(self._steps):
            tool = step.get("tool", "")
            params = step.get("params", {})

            group = QWidget()
            group.setStyleSheet("QWidget { border: 1px solid #ccc; border-radius: 4px; }")
            g_layout = QVBoxLayout(group)
            g_layout.setContentsMargins(8, 6, 8, 6)
            g_layout.setSpacing(4)

            header = QLabel(f"<b>Étape {idx + 1}</b> — <code>{tool}</code>")
            g_layout.addWidget(header)

            if tool == "run_pyqgis_code" and "code" in step:
                lbl = QLabel("Code PyQGIS (éditable) :")
                g_layout.addWidget(lbl)
                if _HAS_CODE_EDITOR:
                    editor = QgsCodeEditorPython()
                    editor.setText(step["code"])
                    editor.setMinimumHeight(150)
                else:
                    editor = QPlainTextEdit(step["code"])
                    editor.setFont(QFont("Courier New", 9))
                    editor.setMinimumHeight(150)
                g_layout.addWidget(editor)
                self._code_editors[idx] = editor
            else:
                # Show params as key: value lines
                params_text = "\n".join(
                    f"  {k}: {v}" for k, v in params.items()
                    if k not in ("iface", "executor")
                )
                params_lbl = QLabel(f"<pre style='margin:0'>{params_text}</pre>")
                params_lbl.setWordWrap(True)
                g_layout.addWidget(params_lbl)

            self._steps_container.addWidget(group)

        self._steps_container.addStretch()

    # ──────────────────────────────────────────────────────────
    # Slots
    # ──────────────────────────────────────────────────────────

    def _on_tab_changed(self, index: int):
        # Refresh preview when the JSON tab is shown
        if self._tabs.tabText(index) == "Aperçu JSON":
            self._refresh_preview()

    def _refresh_preview(self):
        try:
            d = self._build_dict()
            self._preview_edit.setPlainText(json.dumps(d, ensure_ascii=False, indent=2))
        except Exception as e:
            self._preview_edit.setPlainText(f"Erreur : {e}")

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choisir un dossier de base", self.base_folder
        )
        if path:
            # Store the relative sub-folder name
            rel = os.path.relpath(path, self.base_folder)
            if rel.startswith(".."):
                # Folder is outside base — use the leaf name
                rel = os.path.basename(path)
            self._folder_edit.setText(rel)

    def _add_variable_row(self):
        new_id = f"v_value_{self._var_table.rowCount()}"
        var = {"id": new_id, "label": "Nouvelle variable", "type": "value", "default": "", "refs": []}
        self._variables.append(var)
        self._append_variable_row(var)

    def _delete_selected_variable(self):
        rows = sorted(set(i.row() for i in self._var_table.selectedItems()), reverse=True)
        for row in rows:
            self._var_table.removeRow(row)

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nom manquant", "Veuillez saisir un nom pour le traitement.")
            return

        folder = self._folder_edit.text().strip() or "General"

        # Sync edited code back into steps
        for step_idx, editor in self._code_editors.items():
            if step_idx < len(self._steps):
                if _HAS_CODE_EDITOR:
                    self._steps[step_idx]["code"] = editor.text()
                else:
                    self._steps[step_idx]["code"] = editor.toPlainText()

        variables = self._collect_variables()

        try:
            process_dict = self.recorder.build_process_dict(
                name=name,
                description=self._desc_edit.toPlainText().strip(),
                folder=folder,
                variables=variables,
            )
            # Override steps with (potentially code-edited) steps
            process_dict["steps"] = self._rebuild_templated_steps(variables)
            filepath = save_process(process_dict, self.base_folder)
            QMessageBox.information(
                self, "Enregistré",
                f"Traitement enregistré :\n{filepath}"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer :\n{e}")

    # ──────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────

    def _collect_variables(self) -> list[dict]:
        """Read back variable rows from the table into a list of dicts."""
        variables = []
        for row in range(self._var_table.rowCount()):
            id_item = self._var_table.item(row, 0)
            if not id_item:
                continue
            orig = id_item.data(Qt.UserRole) or {}
            var_id = id_item.text()
            label_item = self._var_table.item(row, 1)
            label = label_item.text() if label_item else var_id
            type_combo = self._var_table.cellWidget(row, 2)
            var_type = type_combo.currentData() if type_combo else "value"
            default_item = self._var_table.item(row, 3)
            default = default_item.text() if default_item else ""
            variables.append({
                "id": var_id,
                "label": label,
                "type": var_type,
                "default": default,
                "refs": orig.get("refs", []),
            })
        return variables

    def _rebuild_templated_steps(self, variables: list[dict]) -> list[dict]:
        """Rebuild the steps list with {v_xxx} placeholders."""
        ref_map: dict[tuple, str] = {}
        for var in variables:
            for ref in var.get("refs", []):
                ref_map[tuple(ref)] = var["id"]

        templated = []
        for step_idx, step in enumerate(self._steps):
            new_params = {}
            for key, value in step.get("params", {}).items():
                ref = (step_idx, key)
                if ref in ref_map:
                    new_params[key] = "{" + ref_map[ref] + "}"
                else:
                    new_params[key] = value

            ts = {"tool": step["tool"], "params": new_params}

            if step["tool"] == "run_pyqgis_code" and "code" in step:
                ref = (step_idx, "code")
                if ref in ref_map:
                    ts["code"] = "{" + ref_map[ref] + "}"
                else:
                    ts["code"] = step["code"]

            templated.append(ts)
        return templated

    def _build_dict(self) -> dict:
        variables = self._collect_variables()
        steps = self._rebuild_templated_steps(variables)
        return {
            "version": 1,
            "name": self._name_edit.text().strip() or "Sans nom",
            "description": self._desc_edit.toPlainText().strip(),
            "folder": self._folder_edit.text().strip() or "General",
            "variables": [{k: v for k, v in var.items() if k != "refs"} for var in variables],
            "steps": steps,
        }
