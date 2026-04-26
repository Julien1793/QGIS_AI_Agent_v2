# ui/process_run_dialog.py
#
# Dialog shown when the user wants to run a saved .aiprocess.json.
# Displays the process description and a dynamic form to fill variable values,
# then executes the steps via ProcessRunner and streams progress in the dialog.

import os
import threading

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QPushButton, QLabel,
    QTextEdit, QPlainTextEdit, QWidget, QDialogButtonBox,
    QScrollArea, QProgressBar, QFileDialog,
    QDoubleSpinBox, QCheckBox, QColorDialog,
)
from qgis.PyQt.QtCore import Qt, QThread, QObject, pyqtSignal, pyqtSlot
from qgis.PyQt.QtGui import QFont, QColor

try:
    from qgis.core import QgsProject
    _HAS_QGIS = True
except Exception:
    _HAS_QGIS = False

try:
    from qgis.gui import QgsCodeEditorPython, QgsProjectionSelectionWidget
    _HAS_CRS_WIDGET = True
except Exception:
    _HAS_CRS_WIDGET = False

from ..core.process_runner import ProcessRunner, load_process


# ──────────────────────────────────────────────────────────────
# Background worker
# ──────────────────────────────────────────────────────────────

class _RunWorker(QObject):
    progress = pyqtSignal(dict)            # step event
    tool_request = pyqtSignal(str, object) # (tool_name, args) → main thread
    finished = pyqtSignal()

    def __init__(self, runner: ProcessRunner, process_dict: dict, values: dict):
        super().__init__()
        self._runner = runner
        self._process = process_dict
        self._values = values
        self._tool_event = threading.Event()
        self._tool_result = None

    def receive_tool_result(self, result: dict):
        """Called from the main thread to post the tool result back."""
        self._tool_result = result
        self._tool_event.set()

    def run(self):
        def tool_executor(tool_name, args):
            self._tool_event.clear()
            self._tool_result = None
            self.tool_request.emit(tool_name, dict(args))
            if not self._tool_event.wait(timeout=120):
                return {"success": False, "tool": tool_name,
                        "error": "Timeout — outil sans réponse après 120 s"}
            return self._tool_result

        try:
            for event in self._runner.run(self._process, self._values,
                                          tool_executor=tool_executor):
                self.progress.emit(event)
        except Exception as e:
            self.progress.emit({"type": "tool_error", "text": f"Erreur : {e}", "data": {}})
        self.finished.emit()


# ──────────────────────────────────────────────────────────────
# Main dialog
# ──────────────────────────────────────────────────────────────

