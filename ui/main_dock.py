# ui/main_dock.py

import os
import re
import uuid
import html
from qgis.PyQt.QtWidgets import (QSplitter,
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QTabWidget, QMessageBox, QLabel, QTextBrowser,
    QDialog, QPlainTextEdit, QDialogButtonBox, QApplication,
    QFormLayout, QScrollArea, QLineEdit, QSpinBox, QDoubleSpinBox,
    QCheckBox, QColorDialog,
)
from qgis.PyQt.QtCore import Qt, QCoreApplication, QRect, QSize, QThread, pyqtSlot
from qgis.PyQt.QtGui import QTextCursor, QPixmap, QPainter, QTextFormat, QMovie, QColor

try:
    from qgis.gui import QgsCodeEditorPython
    HAS_QGIS_CODE_EDITOR = True
except Exception:
    HAS_QGIS_CODE_EDITOR = False

from .options_dialog import OptionsDialog
from ..core.agent import AIAgent
from ..core.executor import CodeExecutor
from ..utils.translation import get_translations
from ..core.project_indexer import build_project_snapshot, snapshot_to_json
from ..core.agent_loop import AgentLoop
from ..core.process_recorder import ProcessRecorder
from .agent_steps_widget import AgentStepsRenderer
from .process_save_dialog import ProcessSaveDialog
from .process_run_dialog import ProcessRunDialog
from .process_browser_widget import ProcessBrowserWidget
from .chat_theme import (
    CHAT_CSS,
    wrap_user, wrap_assistant, wrap_system,
    wrap_error, wrap_warning, wrap_success, wrap_info,
    wrap_code,
)
from .workers import ChatWorker, AgentWorker, StreamWorker
from .markdown_renderer import (
    looks_like_html as _looks_like_html,
    pass_through_html_with_md_classes as _pass_through_html_with_md_classes,
    normalize_text as _normalize_text_fn,
    render_markdownish_chat as _render_markdownish_chat_fn,
    md_table_block_to_html as _md_table_block_to_html_fn,
)


class _LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor
    def sizeHint(self):
        return QSize(self._editor.lineNumberAreaWidth(), 0)
    def paintEvent(self, event):
        self._editor._lineNumberAreaPaintEvent(event)

