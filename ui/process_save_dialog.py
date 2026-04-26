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
#   - Edit mode: load an existing .aiprocess.json for modification
#   - Save / Save As buttons

import json
import os
import re

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QPlainTextEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QComboBox, QTabWidget,
    QWidget, QHeaderView, QMessageBox, QFileDialog, QScrollArea,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont

try:
    from qgis.gui import QgsCodeEditorPython
    _HAS_CODE_EDITOR = True
except Exception:
    _HAS_CODE_EDITOR = False

from ..core.process_recorder import ProcessRecorder
from ..core.process_runner import save_process, overwrite_process
from ..utils.translation import get_translations


_VAR_TYPES = ["layer", "field", "file", "crs", "color", "number", "boolean", "value", "code"]
_VAR_TYPE_KEYS = {
    "layer":   "process_vartype_layer",
    "field":   "process_vartype_field",
    "file":    "process_vartype_file",
    "crs":     "process_vartype_crs",
    "color":   "process_vartype_color",
    "number":  "process_vartype_number",
    "boolean": "process_vartype_boolean",
    "value":   "process_vartype_value",
    "code":    "process_vartype_code",
}


class ProcessSaveDialog(QDialog):
    """
    Modal dialog to review, edit and save a recorded agent run as a
    reusable custom process.
    """

    def __init__(self, recorder_or_dict, base_folder: str,
                 source_path: str = None, language: str = "fr", parent=None):
        """
        recorder_or_dict : ProcessRecorder (new process) OR dict (editing an existing process).
        source_path      : path of the existing .aiprocess.json to overwrite on save (edit mode).
        language         : "fr" or "en" for all UI labels.
        """
        super().__init__(parent)
        self.setMinimumSize(700, 560)
        self.base_folder = base_folder
        self._source_path = source_path
        self._code_var_map: dict = {}  # step_idx → var_id, populated in edit mode
        self._t = get_translations(language)

        if isinstance(recorder_or_dict, dict):
            self.recorder = None
            self.setWindowTitle(self._t["process_save_dlg_title_edit"])
            self._load_from_process_dict(recorder_or_dict)
        else:
            self.recorder = recorder_or_dict
            self.setWindowTitle(self._t["process_save_dlg_title_new"])
            self._variables = recorder_or_dict.detect_variables()
            self._steps = list(recorder_or_dict.steps)

        self._build_ui()
        self._populate_variables()
        self._populate_steps()

        # Pre-fill info fields when editing an existing process
        if isinstance(recorder_or_dict, dict):
            self._name_edit.setText(recorder_or_dict.get("name", ""))
            self._desc_edit.setPlainText(recorder_or_dict.get("description", ""))
            self._folder_edit.setText(recorder_or_dict.get("folder", ""))

    def _load_from_process_dict(self, process_dict: dict):
        """
        Reconstruct self._steps and self._variables from an existing .aiprocess.json dict.
        Variable refs are rebuilt by scanning step params for {v_xxx} placeholders.
        For run_pyqgis_code steps the {v_xxx} code reference is resolved to the actual
        code string for display in the editor.
        """
        raw_vars = process_dict.get("variables", [])
        var_by_id = {v["id"]: dict(v, refs=[]) for v in raw_vars}
        self._variables = list(var_by_id.values())

        self._steps = []
        self._code_var_map = {}

        for step_idx, raw_step in enumerate(process_dict.get("steps", [])):
            step = {"tool": raw_step["tool"], "params": dict(raw_step.get("params", {}))}

            # Reconstruct refs from params
            for key, value in step["params"].items():
                if isinstance(value, str):
                    m = re.match(r'^\{(v_[a-zA-Z0-9_]+)\}$', value)
                    if m and m.group(1) in var_by_id:
                        var_by_id[m.group(1)]["refs"].append((step_idx, key))

            # Handle the code field: resolve {v_xxx} → actual code for display
            if "code" in raw_step:
                code_val = raw_step["code"]
                if isinstance(code_val, str):
                    m = re.match(r'^\{(v_[a-zA-Z0-9_]+)\}$', code_val)
                    if m and m.group(1) in var_by_id:
                        var_id = m.group(1)
                        self._code_var_map[step_idx] = var_id
                        var_by_id[var_id]["refs"].append((step_idx, "code"))
                        code_val = var_by_id[var_id].get("default", code_val)
                step["code"] = code_val

            self._steps.append(step)

        # Derive step_tool / step_num from refs for variables that don't have
        # them saved (processes recorded with older code versions).
        for var in self._variables:
            if var.get("refs") and not var.get("step_tool"):
                si, _pk = var["refs"][0]
                if si < len(self._steps):
                    var["step_tool"] = self._steps[si].get("tool", "")
                    var["step_num"] = si + 1

    # ──────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────

    def _build_ui(self):
        t = self._t
        root = QVBoxLayout(self)
        root.setSpacing(8)

        tabs = QTabWidget()
        root.addWidget(tabs)

        tabs.addTab(self._build_info_tab(),      t["process_tab_info"])
        tabs.addTab(self._build_variables_tab(), t["process_tab_variables"])
        tabs.addTab(self._build_steps_tab(),     t["process_tab_steps"])
        tabs.addTab(self._build_preview_tab(),   t["process_tab_preview"])

        self._tabs = tabs
        self._preview_tab_index = 3
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._save_btn = QPushButton(t["process_btn_save"])
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        self._saveas_btn = QPushButton(t["process_btn_save_as"])
        self._saveas_btn.clicked.connect(self._on_save_as)
        btn_row.addWidget(self._saveas_btn)

        cancel_btn = QPushButton(t["process_btn_cancel"])
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        root.addLayout(btn_row)

    def _build_info_tab(self) -> QWidget:
        t = self._t
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(t["process_name_placeholder"])
        form.addRow(t["process_name_label"], self._name_edit)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText(t["process_desc_placeholder"])
        self._desc_edit.setMaximumHeight(80)
        form.addRow(t["process_desc_label"], self._desc_edit)

        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText(t["process_folder_placeholder"])
        folder_layout.addWidget(self._folder_edit)
        folder_browse_btn = QPushButton(t["process_folder_browse_btn"])
        folder_browse_btn.setFixedWidth(90)
        folder_browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(folder_browse_btn)
        form.addRow(t["process_folder_label"], folder_row)

        info = QLabel(
            f"<i>{t['process_folder_info']}<br>"
            f"<code>{self.base_folder}</code></i>"
        )
        info.setWordWrap(True)
        form.addRow("", info)

        return w

    def _build_variables_tab(self) -> QWidget:
        t = self._t
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(6)

        note = QLabel(t["process_vars_note"])
        note.setWordWrap(True)
        layout.addWidget(note)

        self._var_table = QTableWidget(0, 5)
        self._var_table.setHorizontalHeaderLabels([
            t["process_vars_col_step"],
            t["process_vars_col_id"],
            t["process_vars_col_label"],
            t["process_vars_col_type"],
            t["process_vars_col_default"],
        ])
        self._var_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._var_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._var_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._var_table.setColumnWidth(1, 100)
        self._var_table.setColumnWidth(3, 100)
        self._var_table.verticalHeader().setVisible(False)
        self._var_table.setWordWrap(False)
        layout.addWidget(self._var_table)

        add_btn = QPushButton(t["process_vars_add_btn"])
        add_btn.clicked.connect(self._add_variable_row)
        del_btn = QPushButton(t["process_vars_del_btn"])
        del_btn.clicked.connect(self._delete_selected_variable)
        btn_row = QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return w

    def _build_steps_tab(self) -> QWidget:
        t = self._t
        w = QWidget()
        layout = QVBoxLayout(w)

        note = QLabel(t["process_steps_note"])
        note.setWordWrap(True)
        layout.addWidget(note)

        self._steps_container = QVBoxLayout()
        scroll_widget = QWidget()
        scroll_widget.setLayout(self._steps_container)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        self._code_editors: dict = {}  # step_idx → editor widget
        return w

    def _build_preview_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self._preview_edit = QPlainTextEdit()
        self._preview_edit.setReadOnly(True)
        self._preview_edit.setFont(QFont("Courier New", 9))
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
        t = self._t
        row = self._var_table.rowCount()
        self._var_table.insertRow(row)

        # Col 0 — step context: "N · tool_name (param)"
        refs = var.get("refs", [])
        if refs:
            step_idx, param_key = refs[0]
            tool_name = ""
            if step_idx < len(self._steps):
                tool_name = self._steps[step_idx].get("tool", "")
            short_tool = tool_name.replace("set_label_", "lbl·").replace("set_", "")
            step_text = f"{step_idx + 1} · {short_tool}"
            if len(refs) > 1:
                step_text += f" (+{len(refs) - 1})"
            tooltip = "\n".join(
                f"Étape {si + 1} — {self._steps[si].get('tool', '?')} [{pk}]"
                for si, pk in refs
                if si < len(self._steps)
            )
        else:
            step_text = "—"
            tooltip = ""
        step_item = QTableWidgetItem(step_text)
        step_item.setFlags(step_item.flags() & ~Qt.ItemIsEditable)
        step_item.setToolTip(tooltip)
        from qgis.PyQt.QtGui import QColor as _QColor
        step_item.setForeground(_QColor("#4a90d9"))
        self._var_table.setItem(row, 0, step_item)

        # Col 1 — variable ID (read-only, carries the full var dict)
        id_item = QTableWidgetItem(var.get("id", ""))
        id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
        id_item.setData(Qt.UserRole, var)
        self._var_table.setItem(row, 1, id_item)

        # Col 2 — editable user label
        label_item = QTableWidgetItem(var.get("label", ""))
        self._var_table.setItem(row, 2, label_item)

        # Col 3 — type selector
        type_combo = QComboBox()
        for vt in _VAR_TYPES:
            type_combo.addItem(t.get(_VAR_TYPE_KEYS.get(vt, vt), vt), vt)
        current_type = var.get("type", "value")
        idx = _VAR_TYPES.index(current_type) if current_type in _VAR_TYPES else _VAR_TYPES.index("value")
        type_combo.setCurrentIndex(idx)
        self._var_table.setCellWidget(row, 3, type_combo)

        # Col 4 — default value
        default_item = QTableWidgetItem(str(var.get("default", "")))
        self._var_table.setItem(row, 4, default_item)

    def _populate_steps(self):
        t = self._t
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

            # Header row: step label + delete button
            header_row = QHBoxLayout()
            header_row.setContentsMargins(0, 0, 0, 0)
            header = QLabel(
                f"<b>{t['process_step_header'].format(num=idx + 1)}</b>"
                f" — <code>{tool}</code>"
            )
            header_row.addWidget(header, stretch=1)
            del_btn = QPushButton("×")
            del_btn.setFixedSize(22, 22)
            del_btn.setToolTip(t["process_step_delete_tooltip"])
            del_btn.setStyleSheet(
                "QPushButton { color: #c00; font-weight: bold; border: 1px solid #c00; "
                "border-radius: 3px; background: transparent; }"
                "QPushButton:hover { background: #fdd; }"
            )
            del_btn.clicked.connect(lambda _checked, i=idx: self._delete_step(i))
            header_row.addWidget(del_btn)
            g_layout.addLayout(header_row)

            if tool == "run_pyqgis_code" and "code" in step:
                lbl = QLabel(t["process_step_code_label"])
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
        if index == self._preview_tab_index:
            self._refresh_preview()

    def _refresh_preview(self):
        try:
            d = self._build_dict()
            self._preview_edit.setPlainText(json.dumps(d, ensure_ascii=False, indent=2))
        except Exception as e:
            self._preview_edit.setPlainText(
                f"{self._t['process_error_title']} : {e}"
            )

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, self._t["process_browse_dlg_title"], self.base_folder
        )
        if path:
            rel = os.path.relpath(path, self.base_folder)
            if rel.startswith(".."):
                rel = os.path.basename(path)
            self._folder_edit.setText(rel)

    def _add_variable_row(self):
        new_id = f"v_value_{self._var_table.rowCount()}"
        var = {
            "id": new_id,
            "label": self._t["process_new_variable_label"],
            "type": "value",
            "default": "",
            "refs": [],
        }
        self._variables.append(var)
        self._append_variable_row(var)

    def _delete_selected_variable(self):
        rows = sorted(set(i.row() for i in self._var_table.selectedItems()), reverse=True)
        for row in rows:
            self._var_table.removeRow(row)

    def _delete_step(self, step_idx: int):
        """Remove a step, shift variable refs, and auto-remove orphaned variables."""
        self._sync_code_editors()

        for var in self._variables:
            new_refs = []
            for (si, pk) in var.get("refs", []):
                if si == step_idx:
                    continue
                elif si > step_idx:
                    new_refs.append((si - 1, pk))
                else:
                    new_refs.append((si, pk))
            var["refs"] = new_refs

        del self._steps[step_idx]

        # Remove variables whose refs are now empty (belonged only to this step)
        before = len(self._variables)
        self._variables = [v for v in self._variables if v.get("refs")]
        removed = before - len(self._variables)

        self._populate_steps()
        self._populate_variables()

        if removed:
            from qgis.PyQt.QtWidgets import QMessageBox
            msg = self._t.get(
                "process_step_deleted_vars",
                "{n} variable(s) supprimée(s) car elles n'étaient utilisées que par cette étape.",
            ).replace("{n}", str(removed))
            QMessageBox.information(
                self,
                self._t.get("process_step_deleted_title", "Étape supprimée"),
                msg,
            )

    def _sync_code_editors(self):
        """Flush code editor content back into steps and their variable defaults in the table."""
        for step_idx, editor in self._code_editors.items():
            if step_idx >= len(self._steps):
                continue
            code = editor.text() if _HAS_CODE_EDITOR else editor.toPlainText()
            self._steps[step_idx]["code"] = code
            # Also update the variable default cell so _collect_variables picks up the edit.
            for row in range(self._var_table.rowCount()):
                id_item = self._var_table.item(row, 1)  # col 1 = ID
                if not id_item:
                    continue
                orig = id_item.data(Qt.UserRole) or {}
                if any(si == step_idx and pk == "code"
                       for si, pk in orig.get("refs", [])):
                    default_item = self._var_table.item(row, 4)  # col 4 = default
                    if default_item:
                        default_item.setText(code)
                    break

    def _on_save(self):
        process_dict = self._build_current_dict()
        if process_dict is None:
            return
        t = self._t
        try:
            if self._source_path:
                overwrite_process(process_dict, self._source_path)
                QMessageBox.information(
                    self, t["process_saved_title"],
                    t["process_saved_updated"].format(path=self._source_path),
                )
            else:
                filepath = save_process(process_dict, self.base_folder)
                QMessageBox.information(
                    self, t["process_saved_title"],
                    t["process_saved_new"].format(path=filepath),
                )
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self, t["process_error_title"],
                t["process_error_save"].format(error=e),
            )

    def _on_save_as(self):
        """Always create a new file, regardless of whether we are in edit mode."""
        process_dict = self._build_current_dict()
        if process_dict is None:
            return
        t = self._t
        try:
            filepath = save_process(process_dict, self.base_folder)
            QMessageBox.information(
                self, t["process_saved_title"],
                t["process_saved_new"].format(path=filepath),
            )
            self._source_path = filepath
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self, t["process_error_title"],
                t["process_error_save"].format(error=e),
            )

    def _build_current_dict(self) -> dict:
        """Validate inputs, sync editors and return the ready-to-save process dict, or None."""
        t = self._t
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(
                self, t["process_missing_name_title"], t["process_missing_name_msg"]
            )
            return None

        folder = self._folder_edit.text().strip() or "General"
        self._sync_code_editors()
        variables = self._collect_variables()
        steps = self._rebuild_templated_steps(variables)
        return {
            "version": 1,
            "name": name,
            "description": self._desc_edit.toPlainText().strip(),
            "folder": folder,
            "variables": [{k: v for k, v in var.items() if k != "refs"} for var in variables],
            "steps": steps,
        }

    # ──────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────

    def _collect_variables(self) -> list:
        """Read back variable rows from the table into a list of dicts."""
        variables = []
        for row in range(self._var_table.rowCount()):
            id_item = self._var_table.item(row, 1)   # col 1 = ID
            if not id_item:
                continue
            orig = id_item.data(Qt.UserRole) or {}
            var_id = id_item.text()
            label_item = self._var_table.item(row, 2)   # col 2 = label
            label = label_item.text() if label_item else var_id
            type_combo = self._var_table.cellWidget(row, 3)  # col 3 = type
            var_type = type_combo.currentData() if type_combo else "value"
            default_item = self._var_table.item(row, 4)  # col 4 = default
            default = default_item.text() if default_item else ""
            variables.append({
                "id": var_id,
                "label": label,
                "type": var_type,
                "default": default,
                "refs": orig.get("refs", []),
            })
        return variables

    def _rebuild_templated_steps(self, variables: list) -> list:
        """Rebuild the steps list with {v_xxx} placeholders."""
        ref_map = {}
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
            "name": self._name_edit.text().strip() or self._t["process_fallback_name"],
            "description": self._desc_edit.toPlainText().strip(),
            "folder": self._folder_edit.text().strip() or "General",
            "variables": [{k: v for k, v in var.items() if k != "refs"} for var in variables],
            "steps": steps,
        }