class ProcessRunDialog(QDialog):
    """
    Dialog to fill variable values and execute a saved custom process.
    """

    def __init__(self, process_dict: dict, agent_loop, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Traitement : {process_dict.get('name', 'Sans nom')}")
        self.setMinimumSize(520, 480)
        self.process_dict = process_dict
        self.agent_loop = agent_loop
        self._input_widgets: dict[str, QWidget] = {}  # var_id → input widget
        self._thread = None
        self._worker = None

        self._build_ui()

    # ──────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ── Header ──
        name_lbl = QLabel(f"<h3>{self.process_dict.get('name', '')}</h3>")
        root.addWidget(name_lbl)

        desc = self.process_dict.get("description", "").strip()
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #666; font-style: italic;")
            root.addWidget(desc_lbl)

        steps = self.process_dict.get("steps", [])
        info_lbl = QLabel(f"<small>{len(steps)} étape(s) enregistrée(s)</small>")
        root.addWidget(info_lbl)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #ddd;")
        root.addWidget(sep)

        # ── Variable form ──
        variables = self.process_dict.get("variables", [])
        if variables:
            form_widget = QWidget()
            self._form = QFormLayout(form_widget)
            self._form.setSpacing(4)

            current_step = None
            for var in variables:
                step_num = var.get("step_num")
                step_tool = var.get("step_tool", "")

                # Insert a step separator when we enter a new step block
                if step_num is not None and step_num != current_step:
                    current_step = step_num
                    short_tool = step_tool.replace("set_label_", "lbl·").replace("set_", "")
                    sep_lbl = QLabel(
                        f"<small style='color:#4a90d9;'>— Étape {step_num} : "
                        f"<b>{short_tool}</b> —</small>"
                    )
                    sep_lbl.setAlignment(Qt.AlignCenter)
                    sep_lbl.setContentsMargins(0, 6, 0, 2)
                    self._form.addRow(sep_lbl)

                widget = self._make_input_widget(var)
                self._input_widgets[var["id"]] = widget
                self._form.addRow(var.get("label", var["id"]) + " :", widget)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(form_widget)
            scroll.setMaximumHeight(300)
            root.addWidget(scroll)
        else:
            root.addWidget(QLabel("<i>Aucune variable — le traitement s'exécute tel quel.</i>"))

        # ── Progress log ──
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(160)
        self._log.setFont(QFont("Courier New", 9))
        self._log.setVisible(False)
        root.addWidget(self._log)

        # ── Buttons ──
        self._run_btn = QPushButton("Lancer")
        self._run_btn.setDefault(True)
        self._run_btn.clicked.connect(self._on_run)

        self._close_btn = QPushButton("Fermer")
        self._close_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._run_btn)
        btn_row.addWidget(self._close_btn)
        root.addLayout(btn_row)

    def _make_input_widget(self, var: dict) -> QWidget:
        var_type = var.get("type", "value")
        default = str(var.get("default", ""))

        if var_type == "layer":
            widget = QComboBox()
            if _HAS_QGIS:
                for layer in QgsProject.instance().mapLayers().values():
                    widget.addItem(layer.name(), layer.name())
            # Pre-select default if present
            idx = widget.findData(default)
            if idx >= 0:
                widget.setCurrentIndex(idx)
            elif default:
                widget.insertItem(0, default, default)
                widget.setCurrentIndex(0)
            return widget

        if var_type == "field":
            # Simple text input — field names depend on which layer is chosen,
            # which may not be known yet.
            widget = QLineEdit(default)
            widget.setPlaceholderText("Nom du champ")
            return widget

        if var_type == "crs":
            if _HAS_CRS_WIDGET:
                from qgis.core import QgsCoordinateReferenceSystem
                widget = QgsProjectionSelectionWidget()
                if default:
                    crs = QgsCoordinateReferenceSystem(default)
                    if crs.isValid():
                        widget.setCrs(crs)
                return widget
            else:
                widget = QLineEdit(default)
                widget.setPlaceholderText("EPSG:2154")
                return widget

        if var_type == "file":
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            le = QLineEdit(default)
            le.setPlaceholderText("Chemin vers le fichier…")
            row.addWidget(le)
            btn = QPushButton("…")
            btn.setFixedWidth(30)
            btn.clicked.connect(lambda: self._browse_file(le))
            row.addWidget(btn)
            container._line_edit = le  # keep reference for value retrieval
            return container

        if var_type == "color":
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            btn = QPushButton()
            btn.setFixedHeight(28)
            qc = QColor(default) if default and QColor(default).isValid() else QColor("#000000")
            btn._color = qc
            btn.setStyleSheet(f"background-color: {qc.name()}; border: 1px solid #888;")

            lbl_hex = QLabel(qc.name())
            lbl_hex.setStyleSheet("color: #666; font-size: 11px;")

            def _pick(_checked=False, b=btn, lbl=lbl_hex):
                c = QColorDialog.getColor(b._color, self, "Choisir une couleur")
                if c.isValid():
                    b._color = c
                    b.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #888;")
                    lbl.setText(c.name())

            btn.clicked.connect(_pick)
            row.addWidget(btn)
            row.addWidget(lbl_hex)
            container._btn = btn
            return container

        if var_type == "number":
            spin = QDoubleSpinBox()
            spin.setRange(-1e9, 1e9)
            spin.setDecimals(4)
            spin.setStepType(QDoubleSpinBox.AdaptiveDecimalStepType)
            try:
                spin.setValue(float(default))
            except (ValueError, TypeError):
                spin.setValue(0.0)
            return spin

        if var_type == "boolean":
            chk = QCheckBox()
            chk.setChecked(str(default).strip().lower() in ("true", "1", "yes"))
            return chk

        if var_type == "code":
            try:
                from qgis.gui import QgsCodeEditorPython
                editor = QgsCodeEditorPython()
                editor.setText(default)
                editor.setMinimumHeight(120)
                return editor
            except Exception:
                editor = QPlainTextEdit(default)
                editor.setFont(QFont("Courier New", 9))
                editor.setMinimumHeight(120)
                return editor

        # Default: plain text
        widget = QLineEdit(default)
        return widget

    # ──────────────────────────────────────────────────────────
    # Slots
    # ──────────────────────────────────────────────────────────

    def _browse_file(self, line_edit: QLineEdit):
        path, _ = QFileDialog.getSaveFileName(self, "Choisir un fichier de sortie")
        if path:
            line_edit.setText(path)

    def _on_run(self):
        values = self._collect_values()
        self._log.setVisible(True)
        self._log.clear()
        self._run_btn.setEnabled(False)

        runner = ProcessRunner(self.agent_loop)
        self._worker = _RunWorker(runner, self.process_dict, values)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        self._worker.progress.connect(self._on_progress, Qt.QueuedConnection)
        self._worker.finished.connect(self._on_finished, Qt.QueuedConnection)
        self._worker.tool_request.connect(self._on_tool_request, Qt.QueuedConnection)
        self._thread.started.connect(self._worker.run)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    @pyqtSlot(str, object)
    def _on_tool_request(self, tool_name: str, args: object):
        """Execute a QGIS tool on the main thread and return the result to the worker."""
        result = self.agent_loop._execute_tool(tool_name, args)
        if self._worker:
            self._worker.receive_tool_result(result)

    def _on_progress(self, event: dict):
        etype = event.get("type", "")
        text = event.get("text", "")
        color_map = {
            "start":     "#555",
            "tool_call": "#1a6fbb",
            "tool_result": "#2a8a2a",
            "tool_error":  "#cc2222",
            "aborted":     "#cc2222",
            "done":        "#2a8a2a",
        }
        color = color_map.get(etype, "#333")
        self._log.append(f'<span style="color:{color}">{text}</span>')

    def _on_finished(self):
        self._run_btn.setEnabled(True)
        self._thread.quit()
        # Change close button to "OK" after run
        self._close_btn.setText("OK")
        self._close_btn.clicked.disconnect()
        self._close_btn.clicked.connect(self.accept)

    # ──────────────────────────────────────────────────────────
    # Value collection
    # ──────────────────────────────────────────────────────────

    def _collect_values(self) -> dict:
        values = {}
        for var in self.process_dict.get("variables", []):
            var_id = var["id"]
            var_type = var.get("type", "value")
            widget = self._input_widgets.get(var_id)
            if widget is None:
                values[var_id] = var.get("default", "")
                continue

            if var_type == "layer" and isinstance(widget, QComboBox):
                values[var_id] = widget.currentData() or widget.currentText()
            elif var_type == "crs" and _HAS_CRS_WIDGET and hasattr(widget, "crs"):
                values[var_id] = widget.crs().authid()
            elif var_type == "file" and hasattr(widget, "_line_edit"):
                values[var_id] = widget._line_edit.text()
            elif var_type == "color" and hasattr(widget, "_btn"):
                values[var_id] = widget._btn._color.name()
            elif var_type == "number" and isinstance(widget, QDoubleSpinBox):
                values[var_id] = widget.value()
            elif var_type == "boolean" and isinstance(widget, QCheckBox):
                values[var_id] = widget.isChecked()
            elif var_type == "code":
                try:
                    from qgis.gui import QgsCodeEditorPython
                    if isinstance(widget, QgsCodeEditorPython):
                        values[var_id] = widget.text()
                    else:
                        values[var_id] = widget.toPlainText()
                except Exception:
                    values[var_id] = widget.toPlainText()
            elif isinstance(widget, QLineEdit):
                values[var_id] = widget.text()
            elif isinstance(widget, QComboBox):
                values[var_id] = widget.currentData() or widget.currentText()
            else:
                values[var_id] = var.get("default", "")

        return values