class _CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lineNumberArea = _LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()

    def lineNumberAreaWidth(self):
        digits = len(str(max(1, self.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance('9') * digits

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self._lineNumberArea.scroll(0, dy)
        else:
            self._lineNumberArea.update(0, rect.y(), self._lineNumberArea.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def _lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self._lineNumberArea)
        painter.fillRect(event.rect(), self.palette().base())
        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.setPen(self.palette().mid().color())
                painter.drawText(0, top, self._lineNumberArea.width()-4, self.fontMetrics().height(),
                                 Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1

    def highlightCurrentLine(self):
        extra = QTextEdit.ExtraSelection()
        lineColor = self.palette().alternateBase()
        extra.format.setBackground(lineColor)
        extra.format.setProperty(QTextFormat.FullWidthSelection, True)
        extra.cursor = self.textCursor()
        extra.cursor.clearSelection()
        self.setExtraSelections([extra])


class CodeReviewDialog(QDialog):
    def __init__(self, code_text: str, t: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t.get("review_title", "Vérifier et exécuter"))
        self.setMinimumSize(700, 500)
        vbox = QVBoxLayout(self)

        label = QLabel(t.get("code_preview", "Aperçu du code (modifiable avant exécution)"))
        vbox.addWidget(label)

        if HAS_QGIS_CODE_EDITOR:
            self.editor = QgsCodeEditorPython(self)
            try:
                self.editor.setLineNumbersVisible(True)
            except Exception:
                pass
            try:
                self.editor.setFoldingVisible(True)
            except Exception:
                pass
            try:
                self.editor.setAutoCompletionEnabled(True)
            except Exception:
                pass
            self.editor.setText(code_text or "")
        else:
            self.editor = _CodeEditor(self)
            self.editor.setPlainText(code_text or "")

        vbox.addWidget(self.editor)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.run_btn = self.buttons.addButton(
            t.get("run_now", "Lancer"), QDialogButtonBox.AcceptRole
        )
        self.buttons.rejected.connect(self.reject)
        self.buttons.accepted.connect(self.accept)
        vbox.addWidget(self.buttons)

    def get_code(self) -> str:
        if HAS_QGIS_CODE_EDITOR:
            return self.editor.text()
        return self.editor.toPlainText()


class ToolApprovalDialog(QDialog):
    """Human-in-the-loop dialog shown before each agent tool execution."""

    APPROVE = 1
    APPROVE_ALL = 2
    FEEDBACK = 3
    CANCEL = 0

    def __init__(self, tool_name: str, tool_args: dict, t: dict, parent=None):
        super().__init__(parent)
        self._original_args = tool_args
        self._widgets = {}  # key → (widget, original_value)
        self.choice = self.CANCEL
        self.feedback_text = ""

        self.setWindowTitle(t.get("tool_approval_title", "Approve tool call"))
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        about_label = QLabel(t.get("tool_approval_about_to_call", "The agent is about to run:"))
        layout.addWidget(about_label)

        tool_label = QLabel(f"<b>{html.escape(tool_name)}</b>")
        layout.addWidget(tool_label)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #ddd;")
        layout.addWidget(sep)

        # ── Per-argument form ──
        if tool_args:
            form_widget = QWidget()
            form = QFormLayout(form_widget)
            form.setSpacing(4)
            form.setLabelAlignment(Qt.AlignRight)
            for key, value in tool_args.items():
                widget = self._make_widget(value)
                self._widgets[key] = (widget, value)
                form.addRow(f"{key} :", widget)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(form_widget)
            scroll.setMaximumHeight(260)
            scroll.setFrameShape(QScrollArea.NoFrame)
            layout.addWidget(scroll)
        else:
            layout.addWidget(QLabel("<i>—</i>"))

        sep2 = QWidget()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: #ddd;")
        layout.addWidget(sep2)

        feedback_label = QLabel(t.get("tool_approval_feedback_label", "Your message to the agent (optional):"))
        layout.addWidget(feedback_label)

        self._feedback_edit = QTextEdit()
        self._feedback_edit.setMaximumHeight(60)
        self._feedback_edit.setPlaceholderText(
            t.get("tool_approval_feedback_placeholder", "Describe an alternative, a correction, or a warning...")
        )
        layout.addWidget(self._feedback_edit)

        btn_layout = QHBoxLayout()
        approve_btn = QPushButton(t.get("tool_approval_btn_approve", "Approve"))
        approve_all_btn = QPushButton(t.get("tool_approval_btn_approve_all", "Approve all"))
        feedback_btn = QPushButton(t.get("tool_approval_btn_feedback", "Send feedback"))
        cancel_btn = QPushButton(t.get("tool_approval_btn_cancel_loop", "Cancel task"))

        approve_btn.setDefault(True)
        cancel_btn.setStyleSheet("color: #c0392b;")

        approve_btn.clicked.connect(self._on_approve)
        approve_all_btn.clicked.connect(self._on_approve_all)
        feedback_btn.clicked.connect(self._on_feedback)
        cancel_btn.clicked.connect(self._on_cancel)

        btn_layout.addWidget(approve_btn)
        btn_layout.addWidget(approve_all_btn)
        btn_layout.addWidget(feedback_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    # ── Widget factory (type-inferred from the Python value) ──────────────

    def _make_widget(self, value) -> QWidget:
        import re as _re
        if isinstance(value, bool):
            w = QCheckBox()
            w.setChecked(value)
            return w
        if isinstance(value, int):
            w = QSpinBox()
            w.setRange(-2_000_000_000, 2_000_000_000)
            w.setValue(value)
            return w
        if isinstance(value, float):
            w = QDoubleSpinBox()
            w.setRange(-1e12, 1e12)
            w.setDecimals(4)
            w.setStepType(QDoubleSpinBox.AdaptiveDecimalStepType)
            w.setValue(value)
            return w
        str_val = str(value) if value is not None else ""
        if _re.match(r"^#[0-9a-fA-F]{6}$", str_val):
            return self._make_color_widget(str_val)
        if isinstance(value, (list, dict)):
            import json as _json
            w = QLineEdit(_json.dumps(value, ensure_ascii=False))
            return w
        if "\n" in str_val or len(str_val) > 120:
            return self._make_code_widget(str_val)
        w = QLineEdit(str_val)
        return w

    def _make_code_widget(self, code: str) -> QWidget:
        if HAS_QGIS_CODE_EDITOR:
            w = QgsCodeEditorPython(self)
            w.setText(code)
            try:
                w.setLineNumbersVisible(True)
            except Exception:
                pass
            w._is_code_editor = True
        else:
            w = QPlainTextEdit(code)
            w._is_code_editor = True
        w.setMinimumHeight(160)
        return w

    def _make_color_widget(self, hex_color: str) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton()
        btn.setFixedSize(80, 24)
        qc = QColor(hex_color)
        btn._color = qc
        btn.setStyleSheet(f"background-color: {qc.name()}; border: 1px solid #888;")
        lbl = QLabel(qc.name())
        lbl.setStyleSheet("color: #666; font-size: 11px;")
        def _pick(*_, b=btn, l=lbl):
            c = QColorDialog.getColor(b._color, self)
            if c.isValid():
                b._color = c
                b.setStyleSheet(f"background-color: {c.name()}; border: 1px solid #888;")
                l.setText(c.name())
        btn.clicked.connect(_pick)
        row.addWidget(btn)
        row.addWidget(lbl)
        container._btn = btn
        return container

    # ── Value collection ──────────────────────────────────────────────────

    def get_args(self) -> dict:
        """Return args with user-edited values, preserving original types."""
        import json as _json
        result = {}
        for key, (widget, original) in self._widgets.items():
            if isinstance(original, bool) and isinstance(widget, QCheckBox):
                result[key] = widget.isChecked()
            elif isinstance(original, int) and isinstance(widget, QSpinBox):
                result[key] = widget.value()
            elif isinstance(original, float) and isinstance(widget, QDoubleSpinBox):
                result[key] = widget.value()
            elif hasattr(widget, "_btn") and hasattr(widget._btn, "_color"):
                result[key] = widget._btn._color.name()
            elif getattr(widget, "_is_code_editor", False):
                if HAS_QGIS_CODE_EDITOR and isinstance(widget, QgsCodeEditorPython):
                    result[key] = widget.text()
                else:
                    result[key] = widget.toPlainText()
            elif isinstance(widget, QLineEdit):
                text = widget.text()
                if isinstance(original, (list, dict)):
                    try:
                        result[key] = _json.loads(text)
                    except Exception:
                        result[key] = original
                else:
                    result[key] = text
            else:
                result[key] = original
        return result if result else self._original_args

    # ── Button handlers ───────────────────────────────────────────────────

    def _on_approve(self):
        self.choice = self.APPROVE
        self.accept()

    def _on_approve_all(self):
        self.choice = self.APPROVE_ALL
        self.accept()

    def _on_feedback(self):
        self.feedback_text = self._feedback_edit.toPlainText().strip()
        if not self.feedback_text:
            return
        self.choice = self.FEEDBACK
        self.accept()

    def _on_cancel(self):
        self.choice = self.CANCEL
        self.reject()


class MainDock(QDockWidget):
    _restore_done = False
    def __init__(self, iface, settings_manager, conversation_manager):
        super().__init__()
        self.iface = iface
        self.settings_manager = settings_manager
        self.history_turns = int(self.settings_manager.get("history_turns", 0))
        self.conversation_manager = conversation_manager

        self.agent = AIAgent(settings_manager)
        self.executor = CodeExecutor(iface, self.handle_execution_error, settings_manager)

        # Agent loop (function-calling mode)
        self.agent_loop = AgentLoop(
            settings_manager=settings_manager,
            iface=iface,
            executor=self.executor,
        )

        self.total_tokens_used = 0
        self.last_prompt_tokens = 0
        self.last_context_max = 0
        self.current_mode = self.settings_manager.get("mode", "local")
        self.current_model = self.settings_manager.get("model", "")

        try:
            self.lang = self.settings_manager.get_language()
        except Exception:
            self.lang = "en"
        self.t = get_translations(self.lang)

        self.setWindowTitle(self.t["dock_title"])
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setMinimumWidth(400)

        self.messages_loaded = False
        self._last_exec_had_error = False
        self._refresh_ca_bundle_on_open()
        self.init_ui()
        self._pending_ranges = {}  # pid -> (start_pos, end_pos)
        self._process_recorder = ProcessRecorder()

    def _refresh_ca_bundle_on_open(self):
        if not self.settings_manager.get_use_windows_ca_bundle():
            return
        cert_enc = self.settings_manager.get_ca_bundle_cert_encoding()
        if not cert_enc:
            QMessageBox.warning(
                self, self.t.get("error", "Erreur"),
                self.t.get("ca_bundle_encoding_empty", "Le champ d'encodage des certificats est vide.")
            )
            return
        try:
            from ..core.cert_manager import refresh_ca_bundle
            plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path, count = refresh_ca_bundle(plugin_dir, cert_encoding_filter=cert_enc)
            self.settings_manager.set_ca_bundle_path(path)
            QMessageBox.information(
                self, self.t.get("success", "Succès"),
                self.t.get("ca_bundle_refreshed", "CA bundle mis à jour ({count} certificats exportés).").format(count=count)
            )
        except Exception as e:
            QMessageBox.critical(
                self, self.t.get("error", "Erreur"),
                self.t.get("ca_bundle_error", "Erreur lors de la mise à jour du CA bundle : {}").format(str(e))
            )

    def init_ui(self):
        main_widget = QWidget()
        layout = QVBoxLayout()

        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self.update_status_label()

        self.tabs = QTabWidget()
        self.assistant_tab = QWidget()
        self.debug_tab = QWidget()
        self.tabs.addTab(self.assistant_tab, self.t["assistant_tab"])
        self.tabs.addTab(self.debug_tab, self.t["debug_tab"])
        self.tabs.setTabEnabled(1, False)

        self.init_assistant_tab()
        self.init_debug_tab()

        # Processes browser tab
        self.process_browser = ProcessBrowserWidget(
            base_folder_getter=self.settings_manager.get_processes_folder,
            language=self.settings_manager.get_language(),
        )
        self.process_browser.run_requested.connect(self._on_run_process_requested)
        self.process_browser.parent_set_base_folder = self._set_processes_base_folder
        self.tabs.addTab(
            self.process_browser,
            self.t.get("process_browser_tab", "Traitements"),
        )

        layout.addWidget(self.tabs)
        main_widget.setLayout(layout)
        self.setWidget(main_widget)

        total_tokens = 0
        for msg in self.conversation_manager.get_messages():
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                # Legacy footer <p>...
                matches = re.findall(r"⎇[^0-9]*?(\d+)", content, flags=re.IGNORECASE | re.DOTALL)
                if not matches:
                    matches = re.findall(r"(?:Tokens\s+(?:utilisés|used)\s*:\s*)(\d+)", content, flags=re.IGNORECASE)
                # Current footer <!--TOK:n--> or <!--TOK:n:in:out-->
                if not matches:
                    matches = re.findall(r"<!--\s*TOK\s*:\s*(\d+)(?::\d+:\d+)?\s*-->\s*$", content, flags=re.IGNORECASE)
                for m in matches:
                    total_tokens += int(m)
        self.total_tokens_used = total_tokens
        self.update_status_label()
        self._apply_agent_mode_ui()
        self.refresh_chat_highlight()

        msgs = self.conversation_manager.get_messages()

        def _render_line(m):
            role = m.get("role")
            content = m.get("content", "")
            you = self.t["you_prefix"]
            assistant = self.t["assistant_prefix"]
            prefix = f"🧑‍💻 {you} : " if role == "user" else f"🤖 {assistant} : "
            safe = self._render_for_feed(content)
            return f"<div style='margin-bottom:4px;'><b>{prefix}</b>{safe}</div>"

        html = "".join(_render_line(m) for m in msgs)
        self.conversation_view.setHtml(html)
        self.conversation_view.moveCursor(QTextCursor.End)

        if hasattr(self, "refresh_chat_highlight"):
            self.refresh_chat_highlight()

    def _show_spinner(self, text: str = None):
        if text is None:
            text = self.t["loading"]
        self.spinner_text.setText(text)
        self.spinner_label.setVisible(True)
        self.spinner_text.setVisible(True)
        self.spinner_movie.start()
        self.conversation_view.moveCursor(QTextCursor.End)

    def _hide_spinner(self):
        self.spinner_movie.stop()
        self.spinner_label.setVisible(False)
        self.spinner_text.setVisible(False)
        self.spinner_text.clear()

    def extract_token_count(self, usage):
        if isinstance(usage, dict):
            return usage.get("total_tokens", 0)
        return usage if isinstance(usage, int) else 0

    def init_assistant_tab(self):
        layout = QVBoxLayout()

        self.conversation_view = QTextBrowser()
        self.conversation_view.setOpenLinks(False)
        self.conversation_view.setAcceptRichText(True)
        self.conversation_view.anchorClicked.connect(self._on_chat_link_clicked)

        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText(self.t["message_prompt"])

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.conversation_view)
        splitter.addWidget(self.input_text)
        splitter.setSizes([300, 120])
        layout.addWidget(splitter)

        spinner_row = QHBoxLayout()
        self.spinner_label = QLabel()
        self.spinner_text  = QLabel()
        self.spinner_text.setStyleSheet("color: gray;")

        spinner_path = os.path.join(os.path.dirname(__file__), "..", "img", "spinner.gif")
        self.spinner_movie = QMovie(spinner_path)
        self.spinner_label.setMovie(self.spinner_movie)

        self.spinner_label.setVisible(False)
        self.spinner_text.setVisible(False)

        spinner_row.addWidget(self.spinner_label)
        spinner_row.addWidget(self.spinner_text)
        spinner_row.addStretch(1)

        layout.addLayout(spinner_row)

        self.btn_send = QPushButton(self.t["send"])
        self.btn_generate = QPushButton(self.t["generate"])
        self.btn_execute = QPushButton(self.t["execute"])
        self._execute_default_stylesheet = self.btn_execute.styleSheet()
        self.btn_clear = QPushButton(self.t["clear"])
        self.btn_options = QPushButton(self.t["options"])
        self.btn_index = QPushButton(self.t["index_project"])

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.btn_send)
        button_layout.addWidget(self.btn_generate)
        button_layout.addWidget(self.btn_execute)
        button_layout.addWidget(self.btn_clear)
        button_layout.addWidget(self.btn_options)
        button_layout.addWidget(self.btn_index)
        layout.addLayout(button_layout)

        
        
        self.btn_index.clicked.connect(self.handle_index_project)

        self.btn_save_process = QPushButton(
            "\U0001f4be " + self.t.get("save_process_btn", "Enregistrer comme traitement")
        )
        self.btn_save_process.setStyleSheet(
            "QPushButton { background-color: #1e3a1e; color: #80c880;"
            " border: 1px solid #3a6a3a; padding: 4px 10px; font-weight: bold; }"
            "QPushButton:hover { background-color: #2a4a2a; }"
        )
        self.btn_save_process.setVisible(False)
        self.btn_save_process.clicked.connect(self._open_save_process_dialog)
        button_layout.addWidget(self.btn_save_process)

        self.btn_send.clicked.connect(self.handle_send)
        self.btn_generate.clicked.connect(self.handle_generate)
        self.btn_execute.clicked.connect(self.handle_execute)
        self.btn_clear.clicked.connect(self.clear_conversation)
        self.btn_options.clicked.connect(self.open_options)

        self.assistant_tab.setLayout(layout)
        self.set_execute_pending(False)

    def init_debug_tab(self):
        layout = QVBoxLayout()
        self.debug_label = QLabel(self.t["error_during_exec"])
        self.debug_text = QTextEdit()
        self.debug_text.setReadOnly(True)

        self.btn_fix_and_run = QPushButton(self.t["fix_and_run"])
        self.btn_fix_and_run.clicked.connect(self.fix_and_execute)

        layout.addWidget(self.debug_label)
        layout.addWidget(self.debug_text)
        layout.addWidget(self.btn_fix_and_run)

        self.debug_tab.setLayout(layout)

    def show_loading_dialog(self, message=None):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t["dialog_title"])
        dialog.setModal(True)
        dialog.setMinimumWidth(200)

        layout = QVBoxLayout(dialog)

        image_path = os.path.join(os.path.dirname(__file__), "..", "img", "ai_is_working.png")
        pixmap = QPixmap(image_path)
        image_label = QLabel()
        image_label.setPixmap(pixmap)
        image_label.setAlignment(Qt.AlignCenter)

        text_label = QLabel(message or self.t["loading"])
        text_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(image_label)
        layout.addWidget(text_label)

        dialog.setLayout(layout)
        dialog.show()
        QCoreApplication.processEvents()
        return dialog

    def append_to_conversation(self, role, message, tokens_used=None, save=True):
        you = self.t.get("you_prefix", "You")
        assistant = self.t.get("assistant_prefix", "Assistant")
        prefix = f"🧑‍💻 {you} : " if role == "user" else f"🤖 {assistant} : "

        '''
        if tokens_used is not None and role == "assistant":
            message += (
                f"\n<p style='color:gray;font-size:10px;'>"
                f"⎇ {self.t['token_count']} : {tokens_used}</p>"
            )
        '''

        cur = self.conversation_view.textCursor()
        cur.movePosition(QTextCursor.End)
        # Always insert as HTML, isolated in a <div> to avoid style bleed
        cur.insertHtml(f"<div style='margin-bottom:4px;'><b>{prefix}</b>{message}</div>")
        self.conversation_view.setTextCursor(cur)
        self.conversation_view.moveCursor(QTextCursor.End)

        if save:
            self.conversation_manager.append(role, message)


    def set_execute_pending(self, pending: bool):
        if pending:
            self.btn_execute.setStyleSheet(
                "background-color:#FFD24D; color:#222; font-weight:600; border:1px solid #C9A000;"
            )
            tt = self.t["execute_label"]
            self.btn_execute.setToolTip(tt)
        else:
            self.btn_execute.setStyleSheet(self._execute_default_stylesheet)
            self.btn_execute.setToolTip("")

    def handle_index_project(self):
        try:
            self.btn_index.setEnabled(False)
            prj = build_project_snapshot(sample_fields_max=50)
            self._project_snapshot = prj
            msg = self.t["project_indexed"]
            self.conversation_view.append(f"<i>{msg}</i>")
            self.conversation_view.moveCursor(QTextCursor.End)
        except Exception as e:
            QMessageBox.critical(self, self.t.get("error", "Error"), str(e))
        finally:
            self.btn_index.setEnabled(True)

    # -----------------------
    # STREAM HELPERS
    # -----------------------

    def _wrap_assistant_bubble(self, body_html: str, *, is_context: bool = False, tokens_used: int = None) -> str:
        """
        Build a complete assistant chat bubble via the chat_theme helper.
        body_html must already be safe HTML (the markdown pipeline guarantees this).
        """
        label = self.t.get("assistant_prefix", "Assistant")
        tokens_info = (
            f"⎇ {self.t.get('token_count', 'Tokens')} : {tokens_used}"
            if tokens_used is not None else ""
        )
        return wrap_assistant(body_html, label=label, tokens_info=tokens_info, context_badge=is_context)

    def _render_assistant_html(self, content: str, tokens_used: int = None, is_context: bool = False) -> str:
        return self._wrap_assistant_bubble(content, is_context=is_context, tokens_used=tokens_used)





    def _render_stream_content(self, mode: str, text: str) -> str:
        s = self._normalize_text((text or "").replace("\r\n", "\n"))

        if mode == "code":
            safe = self._escape_html(s)
            safe = (safe.replace("&lt;br&gt;", "<br>")
                        .replace("&lt;br/&gt;", "<br>")
                        .replace("&lt;br /&gt;", "<br>"))
            safe = safe.replace("\n", "<br>")
            return f"<pre class='md'><code class='md'>{safe}</code></pre>"

        return self._render_markdownish_chat(s)





    def _append_pending_assistant(self) -> str:
        import uuid as _uuid
        pid = str(_uuid.uuid4())
        pending_text = self.t.get("loading", "Processing request...")

        # One stable wrapper; inner span will be updated during stream
        pending_html = self._wrap_assistant_bubble(
            body_html=f"<span class='stream-{pid}' style='color:gray;'>⌛ {html.escape(pending_text)}</span>",
            is_context=True,
            tokens_used=None
        )
        pending_html = f"<div data-pending='{pid}' id='pending-{pid}' style='opacity:0.95;'>{pending_html}</div>"


        cur = self.conversation_view.textCursor()
        cur.movePosition(QTextCursor.End)
        start = cur.position()
        cur.insertHtml(pending_html)
        end = cur.position()
        self.conversation_view.setTextCursor(cur)
        self.conversation_view.moveCursor(QTextCursor.End)

        # Store the exact character range so _replace_pending can overwrite it later
        self._pending_ranges[pid] = (start, end)

        # spinner under the chat
        self._show_spinner()
        return pid




    def _replace_pending(self, pending_id: str, final_html: str, keep: bool=False, process_events: bool=False):
        # keep=False: finalize by replacing the pending block in-place with the final HTML
        try:
            if pending_id in self._pending_ranges and not keep:
                start, end = self._pending_ranges.pop(pending_id)
                cur = self.conversation_view.textCursor()
                cur.setPosition(start)
                cur.setPosition(end, QTextCursor.KeepAnchor)
                cur.insertHtml(final_html)
                self.conversation_view.setTextCursor(cur)
                self.conversation_view.moveCursor(QTextCursor.End)
            else:
                # No stored range (non-stream path or interim update): append to document
                html_doc = self.conversation_view.toHtml()
                html_doc += final_html
                self.conversation_view.setHtml(html_doc)
                self.conversation_view.moveCursor(QTextCursor.End)

            if process_events:
                QCoreApplication.processEvents()
        except Exception:
            self.conversation_view.append(final_html)
            self.conversation_view.moveCursor(QTextCursor.End)


    # -----------------------
    # SEND (agent mode — function calling)
    # -----------------------
    def handle_send_agent(self, prompt: str):
        """
        Agent mode: runs the tool_call → execute → tool_result → LLM loop,
        rendering each step live in the chat as it progresses.
        Uses AgentLoop and AgentStepsRenderer.
        """
        from qgis.PyQt.QtCore import QCoreApplication
        import uuid as _uuid

        # 1) Display the user bubble
        self._ensure_md_css()
        user_bubble = wrap_user(
            body_html=self._escape_html(prompt).replace("\n", "<br>"),
            label=self.t.get("you_prefix", "You"),
        )
        cur = self.conversation_view.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.insertHtml(user_bubble)
        self.conversation_view.setTextCursor(cur)
        self.conversation_view.moveCursor(QTextCursor.End)

        # Persist the user message before the LLM round-trip
        self.conversation_manager.append("user", prompt)

        # Reset the process recorder for this new run
        self._process_recorder.start()
        if hasattr(self, "btn_save_process"):
            self.btn_save_process.setVisible(False)

        # 2) Build the project snapshot for LLM context
        try:
            ctx_tokens = int(self.settings_manager.get_project_context_max_tokens() or 32768)
        except Exception:
            ctx_tokens = 32768
        try:
            snapshot = build_project_snapshot()
            snapshot_json = snapshot_to_json(snapshot, max_bytes=ctx_tokens * 4)
        except Exception:
            snapshot_json = "{}"

        # 3) Insert a placeholder assistant bubble with an empty agent-steps block
        show_steps = True
        try:
            show_steps = bool(self.settings_manager.get_agent_show_steps())
        except Exception:
            pass

        block_id = f"agent_{_uuid.uuid4().hex[:8]}"
        renderer = AgentStepsRenderer()

        loading_html = (
            f'<span style="opacity:0.55;font-style:italic;">'
            f'⌛ {html.escape(self.t.get("loading", "Processing..."))}</span>'
        )
        placeholder_bubble = wrap_assistant(
            body_html=loading_html,
            label=self.t.get("assistant_prefix", "Assistant"),
            agent_steps_html=f'<div id="{block_id}"></div>',
        )

        cur = self.conversation_view.textCursor()
        cur.movePosition(QTextCursor.End)
        start_pos = cur.position()
        cur.insertHtml(placeholder_bubble)
        end_pos = cur.position()
        self.conversation_view.setTextCursor(cur)
        self.conversation_view.moveCursor(QTextCursor.End)

        # Store the range so the placeholder can be replaced by the final bubble later
        agent_range_key = f"__agent_{block_id}"
        self._pending_ranges[agent_range_key] = (start_pos, end_pos)

        self._show_spinner()
        self.set_busy(True)

        # 4) Step callback — updates the agent-steps block live in the chat
        def on_step(event: dict):
            # Always feed the recorder (independent of show_steps)
            try:
                self._process_recorder.on_step(event)
            except Exception:
                pass

            # Context gauge: update status bar silently, never render in the steps block.
            if event.get("type") == "context_usage":
                data = event.get("data", {})
                self.last_prompt_tokens = data.get("prompt_tokens", 0)
                self.last_context_max = data.get("context_max", 0)
                self.update_status_label()
                return

            if not show_steps:
                return
            # The "final" event is rendered as the bubble body by _on_agent_finished;
            # do not add it to the steps block to avoid duplication.
            if event.get("type") == "final":
                return
            try:
                renderer.add_event(event)
                new_steps_html = renderer.to_html(show_final_marker=False)
                range_info = self._pending_ranges.get(agent_range_key)
                if not range_info:
                    return
                start, end = range_info
                updated_bubble = wrap_assistant(
                    body_html=loading_html,
                    label=self.t.get("assistant_prefix", "Assistant"),
                    agent_steps_html=new_steps_html,
                )
                cur = self.conversation_view.textCursor()
                cur.setPosition(start)
                cur.setPosition(end, QTextCursor.KeepAnchor)
                cur.insertHtml(updated_bubble)
                self._pending_ranges[agent_range_key] = (start, cur.position())
                self.conversation_view.moveCursor(QTextCursor.End)
                QCoreApplication.processEvents()
            except Exception:
                pass

        # 5) Start the agent loop in a dedicated thread.
        # Blocking LLM calls run in the worker; QGIS tool execution stays on the main thread via signal.
        def _on_agent_finished(final_text, total_tokens, total_input, total_output):
            # 6) Replace the placeholder with the final complete bubble
            safe_body = self._render_markdownish_chat(final_text)
            if total_tokens:
                tok_label = self.t.get('token_count', 'Tokens')
                tokens_text = (
                    f"{tok_label}: {total_tokens}"
                    f" (in:{total_input} / out:{total_output})"
                )
            else:
                tokens_text = ""

            if show_steps and renderer.events:
                summary_label = self.t.get("agent_summary_label", "AI Summary")
                safe_body = (
                    f'<p style="font-size:12px;color:#7a9abf;font-weight:bold;'
                    f'margin-top:0;margin-bottom:4px;text-align:center;">'
                    f'{html.escape(summary_label)}</p>'
                ) + safe_body

            final_bubble = wrap_assistant(
                body_html=safe_body,
                label=self.t.get("assistant_prefix", "Assistant"),
                tokens_info=tokens_text,
                agent_steps_html=(renderer.to_html(show_final_marker=True)
                                  if show_steps else ""),
            )

            try:
                start, end = self._pending_ranges.pop(agent_range_key, (None, None))
                if start is not None and end is not None:
                    cur = self.conversation_view.textCursor()
                    cur.setPosition(start)
                    cur.setPosition(end, QTextCursor.KeepAnchor)
                    cur.insertHtml(final_bubble)
                    self.conversation_view.setTextCursor(cur)
                    self.conversation_view.moveCursor(QTextCursor.End)
                else:
                    self.conversation_view.append(final_bubble)
            except Exception:
                self.conversation_view.append(final_bubble)

            # 7) Update the cumulative token counter
            self.total_tokens_used += (total_tokens or 0)
            try:
                self.settings_manager.set(
                    "token_total_since_clear", self.total_tokens_used
                )
            except Exception:
                pass
            self.update_status_label()

            # 8) Persist the response (steps block + token marker for recount on reload)
            steps_marker = ""
            if show_steps and renderer.events:
                steps_html_for_save = renderer.to_html(show_final_marker=True)
                steps_marker = f"<!--AGENT_STEPS_START-->{steps_html_for_save}<!--AGENT_STEPS_END-->"
            saved = steps_marker + safe_body
            if total_tokens:
                saved += f"<!--TOK:{total_tokens}:{total_input}:{total_output}-->"
            try:
                self.conversation_manager.append("assistant", saved)
            except Exception:
                pass

            # 9) Stop the recorder
            try:
                self._process_recorder.stop()
            except Exception:
                pass

            # 10) UI cleanup
            self._hide_spinner()
            self.set_busy(False)
            if hasattr(self, "refresh_chat_highlight"):
                try:
                    self.refresh_chat_highlight()
                except Exception:
                    pass

            # 11) Show/hide the save-process button
            try:
                has_steps = bool(self._process_recorder.steps)
                if hasattr(self, "btn_save_process"):
                    self.btn_save_process.setVisible(has_steps)
            except Exception:
                pass

            # Release the worker thread
            self._agent_thread.quit()

        def _on_agent_error(err_str):
            import traceback
            final_text = (
                self.t.get("llm_request_error", "Request error") + ": " + err_str
            )
            _on_agent_finished(final_text, 0, 0, 0)

        def _on_agent_cancelled():
            cancelled_msg = self.t.get("agent_cancelled", "Request cancelled by user.")
            cancelled_html = (
                f'<p style="margin:4px 0;color:#c0392b;font-style:italic;">'
                f'⛔ {html.escape(cancelled_msg)}</p>'
            )
            bubble = wrap_assistant(
                body_html=cancelled_html,
                label=self.t.get("assistant_prefix", "Assistant"),
            )
            try:
                start, end = self._pending_ranges.pop(agent_range_key, (None, None))
                if start is not None and end is not None:
                    cur = self.conversation_view.textCursor()
                    cur.setPosition(start)
                    cur.setPosition(end, QTextCursor.KeepAnchor)
                    cur.insertHtml(bubble)
                    self.conversation_view.setTextCursor(cur)
                    self.conversation_view.moveCursor(QTextCursor.End)
                else:
                    self.conversation_view.append(bubble)
            except Exception:
                self.conversation_view.append(bubble)
            self._hide_spinner()
            self.set_busy(False)
            self._agent_thread.quit()

        # Fetch turns+1 to include the current turn, then drop the last user message
        # (it is injected by agent_loop directly as the current prompt)
        turns = max(0, int(self.history_turns))
        history_msgs = self.conversation_manager.get_last_turns_messages(turns + 1)
        if history_msgs and history_msgs[-1].get("role") == "user":
            history_msgs = history_msgs[:-1]
        # Strip HTML from assistant messages before sending to the LLM
        history_msgs = [
            {**m, "content": self._clean_for_llm(m["content"])} if m.get("role") == "assistant" else m
            for m in history_msgs
        ]

        self._approve_all_tools = False
        self._agent_thread = QThread(self)
        self._agent_worker = AgentWorker(
            agent_loop=self.agent_loop,
            user_prompt=prompt,
            snapshot_json=snapshot_json,
            history_messages=history_msgs,
        )
        self._agent_worker.moveToThread(self._agent_thread)

        self._agent_worker.step_event.connect(on_step, Qt.QueuedConnection)
        self._agent_worker.tool_request.connect(
            self._on_agent_tool_request, Qt.QueuedConnection
        )
        self._agent_worker.finished.connect(_on_agent_finished, Qt.QueuedConnection)
        self._agent_worker.error_signal.connect(_on_agent_error, Qt.QueuedConnection)
        self._agent_worker.cancelled_signal.connect(_on_agent_cancelled, Qt.QueuedConnection)
        self._agent_thread.started.connect(self._agent_worker.run)
        self._agent_thread.finished.connect(self._agent_thread.deleteLater)

        self._agent_thread.start()

    @pyqtSlot(str, object)
    def _on_agent_tool_request(self, tool_name: str, args: object):
        """Execute a QGIS tool on the main thread, with optional human approval gate."""
        worker = getattr(self, "_agent_worker", None)

        if (self.settings_manager.get_agent_tool_approval()
                and not getattr(self, "_approve_all_tools", False)):
            dlg = ToolApprovalDialog(tool_name, args, self.t, parent=self)
            dlg.exec_()

            if dlg.choice == ToolApprovalDialog.CANCEL:
                if worker:
                    worker.cancel()
                return

            if dlg.choice == ToolApprovalDialog.APPROVE_ALL:
                self._approve_all_tools = True

            if dlg.choice == ToolApprovalDialog.FEEDBACK:
                feedback = dlg.feedback_text
                result = {
                    "success": False,
                    "tool": tool_name,
                    "error": f"[{self.t.get('tool_approval_btn_feedback', 'User feedback')}]: {feedback}",
                }
                if worker:
                    worker.receive_tool_result(result)
                return

            args = dlg.get_args()

        result = self.agent_loop._execute_tool(tool_name, args)
        if worker:
            worker.receive_tool_result(result)

    # -----------------------
    # Custom processes
    # -----------------------

    def _on_chat_link_clicked(self, url):
        """Handle all link clicks in the conversation view."""
        try:
            if url.scheme() == "qgis_ai":
                if url.host() == "save_process":
                    self._open_save_process_dialog()
            else:
                # Open external links (http/https) with the system browser.
                try:
                    from qgis.PyQt.QtGui import QDesktopServices as _DServ
                except ImportError:
                    from qgis.PyQt.QtCore import QDesktopServices as _DServ
                _DServ.openUrl(url)
        except Exception as e:
            QMessageBox.critical(self, "Erreur lien", str(e))

    def _open_save_process_dialog(self):
        """Open the ProcessSaveDialog so the user can save the last agent run as a reusable process."""
        try:
            if not self._process_recorder.steps:
                QMessageBox.information(
                    self, "Info",
                    self.t.get("process_no_steps", "Aucune étape enregistrée.")
                )
                return
            base_folder = self.settings_manager.get_processes_folder()
            dlg = ProcessSaveDialog(
                self._process_recorder, base_folder,
                language=self.settings_manager.get_language(), parent=self,
            )
            if dlg.exec_():
                if hasattr(self, "process_browser"):
                    self.process_browser.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir le dialog :\n{e}")

    def _on_run_process_requested(self, process_dict: dict):
        """Open the ProcessRunDialog to execute a saved process."""
        dlg = ProcessRunDialog(process_dict, self.agent_loop,
                               language=self.settings_manager.get_language(), parent=self)
        dlg.exec_()

    def _set_processes_base_folder(self, path: str):
        """Persist a new base folder for custom processes and refresh the browser."""
        self.settings_manager.set_processes_folder(path)
        if hasattr(self, "process_browser"):
            self.process_browser.refresh()

    # -----------------------
    # SEND (chat) with stream
    # -----------------------
    def handle_send(self):
        prompt = self.input_text.toPlainText().strip()
        if not prompt:
            return

        # Route to agent mode if enabled
        try:
            if self.settings_manager.get_agent_mode_enabled():
                self.input_text.clear()
                self.handle_send_agent(prompt)
                return
        except Exception:
            pass

        # 1) Show user message and clear input
        self.append_to_conversation("user", prompt)
        self.input_text.clear()

        # 2) Insert pending placeholder and lock the UI
        pending_id = self._append_pending_assistant()
        self.set_busy(True)

        # 3) Build the message history for the API call
        messages = self.build_messages_for_api(prompt)

        # 4) Read streaming preference (with safety fallback)
        try:
            use_stream = bool(self.settings_manager.get_streaming_enabled())
        except Exception:
            use_stream = bool(self.settings_manager.get("streaming_enabled", False))

        # Accumulator for streaming text chunks
        live_buf = {"text": ""}

        # Worker thread setup
        self._thread = QThread(self)
        self._worker = ChatWorker(
            self.agent,
            prompt,
            mode="chat",
            lang=self.lang,
            messages=messages,
            stream=use_stream
        )
        self._worker.moveToThread(self._thread)

        # Signal handlers
        def _on_chunk(txt: str):
            live_buf["text"] += (txt or "")
            self._update_stream_pending(pending_id, live_buf["text"], mode="chat")  # or "code"



        def _on_finished(final_text: str, usage_obj):
            tokens = self.extract_token_count(usage_obj)
            self.total_tokens_used += tokens
            self.settings_manager.set("token_total_since_clear", self.total_tokens_used)
            self.update_status_label()

            # Empty response or context overflow: show error message, skip execution
            if not final_text.strip() or self._looks_like_ctx_overflow(final_text):
                self._handle_model_empty_or_overflow(pending_id, mode="chat")
                self._thread.quit(); self._thread.wait()
                self._worker.deleteLater(); self._thread.deleteLater()
                return

            # Render to HTML (tables, lists, etc.) matching the streaming pipeline
            safe_html = self._render_markdownish_chat(final_text)

            # Build the assistant bubble without a duplicate header or a <p> for tokens
            if hasattr(self, "_wrap_assistant_bubble"):
                final_html = self._wrap_assistant_bubble(safe_html, is_context=True, tokens_used=tokens)
            else:
                tmp = self._render_assistant_html(safe_html, tokens_used=None)
                if tokens:
                    tmp = tmp.replace(
                        "</div></div>",  # ferme .msg__body puis .msg
                        f"<div class='msg__tokens'>⎇ {self.t['token_count']} : {tokens}</div></div>"
                    )
                final_html = tmp

            # Replace the pending block with the final rendered bubble
            self._replace_pending(pending_id, final_html, keep=False)

            # Persist only the content HTML + an invisible token marker for recount on reload
            saved = safe_html if not tokens else f"{safe_html}<!--TOK:{tokens}-->"
            self.conversation_manager.append("assistant", saved)

            # UI cleanup
            self._hide_spinner()
            self.set_busy(False)
            self._thread.quit(); self._thread.wait()
            self._worker.deleteLater(); self._thread.deleteLater()

            if hasattr(self, "refresh_chat_highlight"):
                self.refresh_chat_highlight()



        def _on_error(msg: str):
            err_label = self.t.get('llm_request_error', 'Request error')
            err_html = self._render_assistant_html(
                f"<span style='color:#b00'>{err_label} : {self._escape_html(msg)}</span>"
            )
            self._replace_pending(pending_id, err_html, keep=False)
            self._hide_spinner()
            self.set_busy(False)
            self._thread.quit(); self._thread.wait()
            self._worker.deleteLater(); self._thread.deleteLater()

        # Wire up signals
        self._thread.started.connect(self._worker.run)
        if use_stream and hasattr(self._worker, "stream_chunk"):
            self._worker.stream_chunk.connect(_on_chunk)
        self._worker.finished.connect(_on_finished)
        self._worker.error.connect(_on_error)

        self._thread.start()



    def _start_chatworker(self, prompt, messages, pending_id, mode="chat"):
        self._thread = QThread(self)
        self._worker = ChatWorker(self.agent, prompt, mode=mode, lang=self.lang, messages=messages)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)

        def _on_finished(response, usage):
            tokens = self.extract_token_count(usage)

            # 1) Empty/overflow check — do not activate Execute button
            if not (response or "").strip() or self._looks_like_ctx_overflow(response):
                # no Execute activation
                try:
                    self.executor.clear_last_code()
                except Exception:
                    pass
                self.set_execute_pending(False)
                self._handle_model_empty_or_overflow(pending_id, mode=mode)
                self._hide_spinner(); self.set_busy(False)
                self._thread.quit(); self._thread.wait()
                self._worker.deleteLater(); self._thread.deleteLater()
                return

            # 2) comptage tokens + statut
            self.total_tokens_used += tokens
            self.settings_manager.set("token_total_since_clear", self.total_tokens_used)
            self.update_status_label()

            # 3) rendu selon mode
            if mode == "code":
                cleaned = (self.clean_code(response) or "").strip()
                if not cleaned:
                    # pas de code après nettoyage → traiter comme overflow/vide
                    try:
                        self.executor.clear_last_code()
                    except Exception:
                        pass
                    self.set_execute_pending(False)
                    self._handle_model_empty_or_overflow(pending_id, mode="code")
                    self._hide_spinner(); self.set_busy(False)
                    self._thread.quit(); self._thread.wait()
                    self._worker.deleteLater(); self._thread.deleteLater()
                    return

                # HTML joli dans le chat
                safe = f"<pre class='md'><code class='md'>{self._escape_html(cleaned)}</code></pre>"

                # préparer le bouton Exécuter
                self.executor.set_last_code(cleaned)
                self.set_execute_pending(True)
            else:
                # chat classique
                safe = self._render_markdownish_chat(response)

            # 4) bulle assistant + tokens (sans <p>)
            if hasattr(self, "_wrap_assistant_bubble"):
                final_html = self._wrap_assistant_bubble(safe, is_context=False, tokens_used=tokens)
            else:
                tmp = self._render_assistant_html(safe, tokens_used=None)  # pas de <p> ici
                if tokens:
                    tmp = f"{tmp}<div class='msg__tokens'>⎇ {self.t['token_count']} : {tokens}</div>"
                final_html = tmp

            # 5) remplacer le pending par le rendu final
            self._replace_pending(pending_id, final_html)

            # 6) persister l'HTML rendu + TOK en commentaire (pas de balises visibles)
            saved_content = safe if not tokens else f"{safe}<!--TOK:{tokens}-->"
            self.conversation_manager.append("assistant", saved_content)

            # 7) cleanup UI
            self._hide_spinner()
            self.set_busy(False)
            self._thread.quit(); self._thread.wait()
            self._worker.deleteLater(); self._thread.deleteLater()

            if hasattr(self, "refresh_chat_highlight"):
                self.refresh_chat_highlight()


        def _on_error(msg):
            final_html = self._render_assistant_html(f"<span style='color:#b00'>Erreur : {self._escape_html(msg)}</span>")
            self._replace_pending(pending_id, final_html)
            self._hide_spinner()
            self.set_busy(False)
            self._thread.quit(); self._thread.wait()
            self._worker.deleteLater(); self._thread.deleteLater()

        self._worker.finished.connect(_on_finished)
        self._worker.error.connect(_on_error)
        self._thread.start()


    # -----------------------
    # GENERATE CODE with stream
    # -----------------------
    def handle_generate(self):
        prompt = self.input_text.toPlainText().strip()
        if not prompt:
            return

        # 1) trace côté UI + reset saisie
        self.append_to_conversation("user", prompt)
        self.input_text.clear()

        # 2) placeholder "pending" + lock UI
        pending_id = self._append_pending_assistant()
        self.set_busy(True)

        # 3) construire l'historique à envoyer
        messages = self.build_messages_for_api(prompt)

        # 4) stream ON/OFF depuis les réglages (filet de sécu rétrocompat)
        try:
            use_stream = bool(self.settings_manager.get_streaming_enabled())
        except Exception:
            use_stream = bool(self.settings_manager.get("streaming_enabled", False))

        # Accumulateur live
        live_buf = {"text": ""}

        # Si pas de stream → on garde le worker classique
        if not use_stream:
            self._start_chatworker(prompt, messages, pending_id, mode="code")
            return

        # --- STREAM ---
        self._thread = QThread(self)
        self._worker = ChatWorker(
            self.agent,
            prompt,
            mode="code",
            lang=self.lang,
            messages=messages,
            stream=True
        )
        self._worker.moveToThread(self._thread)

        def _on_chunk(txt: str):
            live_buf["text"] += (txt or "")
            self._update_stream_pending(pending_id, live_buf["text"], mode="code")  # or "code"



        def _on_finished(final_text: str, usage_obj):
            # Tokens
            tokens = self.extract_token_count(usage_obj)
            self.total_tokens_used += tokens
            self.settings_manager.set("token_total_since_clear", self.total_tokens_used)
            self.update_status_label()

            # 1) Nettoyage du code (enlève <pre>, <code>, <br>, &quot;, etc.)
            cleaned_code = self.clean_code(final_text).strip()

            # 2) Réponse vide / overflow → message d'erreur + pas d'exécution
            if (not final_text.strip()) or (not cleaned_code) or self._looks_like_ctx_overflow(final_text):
                # annule tout "pré-exécution"
                try:
                    self.executor.clear_last_code()
                except Exception:
                    pass
                self.set_execute_pending(False)
                self._handle_model_empty_or_overflow(pending_id, mode="code")
                self._thread.quit(); self._thread.wait()
                self._worker.deleteLater(); self._thread.deleteLater()
                return

            # 3) Rendu HTML propre dans le chat (identique au mode "Envoyer")
            code_html = f"<pre class='md'><code class='md'>{self._escape_html(cleaned_code)}</code></pre>"

            if hasattr(self, "_wrap_assistant_bubble"):
                # bulle uniforme, sans <p> tokens
                final_html = self._wrap_assistant_bubble(code_html, is_context=True, tokens_used=tokens)
            else:
                # fallback : utilise ton wrapper actuel SANS injecter de <p>
                tmp = self._render_assistant_html(code_html, tokens_used=None)
                if tokens:
                    # ajoute un bloc propre pour les tokens (évite <p>)
                    tmp = tmp.replace(
                        "</div></div>",  # ferme .msg__body puis .msg (structure de ta bulle)
                        f"<div class='msg__tokens'>⎇ {self.t['token_count']} : {tokens}</div></div>"
                    )
                final_html = tmp

            # 4) Remplace le pending par le rendu final
            self._replace_pending(pending_id, final_html)

            # 5) Historique (HTML + TOK en commentaire invisible)
            saved = code_html if not tokens else f"{code_html}<!--TOK:{tokens}-->"
            self.conversation_manager.append("assistant", saved)

            # 6) Prépare le bouton Exécuter (code bien nettoyé)
            self.executor.set_last_code(cleaned_code)
            self.set_execute_pending(True)

            # 7) UI cleanup
            self._hide_spinner()
            self.set_busy(False)
            self._thread.quit(); self._thread.wait()
            self._worker.deleteLater(); self._thread.deleteLater()

            if hasattr(self, "refresh_chat_highlight"):
                self.refresh_chat_highlight()


        def _on_error(msg: str):
            err_label = self.t.get('llm_request_error', 'Request error')
            err_html = self._render_assistant_html(
                f"<span style='color:#b00'>{err_label} : {self._escape_html(msg)}</span>"
            )
            self._replace_pending(pending_id, err_html)
            self._hide_spinner()
            self.set_busy(False)
            self._thread.quit(); self._thread.wait()
            self._worker.deleteLater(); self._thread.deleteLater()

        # Connexions
        self._thread.started.connect(self._worker.run)
        if hasattr(self._worker, "stream_chunk"):
            self._worker.stream_chunk.connect(_on_chunk)
        self._worker.finished.connect(_on_finished)
        self._worker.error.connect(_on_error)

        # Go
        self._thread.start()


    def handle_execute(self):
        code = self.executor.get_last_code()
        if not code:
            QMessageBox.warning(self, self.t["execution"], self.t["no_code"])
            return

        # Option "vérifier avant d'exécuter" => ouvrir l'éditeur
        if self.settings_manager.get_verify_before_execute():
            dlg = CodeReviewDialog(code, self.t, parent=self)

            # IMPORTANT : l'éditeur s'ouvre au-dessus de l'onglet Assistant
            # (on veut que l'arrière-plan soit l'onglet Assistant)
            self.tabs.setCurrentIndex(0)

            result = dlg.exec_()
            if result != QDialog.Accepted:
                # Annulé/fermé : on conserve le code, on garde Execute allumé,
                # on reste sur Assistant, Debug reste actif et inchangé.
                self.executor.set_last_code(code)           # sûreté
                if hasattr(self, "set_execute_pending"):
                    self.set_execute_pending(True)
                self.tabs.setTabEnabled(1, True)            # Debug actif
                self.tabs.setCurrentIndex(0)                # rester sur Assistant
                return

            # L'utilisateur a validé → on récupère le code modifié
            code = dlg.get_code()

        try:
            # Exécuter (le CodeExecutor gère erreurs/avertissements et notifie handle_execution_error)
            self._last_exec_had_error = False  # reset avant tentative
            self.executor.execute_code(code)

            # Succès sans avertissement/erreur remontée → on nettoie
            if not self._last_exec_had_error:
                self.executor.clear_last_code()
                self.input_text.clear()
                if hasattr(self, "set_execute_pending"):
                    self.set_execute_pending(False)

                # Désactiver + vider Debug et rester sur Assistant
                if hasattr(self, "debug_text"):
                    self.debug_text.clear()
                self.tabs.setTabEnabled(1, False)
                self.tabs.setCurrentIndex(0)

        except Exception:
            # Exception python non gérée par l'executor (rare) :
            if hasattr(self, "set_execute_pending"):
                self.set_execute_pending(False)
            # handle_execution_error fera l'UI Debug; on ne fait rien ici.
            pass


    def handle_execution_error(self, code, error_message):
        self._last_exec_had_error = True
        self.executor.clear_last_code()
        self.set_execute_pending(False)
        # En mode agent l'agent corrige lui-même : ne pas ouvrir l'onglet debug
        if not self.settings_manager.get_agent_mode_enabled():
            self.tabs.setTabEnabled(1, True)
            self.tabs.setCurrentIndex(1)
        self.debug_text.setPlainText(f"{code}\n\n{str(error_message)}")


    def fix_and_execute(self):
        raw_content = self.debug_text.toPlainText().strip()
        if not raw_content:
            QMessageBox.warning(self, self.t["correction"], self.t["no_error"])
            return

        # --- Récup des marqueurs localisés depuis translation.py ---
        err_sep = self.t["error_to_fix"]     # "Erreur :" ou "Error :"
        warn_sep = self.t["warnings"] + " :" # "Avertissements :" ou "Warnings :"

        has_error = err_sep in raw_content
        has_warn  = warn_sep in raw_content

        if not (has_error or has_warn):
            QMessageBox.warning(self, self.t["correction"], self.t["no_error"])
            return

        # --- Découpage selon le type ---
        if has_error:
            code_part, diag_part = raw_content.split(err_sep, 1)
            header      = self.t["error_fix_header"]
            instruction = self.t["error_fix_instruction"]
            diag_label  = err_sep
        else:
            code_part, diag_part = raw_content.split(warn_sep, 1)
            header      = self.t["warn_fix_header"]
            instruction = self.t["warn_fix_instruction"]
            diag_label  = warn_sep

        # --- Prompt localisé complet ---
        prompt = (
            f"{header}\n\n"
            f"{instruction}\n\n"
            f"{self.t['code_to_fix']}:\n\n"
            f"{code_part.strip()}\n\n"
            f"{diag_label} {diag_part.strip()}\n"
        )

        # UI → afficher comme question utilisateur
        self.append_to_conversation("user", prompt)
        if hasattr(self, "btn_fix_and_run"):
            self.btn_fix_and_run.setEnabled(False)
        self.tabs.setCurrentIndex(0)
        pending_id = self._append_pending_assistant()
        self.set_busy(True)

        messages = self.build_messages_for_api(prompt)

        # --- Streaming activé ? ---
        try:
            use_stream = bool(self.settings_manager.get_streaming_enabled())
        except Exception:
            use_stream = bool(self.settings_manager.get("streaming_enabled", False))

        self._thread = QThread(self)
        self._worker = ChatWorker(
            self.agent, prompt, mode="code", lang=self.lang,
            messages=messages, stream=use_stream
        )
        self._worker.moveToThread(self._thread)

        live_buf = {"text": ""}

        def _on_chunk(txt: str):
            live_buf["text"] += (txt or "")
            self._update_stream_pending(pending_id, live_buf["text"], mode="code")

        def _on_finished(fixed_code, usage):
            # 0) Réponse vide / overflow
            if not (fixed_code or "").strip() or self._looks_like_ctx_overflow(fixed_code):
                # pas d'exécution dans ce cas
                try:
                    self.executor.clear_last_code()
                except Exception:
                    pass
                self.set_execute_pending(False)
                self._handle_model_empty_or_overflow(pending_id, mode="fix")
                self._hide_spinner()
                self.set_busy(False)
                if hasattr(self, "btn_fix_and_run"):
                    self.btn_fix_and_run.setEnabled(True)
                self._thread.quit(); self._thread.wait()
                self._worker.deleteLater(); self._thread.deleteLater()
                return

            # 1) Nettoyage code
            cleaned_code = self.clean_code(fixed_code).strip()

            # Si après nettoyage il n'y a plus rien → même traitement que vide
            if not cleaned_code:
                try:
                    self.executor.clear_last_code()
                except Exception:
                    pass
                self.set_execute_pending(False)
                self._handle_model_empty_or_overflow(pending_id, mode="fix")
                self._hide_spinner()
                self.set_busy(False)
                if hasattr(self, "btn_fix_and_run"):
                    self.btn_fix_and_run.setEnabled(True)
                self._thread.quit(); self._thread.wait()
                self._worker.deleteLater(); self._thread.deleteLater()
                return

            # 2) Tokens
            tokens = self.extract_token_count(usage)
            self.total_tokens_used += tokens
            self.settings_manager.set("token_total_since_clear", self.total_tokens_used)
            self.update_status_label()

            # 3) Rendu HTML propre dans le chat (même style que "Envoyer"/"Générer code")
            code_html = f"<pre class='md'><code class='md'>{self._escape_html(cleaned_code)}</code></pre>"

            if hasattr(self, "_wrap_assistant_bubble"):
                # bulle uniforme (sans <p>), tokens via .msg__tokens
                final_html = self._wrap_assistant_bubble(code_html, is_context=True, tokens_used=tokens)
            else:
                # fallback sur le wrapper existant mais SANS injecter <p>
                tmp = self._render_assistant_html(code_html, tokens_used=None)
                if tokens:
                    # ajoute un bloc tokens discret (évite <p>)
                    # si ta bulle n'a pas .msg__body/.msg, on insère simplement à la fin
                    tmp = f"{tmp}<div class='msg__tokens'>⎇ {self.t['token_count']} : {tokens}</div>"
                final_html = tmp

            # 4) Remplacer le pending par le rendu final
            self._replace_pending(pending_id, final_html, keep=False)

            # 5) Historique (HTML + TOK en commentaire)
            saved_content = code_html if not tokens else f"{code_html}<!--TOK:{tokens}-->"
            self.conversation_manager.append("assistant", saved_content)

            # 6) Préparer/Allumer Exécuter (et exécuter)
            self._hide_spinner()
            self.executor.set_last_code(cleaned_code)
            self.set_execute_pending(True)
            self.tabs.setTabEnabled(1, True)
            self.tabs.setCurrentIndex(0)
            self.handle_execute()

            # 7) UI cleanup
            self.set_busy(False)
            if hasattr(self, "btn_fix_and_run"):
                self.btn_fix_and_run.setEnabled(True)
            self._thread.quit(); self._thread.wait()
            self._worker.deleteLater(); self._thread.deleteLater()

            if hasattr(self, "refresh_chat_highlight"):
                self.refresh_chat_highlight()


        def _on_error(msg: str):
            err_html = self._render_assistant_html(f"<span style='color:#b00'>{self._escape_html(msg)}</span>")
            self._replace_pending(pending_id, err_html, keep=False)
            self._hide_spinner()
            self.tabs.setTabEnabled(1, True)
            self.tabs.setCurrentIndex(1)
            self.set_busy(False)
            if hasattr(self, "btn_fix_and_run"):
                self.btn_fix_and_run.setEnabled(True)
            self._thread.quit(); self._thread.wait()
            self._worker.deleteLater(); self._thread.deleteLater()

        self._thread.started.connect(self._worker.run)
        if use_stream and hasattr(self._worker, "stream_chunk"):
            self._worker.stream_chunk.connect(_on_chunk)
        self._worker.finished.connect(_on_finished)
        self._worker.error.connect(_on_error)
        self._thread.start()









    def clean_code(self, code: str) -> str:
        import re, html as _html
        code = (code or "")

        # 1) Extraire l'intérieur d'un <pre> ou <code>
        m = re.search(r'<pre[^>]*>(.*?)</pre>', code, flags=re.IGNORECASE | re.DOTALL)
        if m:
            code = m.group(1)
        else:
            m = re.search(r'<code[^>]*>(.*?)</code>', code, flags=re.IGNORECASE | re.DOTALL)
            if m:
                code = m.group(1)

        # 2) Normaliser les <br> en vrais sauts de ligne
        code = re.sub(r'</?br\s*/?>', '\n', code, flags=re.IGNORECASE)

        # 3) Retirer tout le HTML résiduel
        code = re.sub(r'<[^>]+>', '', code)

        # 4) 🔑 Déséchapper les entités HTML (&quot;, &amp;, etc.)
        code = _html.unescape(code)

        # 5) Supprimer les fences ```
        code = re.sub(r"```(?:\w+)?", "", code)
        code = code.replace("```", "")

        # 6) Élaguer l'intro avant le vrai code
        lines = code.strip().splitlines()
        while lines and not (
            lines[0].strip().startswith(("import", "from", "#", "layer", "Qgs"))
        ):
            lines.pop(0)

        return "\n".join(lines).strip()

    def clear_conversation(self):
        self.conversation_view.clear()
        self.conversation_manager.clear()
        self.total_tokens_used = 0
        self.last_prompt_tokens = 0
        self.last_context_max = 0
        self.settings_manager.set("token_total_since_clear", 0)
        self.update_status_label()
        self._reset_project_context()
        if hasattr(self, "btn_save_process"):
            self.btn_save_process.setVisible(False)

        if hasattr(self, "set_execute_pending"):
            self.set_execute_pending(False)
        if hasattr(self, "executor"):
            self.executor.clear_last_code()

        if hasattr(self, "debug_text"):
            self.debug_text.clear()
        if hasattr(self, "tabs"):
            self.tabs.setTabEnabled(1, False)
            self.tabs.setCurrentIndex(0)
        if hasattr(self, "_last_exec_had_error"):
            self._last_exec_had_error = False
        if hasattr(self, "btn_fix_and_run"):
            self.btn_fix_and_run.setEnabled(True)

        if hasattr(self, "_hide_spinner"):
            try:
                self._hide_spinner()
            except Exception:
                pass

        self.update_status_label()
        if hasattr(self, "refresh_chat_highlight"):
            self.refresh_chat_highlight()

    def open_options(self):
        dialog = OptionsDialog(self.settings_manager)
        try:
            dialog.request_full_reset.connect(self._handle_full_reset)
        except Exception:
            pass
        if dialog.exec_():
            self.lang = self.settings_manager.get_language()
            if self.lang not in ["fr", "en"]:
                self.lang = "fr"
            self.t = get_translations(self.lang)
            if hasattr(self, "executor") and hasattr(self.executor, "update_language"):
                self.executor.update_language(self.lang)
            self.history_turns = int(self.settings_manager.get("history_turns", 0))
            if hasattr(self, "refresh_chat_highlight"):
                self.refresh_chat_highlight()
            self.last_context_max = self.settings_manager.get_project_context_max_tokens()
            self.update_status_label()

            self.setWindowTitle(self.t["dock_title"])
            self.tabs.setTabText(0, self.t["assistant_tab"])
            self.tabs.setTabText(1, self.t["debug_tab"])
            self.btn_send.setText(self.t["send"])
            self.btn_generate.setText(self.t["generate"])
            self.btn_execute.setText(self.t["execute"])
            self.btn_clear.setText(self.t["clear"])
            self.btn_options.setText(self.t["options"])
            self.debug_label.setText(self.t["error_during_exec"])
            self.btn_fix_and_run.setText(self.t["fix_and_run"])
            self.btn_index.setText(self.t["index_project"])
            self.input_text.setPlaceholderText(self.t["message_prompt"])

        self.update_status_label()
        self._apply_agent_mode_ui()

    def _apply_agent_mode_ui(self):
        """Désactive Execute, Générer code et l'onglet Debug quand le mode agent est activé."""
        agent_on = self.settings_manager.get_agent_mode_enabled()
        enabled = not agent_on
        if hasattr(self, "btn_generate"):
            self.btn_generate.setEnabled(enabled)
        if hasattr(self, "btn_execute"):
            self.btn_execute.setEnabled(enabled) 
        if hasattr(self, "btn_index"):
            self.btn_index.setEnabled(enabled)
        # Onglet Debug (index 1) : désactivé en mode agent
        if hasattr(self, "tabs"):
            current = self.tabs.currentIndex()
            self.tabs.setTabEnabled(1, enabled)
            if agent_on and current == 1:
                self.tabs.setCurrentIndex(0)

    def update_status_label(self):
        _mode_key = "mode_remote" if self.settings_manager.get("mode", "local") == "distant" else "mode_local"
        mode = self.t.get(_mode_key, self.settings_manager.get("mode", "local").capitalize())
        model = self.settings_manager.get("model", None) or self.settings_manager.get("model_name", "N/A")

        ctx_part = ""
        prompt_tok = self.last_prompt_tokens
        ctx_max = self.last_context_max
        if prompt_tok and ctx_max:
            pct = min(int(prompt_tok / ctx_max * 100), 100)
            filled = min(pct // 10, 10)
            bar = "█" * filled + "░" * (10 - filled)
            color = "#e74c3c" if pct >= 90 else "#f39c12" if pct >= 75 else "#2ecc71"
            ctx_label = self.t.get("context_usage_label", "Context")
            ctx_part = (
                f" | <b>{ctx_label} :</b> "
                f"<span style='color:{color}'>{bar} {prompt_tok:,}&nbsp;/&nbsp;{ctx_max:,} tokens</span>"
            )

        self.status_label.setText(
            f"<b>{self.t['mode']} :</b> {mode} | "
            f"<b>{self.t['model']} :</b> {model} | "
            f"<b>{self.t['token_count']} :</b> {self.total_tokens_used}"
            + ctx_part
        )
        self.status_label.setToolTip(self.t.get("gauge_tooltip", "") if ctx_part else "")

    @staticmethod
    def _clean_for_llm(content: str) -> str:
        """Retourne le contenu épuré de tout balisage HTML pour l'envoi au LLM."""
        import re, html as _html
        c = content or ""
        # Supprimer le bloc agent-steps complet
        c = re.sub(r"<!--AGENT_STEPS_START-->.*?<!--AGENT_STEPS_END-->", "", c, flags=re.DOTALL)
        # Supprimer les marqueurs de tokens
        c = re.sub(r"<!--TOK:\d+-->", "", c)
        # Supprimer les commentaires HTML restants
        c = re.sub(r"<!--.*?-->", "", c, flags=re.DOTALL)
        # Remplacer <br> et <br/> par newline
        c = re.sub(r"<br\s*/?>", "\n", c, flags=re.IGNORECASE)
        # Supprimer toutes les balises HTML restantes
        c = re.sub(r"<[^>]+>", "", c)
        # Décoder les entités HTML
        c = _html.unescape(c)
        return c.strip()

    def build_messages_for_api(self, new_user_prompt: str):
        turns = max(0, int(self.history_turns))
        history = self.conversation_manager.get_last_turns_messages(turns)
        history = [m for m in history if m.get("role") in ("user", "assistant")]
        history = [
            {**m, "content": self._clean_for_llm(m["content"])} if m.get("role") == "assistant" else m
            for m in history
        ]

        new_clean = (new_user_prompt or "").strip()
        if new_clean:
            if not (history and history[-1].get("role") == "user" and str(history[-1].get("content","")).strip() == new_clean):
                history.append({"role": "user", "content": new_clean})

        if self.settings_manager.get_include_project_context():
            try:
                prj = getattr(self, "_project_snapshot", None)
                if prj is not None:
                    ctx_tokens = max(512, int(self.settings_manager.get_project_context_max_tokens()))
                    js = snapshot_to_json(prj, max_bytes=ctx_tokens * 4)
                    lang = self.settings_manager.get_language()
                    tr = get_translations(lang)
                    history.insert(0, {
                        "role": "system",
                        "content": f"{tr['project_snapshot_intro']}\n```json\n{js}\n```"
                    })
            except Exception:
                pass

        return history

    def render_message_html(self, role: str, content: str, highlight: bool = False) -> str:
        import re
        self._ensure_md_css()
        label = self.t.get("you_prefix", "Vous") if role == "user" else self.t.get("assistant_prefix", "Assistant")

        c = content or ""
        is_already_html = bool(re.match(r"\s*<", c))
        tokens_info = ""
        agent_steps_html = ""

        if is_already_html:
            # Extraire les étapes agent si présentes (sauvegardées comme commentaire HTML)
            m_steps = re.search(r"<!--AGENT_STEPS_START-->(.*?)<!--AGENT_STEPS_END-->", c, re.DOTALL)
            if m_steps:
                agent_steps_html = m_steps.group(1)
                c = c[:m_steps.start()] + c[m_steps.end():]
            m_tok = re.search(r"^(.*)<!--\s*TOK\s*:\s*(\d+)(?::(\d+):(\d+))?\s*-->\s*$", c, flags=re.I | re.S)
            if m_tok:
                c = m_tok.group(1)
                tok_total = int(m_tok.group(2))
                tok_in = int(m_tok.group(3)) if m_tok.group(3) else None
                tok_out = int(m_tok.group(4)) if m_tok.group(4) else None
                tok_label = self.t.get('token_count', 'Tokens')
                if tok_in is not None:
                    tokens_info = f"{tok_label}: {tok_total} (in:{tok_in} / out:{tok_out})"
                else:
                    tokens_info = f"⎇ {tok_label} : {tok_total}"
            body_html = c
        else:
            body_html = self._render_for_feed(c)

        if role == "user":
            return wrap_user(body_html, label=label, context_badge=highlight)
        else:
            return wrap_assistant(body_html, label=label, tokens_info=tokens_info,
                                  agent_steps_html=agent_steps_html, context_badge=highlight)


    
    def _strip_html_for_snippet(self, s: str, limit: int = 140) -> str:
        import re, html as _html
        if not s:
            return ""
        # enlever tags
        s = re.sub(r"<[^>]+>", " ", s)
        # unescape entités, normaliser espaces
        s = _html.unescape(s)
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) > limit:
            s = s[:limit - 1].rstrip() + "…"
        return s

    def _render_context_preview(self, msgs: list) -> str:
        # msgs: liste de dicts {"role": "...", "content": "..."}
        if not msgs:
            return ""
        items = []
        for m in msgs:
            who = self.t.get("you_prefix", "You") if m.get("role") == "user" else self.t.get("assistant_prefix", "Assistant")
            snip = self._strip_html_for_snippet(m.get("content", ""), 160)
            items.append(f"<div class='ctx-item'><div class='who'>{who}</div><div class='snippet'>{snip}</div></div>")
        count = len(msgs)
        return (
            f"<div class='ctx-preview'>"
            f"  <div class='ctx-preview__title'>"
            f"    <span>{self.t.get('context_chat','Context sent')}</span>"
            f"    <span class='count'>{self.t.get('context_last_messages_chat').format(count=count)}</span>"
            f"  </div>"
            f"  {''.join(items)}"
            f"</div>"
        )


    def refresh_chat_highlight(self):
        self._ensure_md_css()
        all_msgs = list(self.conversation_manager.get_messages())
        to_send = self.conversation_manager.get_last_turns_messages(self.history_turns)

        # Associer les indices des messages marqués "à envoyer"
        idx_to_send = set()
        i_all, i_send = len(all_msgs) - 1, len(to_send) - 1
        while i_all >= 0 and i_send >= 0:
            if (all_msgs[i_all].get("role") == to_send[i_send].get("role") and
                all_msgs[i_all].get("content") == to_send[i_send].get("content")):
                idx_to_send.add(i_all)
                i_all -= 1
                i_send -= 1
            else:
                i_all -= 1

        # Rendu messages
        html_msgs = "".join(
            self.render_message_html(m.get("role"), m.get("content", ""), (i in idx_to_send))
            for i, m in enumerate(all_msgs)
        )

        # Rendu panneau de preview (dans l'ordre d'apparition)
        ctx_msg_list = [all_msgs[i] for i in range(len(all_msgs)) if i in idx_to_send]
        preview = self._render_context_preview(ctx_msg_list)

        self.conversation_view.setHtml(preview + html_msgs)
        self.conversation_view.moveCursor(QTextCursor.End)


    def set_busy(self, busy: bool):
        """
        Désactive/active les boutons et affiche/masque le spinner.
        """
        # boutons susceptibles d'exister
        widgets = [
            getattr(self, "btn_send", None),
            getattr(self, "btn_generate", None),
            getattr(self, "btn_execute", None),
            getattr(self, "btn_clear", None),
            getattr(self, "btn_options", None),
            getattr(self, "btn_index", None),
        ]
        for w in widgets:
            if w is not None:
                w.setEnabled(not busy)

        # curseur + spinner
        self.setCursor(Qt.BusyCursor if busy else Qt.ArrowCursor)
        if busy:
            self._show_spinner()
        else:
            self._hide_spinner()
            # Réappliquer les restrictions du mode agent après réactivation des boutons
            if hasattr(self, "_apply_agent_mode_ui"):
                self._apply_agent_mode_ui()


    def _handle_full_reset(self):
        try:
            self.conversation_manager.clear()
            if hasattr(self.conversation_manager, "purge_on_disk"):
                self.conversation_manager.purge_on_disk()
        except Exception:
            pass

        self.total_tokens_used = 0
        self.settings_manager.set_token_total_since_clear(0)

        if hasattr(self, "_project_snapshot"):
            self._project_snapshot = None

        try:
            self.conversation_view.clear()
            if hasattr(self, "refresh_chat_highlight"):
                self.refresh_chat_highlight()
        except Exception:
            pass

        try:
            self.debug_text.clear()
            self.tabs.setTabEnabled(1, False)
            self.tabs.setCurrentIndex(0)
        except Exception:
            pass

        self.update_status_label()

    def _reset_project_context(self):
        if hasattr(self, "_project_snapshot"):
            self._project_snapshot = None
        try:
            cache_path = getattr(self, "_project_snapshot_file", None)
            if not cache_path:
                cache_path = self.settings_manager.get("project_snapshot_file", "")
            if cache_path:
                if os.path.exists(cache_path):
                    os.remove(cache_path)
                self._project_snapshot_file = None
                self.settings_manager.set("project_snapshot_file", "")
        except Exception:
            pass

    def _escape_html(self, text: str) -> str:
        import html as _html
        return _html.escape(text or "").replace("\r\n", "\n")

    def _looks_like_ctx_overflow(self, txt: str) -> bool:
        """Heuristique: repère les messages d'overflow de contexte renvoyés par LM Studio / modèles OSS."""
        if not txt:
            return True  # si c'est vide, on traitera comme overflow/erreur modèle
        t = txt.lower()
        keys = [
            "reached context length",
            "context length of",
            "max context",
            "context window",
            "too many tokens",
            "exceeds the context",  # variantes
            "overflow",             # variantes génériques
        ]
        return any(k in t for k in keys)

    def _handle_model_empty_or_overflow(self, pending_id: str, mode: str):
        """
        Rend un message d'erreur lisible + n'active PAS le bouton Exécuter
        si on était en génération de code/correction.
        """
        title = self.t.get("err_ctx_overflow_title", "Limite de contexte atteinte")
        body  = self.t.get(
            "err_ctx_overflow_body",
            "La requête est trop longue pour ce modèle. Réduisez le contexte (messages, index projet) "
            "ou choisissez un modèle avec une fenêtre de contexte plus grande."
        )
        tips  = self.t.get(
            "err_ctx_overflow_tips",
            "Astuce : diminuez le nombre de messages de contexte dans les options, "
            "désactivez le snapshot de projet, ou relancez avec un modèle à plus grande mémoire."
        )

        html = (
            f"<div style='color:#b00;'>"
            f"<b>⚠ {self._escape_html(title)}</b><br>{self._escape_html(body)}<br>"
            f"<i style='color:#999'>{self._escape_html(tips)}</i>"
            f"</div>"
        )

        # Assure-toi que le bouton Exécuter reste ÉTEINT pour les flux 'code' ou 'fix'
        if mode in ("code", "fix"):
            try:
                self.executor.clear_last_code()
            except Exception:
                pass
            if hasattr(self, "set_execute_pending"):
                self.set_execute_pending(False)

        err_html = self._render_assistant_html(html, tokens_used=None)
        self._replace_pending(pending_id, err_html, keep=False)
        self._hide_spinner()
        self.set_busy(False)

    
    def _update_stream_pending(self, pending_id: str, text: str, mode: str = "chat"):
        """
        Update ONLY the existing pending block using the exact QTextCursor range
        we stored at insertion time. This never appends new lines.
        """
        try:
            if pending_id not in self._pending_ranges:
                # As a last resort, append (but this should not happen)
                self.conversation_view.append(
                    f"<br><b>🤖 {self.t.get('assistant_label','Assistant')} : </b>{self._render_stream_content(mode, text)}"
                )
                self.conversation_view.moveCursor(QTextCursor.End)
                return

            start, end = self._pending_ranges[pending_id]
            cur = self.conversation_view.textCursor()
            cur.setPosition(start)
            cur.setPosition(end, QTextCursor.KeepAnchor)

            safe_inner = self._render_stream_content(mode, text)
            inner = f"<span class='stream-{pending_id}'>{safe_inner}</span>"
            bubble = self._wrap_assistant_bubble(inner, is_context=True, tokens_used=None)
            new_wrapper = f"<div data-pending='{pending_id}' id='pending-{pending_id}' style='opacity:0.95;'>{bubble}</div>"


            cur.insertHtml(new_wrapper)
            # after replacement, cursor now points to end of the new wrapper
            new_end = cur.position()
            self._pending_ranges[pending_id] = (start, new_end)

            # make it feel realtime
            self.conversation_view.setTextCursor(cur)
            self.conversation_view.moveCursor(QTextCursor.End)
            QCoreApplication.processEvents()
        except Exception:
            # very safe fallback: append (won't crash, but could duplicate)
            self.conversation_view.append(
                f"<b>🤖 {self.t.get('assistant_label','Assistant')} : </b>{self._render_stream_content(mode, text)}"
            )
            self.conversation_view.moveCursor(QTextCursor.End)


    def _ensure_md_css(self):
        """Installe le thème visuel unifié du chat (une seule fois)."""
        if getattr(self, "_md_css_done", False):
            return
        try:
            self.conversation_view.document().setDefaultStyleSheet(CHAT_CSS)
        except Exception:
            pass
        self._md_css_done = True

    def _render_for_feed(self, content: str) -> str:
        import re
        c = content or ""

        # --- 1) Ancien footer en <p> déjà présent à la fin → on garde (compat ascendante)
        m_p = re.search(r"^(.*?)(<p[^>]*>\s*⎇[\s\S]*?</p>\s*)$", c, flags=re.I | re.S)
        if m_p:
            body, footer_html = m_p.group(1), m_p.group(2)
            # Si body n'est pas encore rendu, on le rend
            if not re.search(r"class=['\"]md['\"]", body, flags=re.I):
                body = self._render_markdownish_chat(body)
            return body + footer_html

        # --- 2) Nouveau footer stocké en commentaire <!--TOK:n--> → on fabrique une ligne visible
        m_tok = re.search(r"^(.*)<!--\s*TOK\s*:\s*(\d+)\s*-->\s*$", c, flags=re.I | re.S)
        if m_tok:
            body, tok = m_tok.group(1), int(m_tok.group(2))
            # Si body est déjà rendu (contient class="md"), on n'y retouche pas
            if not re.search(r"class=['\"]md['\"]", body, flags=re.I):
                body = self._render_markdownish_chat(body)
            return f"{body}<div class='msg-footer'>⎇ {self.t['token_count']} : {tok}</div>"

        # --- 3) S'il est déjà rendu (class="md"), on rend tel quel
        if re.search(r"<(table|pre|code|ul|ol|blockquote|h[1-6])\b[^>]*class=['\"]md['\"]", c, flags=re.I):
            return c

        # --- 4) Sinon rendu normal (markdown→HTML)
        return self._render_markdownish_chat(c)



    
    def _normalize_text(self, s: str) -> str:
        return _normalize_text_fn(s)

    def _render_markdownish_chat(self, text: str) -> str:
        self._ensure_md_css()
        return _render_markdownish_chat_fn(text)

    def _md_table_block_to_html(self, lines):
        return _md_table_block_to_html_fn(lines)
