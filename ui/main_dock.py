# ui/main_dock.py

import os
import re
import uuid
import html
from qgis.PyQt.QtWidgets import (QSplitter,
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QTabWidget, QMessageBox, QLabel, QTextBrowser,
    QDialog, QPlainTextEdit, QDialogButtonBox, QApplication,
)
import threading
from qgis.PyQt.QtCore import Qt, QCoreApplication, QRect, QSize, QThread, QObject, pyqtSignal, pyqtSlot
from qgis.PyQt.QtGui import QTextCursor, QPixmap, QPainter, QTextFormat, QMovie

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


# ---- HTML helpers for streaming/non-stream ----

def _looks_like_html(s: str) -> bool:
    import re as _re
    """Lightweight heuristic: detect HTML containing list/table/blockquote/code elements."""
    return bool(_re.search(r"<(ul|ol|li|table|thead|tbody|tr|th|td|pre|code|blockquote|h[1-6]|p)\b", s or "", _re.I))

def _pass_through_html_with_md_classes(html: str) -> str:
    """
    Pass through LLM-generated HTML while injecting class='md' on block elements
    that our CSS styles (ul/ol/table/pre/code/blockquote/h1..h6) when no class is already set.
    Also applies minimal sanitization: strips <script> tags and inline event handlers.
    """
    import re
    # 0) minimal sanitization
    html = re.sub(r"(?is)<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", html)
    html = re.sub(r"\son[a-zA-Z]+\s*=", " data-on-removed=", html)

    # 1) normalize <br/>
    html = re.sub(r"</?br\s*/?>", "<br>", html, flags=re.I)

    # 2) inject class='md' where absent
    for tag in ("ul", "ol", "table", "pre", "code", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"):
        html = re.sub(rf"<{tag}\b(?![^>]*\bclass=)", rf"<{tag} class='md'", html, flags=re.I)

    return html


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


class ChatWorker(QObject):
    finished = pyqtSignal(str, object)   # (response, usage)
    error = pyqtSignal(str)
    stream_chunk = pyqtSignal(str)       # NEW

    def __init__(self, agent, prompt, mode, lang, messages=None, stream=False):
        super().__init__()
        self.agent = agent
        self.prompt = prompt
        self.mode = mode
        self.lang = lang
        self.messages = messages
        self.stream = stream

    def run(self):
        try:
            if self.stream:
                # pass a callback -> route to signal
                def _on_chunk(txt):
                    self.stream_chunk.emit(txt)
                resp, usage = self.agent.chat(self.prompt, mode=self.mode, lang=self.lang,
                                              messages=self.messages, on_stream=_on_chunk)
            else:
                resp, usage = self.agent.chat(self.prompt, mode=self.mode, lang=self.lang,
                                              messages=self.messages)
            self.finished.emit(resp, usage)
        except Exception as e:
            self.error.emit(str(e))



class AgentWorker(QObject):
    """Runs the agent loop in a dedicated worker thread.
    Blocking LLM calls execute in the worker thread.
    QGIS tool execution is delegated back to the main thread via a Qt signal.
    """
    step_event = pyqtSignal(object)       # event dict → on_step UI callback
    tool_request = pyqtSignal(str, object)  # (tool_name, args) → thread principal
    finished = pyqtSignal(str, int)       # (final_text, total_tokens)
    error_signal = pyqtSignal(str)

    def __init__(self, agent_loop, user_prompt, snapshot_json, history_messages=None):
        super().__init__()
        self.agent_loop = agent_loop
        self.user_prompt = user_prompt
        self.snapshot_json = snapshot_json
        self.history_messages = history_messages or []
        self._tool_event = threading.Event()
        self._tool_result = None

    @pyqtSlot()
    def run(self):
        def tool_executor(tool_name, args):
            self._tool_event.clear()
            self._tool_result = None
            self.tool_request.emit(tool_name, dict(args))
            # Block the worker thread until the main thread posts the result
            if not self._tool_event.wait(timeout=120):
                return {"success": False, "tool": tool_name,
                        "error": "timeout: no response from main thread"}
            return self._tool_result or {"success": False, "tool": tool_name,
                                         "error": "no result"}

        try:
            final_text, tokens = self.agent_loop.run(
                user_prompt=self.user_prompt,
                snapshot_json=self.snapshot_json,
                on_step=lambda e: self.step_event.emit(e),
                tool_executor=tool_executor,
                history_messages=self.history_messages,
            )
            self.finished.emit(final_text, tokens or 0)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_signal.emit(str(e))

    def receive_tool_result(self, result: dict):
        """Appelé depuis le thread principal pour renvoyer le résultat d'un outil."""
        self._tool_result = result
        self._tool_event.set()


class StreamWorker(QObject):
    partial = pyqtSignal(str)
    finished = pyqtSignal(str, object)
    error = pyqtSignal(str)
    not_supported = pyqtSignal(str)

    def __init__(self, agent, prompt, mode, lang, messages=None):
        super().__init__()
        self.agent = agent
        self.prompt = prompt
        self.mode = mode
        self.lang = lang
        self.messages = messages

    def run(self):
        import requests, json
        try:
            api_url, headers, payload = self.agent.build_request(
                self.prompt, mode=self.mode, lang=self.lang, messages=self.messages
            )
            payload_stream = dict(payload)
            payload_stream["stream"] = True

            resp = requests.post(api_url, json=payload_stream, headers=headers, stream=True, timeout=300,
                                 verify=self.agent.settings.get_ssl_verify())

            if resp.status_code >= 400:
                self.error.emit(f"HTTP {resp.status_code}: {resp.text}")
                return

            buf = ""
            usage = None
            got_any = False

            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                s = raw.strip()
                if not s.startswith("data:"):
                    continue

                data = s[5:].strip()
                if data == "[DONE]":
                    break

                try:
                    obj = json.loads(data)
                except Exception:
                    continue

                if "error" in obj:
                    msg = obj["error"].get("message") if isinstance(obj["error"], dict) else str(obj["error"])
                    self.error.emit(msg or "stream error")
                    return

                ch = (obj.get("choices") or [{}])[0]
                delta = ch.get("delta", {})
                piece = delta.get("content") or ch.get("message", {}).get("content") or ""
                if piece:
                    buf += piece
                    got_any = True
                    self.partial.emit(buf)

                if "usage" in obj:
                    usage = obj["usage"]

            if not got_any:
                self.not_supported.emit("no-chunk")
                return

            self.finished.emit(buf, (usage or {}))

        except Exception as e:
            self.error.emit(str(e))


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
                # Current footer <!--TOK:n-->
                if not matches:
                    matches = re.findall(r"<!--\s*TOK\s*:\s*(\d+)\s*-->\s*$", content, flags=re.IGNORECASE)
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
        def _on_agent_finished(final_text, total_tokens):
            # 6) Replace the placeholder with the final complete bubble
            safe_body = self._render_markdownish_chat(final_text)
            tokens_text = (
                f"{self.t.get('token_count', 'Tokens')}: {total_tokens}"
                if total_tokens else ""
            )

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
                saved += f"<!--TOK:{total_tokens}-->"
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
            _on_agent_finished(final_text, 0)

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
        self._agent_thread.started.connect(self._agent_worker.run)
        self._agent_thread.finished.connect(self._agent_thread.deleteLater)

        self._agent_thread.start()

    @pyqtSlot(str, object)
    def _on_agent_tool_request(self, tool_name: str, args: object):
        """Execute a QGIS tool on the main thread and post the result back to the worker."""
        result = self.agent_loop._execute_tool(tool_name, args)
        if hasattr(self, "_agent_worker") and self._agent_worker:
            self._agent_worker.receive_tool_result(result)

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
        dlg = ProcessRunDialog(process_dict, self.agent_loop, self)
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
        self.status_label.setText(
            f"<b>{self.t['mode']} :</b> {mode} | "
            f"<b>{self.t['model']} :</b> {model} | "
            f"<b>{self.t['token_count']} :</b> {self.total_tokens_used}"
        )

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
            m_tok = re.search(r"^(.*)<!--\s*TOK\s*:\s*(\d+)\s*-->\s*$", c, flags=re.I | re.S)
            if m_tok:
                c = m_tok.group(1)
                tokens_info = f"⎇ {self.t.get('token_count', 'Tokens')} : {int(m_tok.group(2))}"
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
        import html as _html, re, json
        if not s:
            return ""

        # ——— Désinfection "fil de fer" du protocole LLM ———
        # 0) supprime les balises <|xxx|>
        s = re.sub(r"<\|\w+\|>", "", s)
        # 1) supprime labels du type to=developer / to=final
        s = re.sub(r"\bto\s*=\s*[\w\-/]+", "", s, flags=re.I)
        # 2) supprime le mot isolé "json" juste avant un objet { ... }
        s = re.sub(r"\bjson\b(?=\s*\{)", "", s, flags=re.I)
        # 3) si on a vu ces marqueurs, essaie d'extraire un JSON final { ... } → "response|content|message|text"
        if "<|" in s or "to=" in s:
            m = re.search(r"(\{[^{}]*\}|\{[\s\S]*\})\s*$", s, flags=re.S)
            if m:
                raw = m.group(1)
                try:
                    obj = json.loads(raw)
                    if isinstance(obj, dict):
                        for k in ("response", "content", "message", "text"):
                            v = obj.get(k)
                            if isinstance(v, str) and v.strip():
                                s = s[:m.start(1)].strip() + (" " if s[:m.start(1)].strip() else "") + v
                                break
                except Exception:
                    pass

        # ——— Normalisation existante ———
        s = _html.unescape(s)
        s = (s
            .replace("\u00A0", " ")
            .replace("\u202F", " ")
            .replace("\u2009", " ")
            .replace("\u2011", "-"))
        s = re.sub(r"[ \t]{2,}", " ", s)
        return s



    def _render_markdownish_chat(self, text: str) -> str:
        """
        Final (non-stream) renderer for chat responses:
        - fenced code blocks   -> <pre><code>
        - tables (markdown)    -> <table>
        - headings (#..######) -> <h1>..</h1>
        - lists (-, *, 1.)     -> <ul>/<ol>
        - task list [-]        -> [ ] / [x]
        - blockquotes          -> <blockquote>
        - hr                   -> <hr>
        - inline: **bold**, *italic*, `code`, links
        Everything else: escape + <br>.
        """
        import re, html as _html
        self._ensure_md_css()
        src = text or ""
        src = self._normalize_text(src)
        # --- FAST PATH: si le LLM a déjà renvoyé du HTML (listes/tables/etc.),
        # on le garde tel quel (avec une sanitation légère) et on injecte class='md'
        # pour bénéficier du CSS existant.
        if _looks_like_html(src):
            return _pass_through_html_with_md_classes(src)


        # ——— helper commun : applique **bold**/__bold__, *italic*/_italic_ robustement ———
        def _apply_strong_em(s: str) -> str:
            # Ne pas toucher aux marqueurs échappés \* ou \_
            # 1) BOLD: **…** ou __…__  (on tolère espaces fines/insécables)
            s = re.sub(r"(?<!\\)(\*\*|__)\s*([^\s].*?[^\s])\s*\1", r"<b>\2</b>", s, flags=re.DOTALL)
            # 2) ITALIC: *…* ou _…_ mais pas quand c'est du bold (évite ***…*** / ___…___)
            s = re.sub(r"(?<!\\)(?<!\*)\*(?!\*)\s*([^\s].*?[^\s])\s*(?<!\*)\*(?!\*)", r"<i>\1</i>", s, flags=re.DOTALL)
            s = re.sub(r"(?<!\\)(?<!_)_(?!_)\s*([^\s].*?[^\s])\s*(?<!_)_(?!_)", r"<i>\1</i>", s, flags=re.DOTALL)
            return s

        # ---------------- helpers ----------------

        def _protect_codeblocks(s: str):
            """Protège <pre>…</pre> et code fences ```...``` en placeholders."""
            blocks = []

            # 1) <pre>…</pre>
            def _protect_html_pre(m):
                blocks.append(m.group(0))
                return f"\uE100PRE{len(blocks)-1}\uE100"

            s = re.sub(r"<pre\b[\s\S]*?</pre>", _protect_html_pre, s, flags=re.I)

            # 2) ```fences```
            def _protect_fence(m):
                lang = m.group(1) or ""
                inner = m.group(2) or ""
                inner = _html.escape(inner)
                html = f"<pre class='md'><code class='md'>{inner}</code></pre>"
                blocks.append(html)
                return f"\uE100PRE{len(blocks)-1}\uE100"

            s = re.sub(r"```(\w+)?\s*\n([\s\S]*?)\n```", _protect_fence, s, flags=re.MULTILINE)
            return s, blocks

        def _restore_codeblocks(s: str, blocks):
            return re.sub(r"\uE100PRE(\d+)\uE100", lambda m: blocks[int(m.group(1))], s)

        def _inline_pass(s: str) -> str:
            """Bold/italic/code/links + <br>, sans toucher aux placeholders de blocs."""
            import re, html as _html

            # 0) normaliser <br> échappés et espaces “exotiques”
            s = self._normalize_text(s)
            s = (s.replace("&lt;br&gt;", "<br>")
                .replace("&lt;br/&gt;", "<br>")
                .replace("&lt;br /&gt;", "<br>"))
            
            # PROTÈGE les <br> déjà présents pour éviter qu'ils deviennent &lt;br&gt;
            BR_TOKEN = "\uE000BR\uE000"
            s = s.replace("<br>", BR_TOKEN)

            # 1) protéger `code` inline pour ne PAS appliquer gras/italique dedans
            code_spans = []
            def _protect_inline_code(m):
                code_spans.append(m.group(1))
                return f"\uE101CODE{len(code_spans)-1}\uE101"
            s = re.sub(r"`([^`]+)`", _protect_inline_code, s)

            # 2) protéger aussi les placeholders de blocs (déjà posés ailleurs) avant escape
            PH = "\uE001PH"
            s = s.replace("\uE100", PH + "A").replace("\uE101", PH + "B")

            # 3) ÉCHAPPER le reste (après protections)
            s = _html.escape(s).replace("\r\n", "\n")

            # 4) déprotéger les marqueurs de blocs (on n'échappe plus après ça)
            s = s.replace(PH + "A", "\uE100").replace(PH + "B", "\uE101")

            # 5) **bold** puis *italic* (hors placeholders)
            s = _apply_strong_em(s)

            # 6) Linkification APRÈS escape (sinon les <a> seraient ré-échappés)
            #    a) Markdown [label](url)
            def _mk_link(m):
                label = m.group(1)           # déjà échappé au #3
                url   = _html.escape(m.group(2))
                return f"<a href='{url}'>{label}</a>"
            s = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", _mk_link, s)

            #    b) Autolink brut
            def _auto(m):
                u = m.group(1)
                return f"<a href='{_html.escape(u)}'>{_html.escape(u)}</a>"
            s = re.sub(r"(?<!['\">])(https?://[^\s<]+)", _auto, s)

            # 7) restaurer les `code` inline (le contenu est échappé une seule fois)
            def _restore_code(m):
                idx = int(m.group(1))
                return f"<code class='md'>{_html.escape(code_spans[idx])}</code>"
            s = re.sub(r"\uE101CODE(\d+)\uE101", _restore_code, s)

            # 8) \n -> <br>, mais pas s'il est tout seul au début/fin
            s = s.strip("\n")         # enlève les \n initiaux et finaux
            s = s.replace("\n", "<br>")

            # RESTAURE les <br> originaux
            s = s.replace(BR_TOKEN, "<br>")

            return s
        
        def _render_blockquote(block: str) -> str:
            inner = "\n".join([re.sub(r"^\s*>\s?", "", ln) for ln in block.splitlines()])
            return f"<blockquote class='md'>{_inline_pass(inner)}</blockquote>"


        # ---------------------------------------------------------------

        # Ne court-circuite que si c'est DÉJÀ notre HTML md rendu,
        # sinon on peut encore avoir du markdown (tables, listes…) à convertir
        if re.search(r"<(table|pre|code|ul|ol|blockquote|h[1-6])\b[^>]*class=['\"]md['\"]", src, re.I):
            safe, blocks = _protect_codeblocks(src)
            safe = _inline_pass(safe)
            return _restore_codeblocks(safe, blocks)


        # Protéger les blocs code (HTML + fences) d'abord
        work, blocks = _protect_codeblocks(src)

        # Découper en paragraphes par doubles sauts
        paragraphs = re.split(r"\n{2,}", work)
        out = []

        for para in paragraphs:
            p = para.strip()
            if not p:
                continue

            lines = p.splitlines()

            # 0) hr ?
            if all(re.match(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", ln) for ln in lines):
                out.append("<hr>")
                continue

            # 1) tableau markdown ?
            def is_sep_row(s: str) -> bool:
                return bool(re.match(r"^\s*\|?\s*:?-{3,}.*\|\s*(?:\:?-{3,}\:?\s*\|.*)*$", s.strip()))

            i = 0
            emitted_table = False
            while i < len(lines):
                if ("|" in lines[i] and i+1 < len(lines) and "|" in lines[i+1] and is_sep_row(lines[i+1])):
                    j = i + 2
                    while j < len(lines) and "|" in lines[j]:
                        j += 1
                    tbl_lines = lines[i:j]
                    out.append(self._md_table_block_to_html(tbl_lines))
                    emitted_table = True
                    i = j
                else:
                    i += 1
            if emitted_table:
                continue

            # 2) blockquote (un ou plusieurs > consécutifs)
            if all(ln.strip().startswith(">") for ln in lines):
                out.append(_render_blockquote(p))
                continue

            # 3) heading ATX (paragraphe mono-ligne)
            m_h = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", p)
            if m_h:
                lvl = min(6, len(m_h.group(1)))
                inner = _inline_pass(m_h.group(2).strip())
                out.append(f"<h{lvl} class='md'>{inner}</h{lvl}>")
                continue

            # 4) liste ordonnée simple 1. 2. ...
            if all(re.match(r"^\s*\d+\.\s+.+", ln) for ln in lines) and len(lines) > 1:
                items = []
                for ln in lines:
                    item = re.sub(r"^\s*\d+\.\s+", "", ln).strip()
                    items.append(f"<li>{_inline_pass(item)}</li>")
                out.append("<ol class='md'>" + "".join(items) + "</ol>")
                continue

            # 5) liste à puces (- ou *)
            if all((ln.strip().startswith("- ") or ln.strip().startswith("* ")) for ln in lines) and len(lines) > 1:
                items = []
                for ln in lines:
                    it = ln.strip()[2:]
                    # cases à cocher
                    m_task = re.match(r"^\[( |x|X)\]\s+(.*)$", it)
                    if m_task:
                        checked = (m_task.group(1).lower() == "x")
                        label = _inline_pass(m_task.group(2))
                        cb = "<input type='checkbox' disabled " + ("checked>" if checked else ">")
                        items.append(f"<li>{cb} {label}</li>")
                    else:
                        items.append(f"<li>{_inline_pass(it)}</li>")
                out.append("<ul class='md'>" + "".join(items) + "</ul>")
                continue

            # 6) contenu mixte ou texte libre — traitement ligne par ligne
            # Gère les paragraphes mélangeant ### headings, listes et texte
            def _process_mixed(lines_):
                parts = []
                i = 0
                while i < len(lines_):
                    ln = lines_[i]
                    # Heading ATX ?
                    m_hx = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", ln.rstrip())
                    if m_hx:
                        lvl = min(6, len(m_hx.group(1)))
                        parts.append(
                            f"<h{lvl} class='md'>{_inline_pass(m_hx.group(2).strip())}</h{lvl}>"
                        )
                        i += 1
                        continue
                    # Liste à puces (- ou *) ?
                    if re.match(r"^\s*[-*]\s+", ln):
                        items = []
                        while i < len(lines_) and re.match(r"^\s*[-*]\s+", lines_[i]):
                            it = re.sub(r"^\s*[-*]\s+", "", lines_[i])
                            m_task = re.match(r"^\[( |x|X)\]\s+(.*)$", it)
                            if m_task:
                                checked = m_task.group(1).lower() == "x"
                                cb = "<input type='checkbox' disabled " + (
                                    "checked>" if checked else ">")
                                items.append(f"<li>{cb} {_inline_pass(m_task.group(2))}</li>")
                            else:
                                items.append(f"<li>{_inline_pass(it)}</li>")
                            i += 1
                        parts.append("<ul class='md'>" + "".join(items) + "</ul>")
                        continue
                    # Liste ordonnée ?
                    if re.match(r"^\s*\d+\.\s+", ln):
                        items = []
                        while i < len(lines_) and re.match(r"^\s*\d+\.\s+", lines_[i]):
                            it = re.sub(r"^\s*\d+\.\s+", "", lines_[i]).strip()
                            items.append(f"<li>{_inline_pass(it)}</li>")
                            i += 1
                        parts.append("<ol class='md'>" + "".join(items) + "</ol>")
                        continue
                    # Texte libre
                    parts.append(_inline_pass(ln))
                    i += 1
                return "<br>".join(p for p in parts if p)

            out.append(_process_mixed(lines))

        final_html = "<br>".join(out)
        return _restore_codeblocks(final_html, blocks)






    def _md_table_block_to_html(self, lines):
        r"""
        - Convert a block of markdown table lines to HTML <table>.
        - split robuste (ignore \| et pipes dans `code`)
        - normalise le nombre de colonnes...
        """

        import re, html as _html

        def _apply_strong_em_cell(s: str) -> str:
            # BOLD: **…** ou __…__ (tolère espaces fines/insécables, ignore \** et \__)
            s = re.sub(r"(?<!\\)(\*\*|__)\s*([^\s].*?[^\s])\s*\1", r"<b>\2</b>", s, flags=re.DOTALL)
            # ITALIC: *…* ou _…_ (évite ***…***/___…___, ignore \* et \_)
            s = re.sub(r"(?<!\\)(?<!\*)\*(?!\*)\s*([^\s].*?[^\s])\s*(?<!\*)\*(?!\*)", r"<i>\1</i>", s, flags=re.DOTALL)
            s = re.sub(r"(?<!\\)(?<!_)_(?!_)\s*([^\s].*?[^\s])\s*(?<!_)_(?!_)", r"<i>\1</i>", s, flags=re.DOTALL)
            return s

        def smart_split(row: str):
            s = row.strip()
            if s.startswith("|"): s = s[1:]
            if s.endswith("|"): s = s[:-1]

            cells, buf = [], []
            in_code = False
            esc = False
            i = 0
            while i < len(s):
                ch = s[i]
                if esc:
                    buf.append(ch); esc = False
                elif ch == "\\":
                    esc = True
                elif ch == "`":
                    in_code = not in_code
                    buf.append(ch)
                elif ch == "|" and not in_code:
                    cells.append("".join(buf).strip()); buf = []
                else:
                    buf.append(ch)
                i += 1
            cells.append("".join(buf).strip())
            return cells

        if len(lines) < 2:
            return _html.escape("\n".join(lines))

        header = smart_split(lines[0])
        sep    = smart_split(lines[1])
        body   = [smart_split(r) for r in lines[2:]] if len(lines) > 2 else []

        # ncols = max de toutes les lignes
        ncols = max(len(header), len(sep), max((len(r) for r in body), default=0))

        def normalize(row):
            r = list(row)
            if len(r) < ncols:
                r += [""] * (ncols - len(r))
            elif len(r) > ncols:
                r = r[:ncols]
            return r

        header = normalize(header)
        sep    = normalize(sep)
        body   = [normalize(r) for r in body]

        # alignements à partir de la ligne de séparation
        aligns = []
        for cell in sep:
            c = cell.replace(" ", "")
            if c.startswith(":") and c.endswith(":"): aligns.append("center")
            elif c.endswith(":"): aligns.append("right")
            elif c.startswith(":"): aligns.append("left")
            else: aligns.append(None)
        if len(aligns) < ncols:
            aligns += [None] * (ncols - len(aligns))
        elif len(aligns) > ncols:
            aligns = aligns[:ncols]

        def render_cell(cell, idx, tag="td"):
            import html as _html, re
            txt_raw = (cell or "").strip()

            # 0) Dé-échappe tout de suite les entités HTML (&quot; -> ", &amp; -> & …)
            txt_raw = _html.unescape(txt_raw)

            # 1) normaliser les variantes de <br>
            txt_raw = (txt_raw
                    .replace("<br/>", "<br>")
                    .replace("<br />", "<br>")
                    .replace("&lt;br/&gt;", "<br>")
                    .replace("&lt;br /&gt;", "<br>")
                    .replace("&lt;br&gt;", "<br>"))

            # 2) remettre les pipes échappés \| comme texte
            txt_raw = txt_raw.replace("\\|", "|")

            # 3) normalisation Unicode légère (NBSP, hyphen…)
            txt_raw = self._normalize_text(txt_raw)

            # 4) protéger <br> pendant l'escape
            BR_TOKEN = "\uE000BR\uE000"
            txt_raw = txt_raw.replace("<br>", BR_TOKEN)

            # 5) escape HTML (puis on fera gras/italique hors `code`)
            esc = _html.escape(txt_raw)

            # 6) protéger les segments `code` pour ne pas y appliquer gras/italique
            code_spans = []
            def _protect_code(m):
                code_spans.append(m.group(1))
                return f"\uE002CODE{len(code_spans)-1}\uE002"
            esc = re.sub(r"`([^`]+)`", _protect_code, esc)

            # 7) **bold** puis *italic* dans les cellules (hors `code`)
            esc = _apply_strong_em_cell(esc)

            # 8) restaurer les code spans
            def _restore_code(m):
                idxc = int(m.group(1))
                return f"<code class='md'>{code_spans[idxc]}</code>"
            esc = re.sub(r"\uE002CODE(\d+)\uE002", _restore_code, esc)

            # 9) rétablir <br>
            esc = esc.replace(BR_TOKEN, "<br>")

            a = aligns[idx] if idx < len(aligns) else None
            style = f" style='text-align:{a};'" if a else ""
            return f"<{tag}{style}>{esc}</{tag}>"

        ths = "".join(render_cell(h, i, "th") for i, h in enumerate(header))
        trs = []
        for row in body:
            tds = "".join(render_cell(v, i, "td") for i, v in enumerate(row))
            trs.append(f"<tr>{tds}</tr>")

        return f"<table class='md'><thead><tr>{ths}</tr></thead><tbody>{''.join(trs)}</tbody></table>"






