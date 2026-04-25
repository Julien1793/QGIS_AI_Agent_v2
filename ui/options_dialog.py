import os
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QMessageBox, QSpinBox, QCheckBox, QFileDialog,
    QTabWidget, QGroupBox, QWidget
)
from qgis.PyQt.QtCore import pyqtSignal, QUrl
from qgis.PyQt.QtGui import QDesktopServices
import requests
from ..utils.translation import get_translations


class OptionsDialog(QDialog):
    request_full_reset = pyqtSignal()
    def __init__(self, settings_manager):
        super().__init__()
        self.settings = settings_manager

        self.lang = self.settings.get_language()
        if self.lang not in ["fr", "en"]:
            self.lang = "fr"
        self.t = get_translations(self.lang)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)

        # ── Tab 1 : Connexion ─────────────────────────────────────────────
        tab_conn = QWidget()
        tab_conn_layout = QVBoxLayout()
        tab_conn.setLayout(tab_conn_layout)

        self.mode_layout = QHBoxLayout()
        self.mode_label = QLabel()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("", "local")
        self.mode_combo.addItem("", "distant")
        saved_mode = self.settings.get_mode()
        idx = self.mode_combo.findData(saved_mode)
        self.mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.mode_combo.currentIndexChanged.connect(self.update_visibility)
        self.mode_layout.addWidget(self.mode_label)
        self.mode_layout.addWidget(self.mode_combo)
        tab_conn_layout.addLayout(self.mode_layout)

        self.url_layout = QHBoxLayout()
        self.url_label = QLabel()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("http://localhost:1234/v1/chat/completions")
        self.url_input.setText(self.settings.get_api_url())
        self.url_layout.addWidget(self.url_label)
        self.url_layout.addWidget(self.url_input)
        tab_conn_layout.addLayout(self.url_layout)

        self.model_layout = QHBoxLayout()
        self.model_label = QLabel()
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("mistral, llama3, gpt-4...")
        self.model_input.setText(self.settings.get_model())
        self.model_layout.addWidget(self.model_label)
        self.model_layout.addWidget(self.model_input)
        tab_conn_layout.addLayout(self.model_layout)

        self.key_layout = QHBoxLayout()
        self.key_label = QLabel()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("sk-...")
        self.api_key_input.setText(self.settings.get_api_key())
        self.key_layout.addWidget(self.key_label)
        self.key_layout.addWidget(self.api_key_input)
        tab_conn_layout.addLayout(self.key_layout)

        test_btn_row = QHBoxLayout()
        self.btn_test = QPushButton()
        test_btn_row.addStretch()
        test_btn_row.addWidget(self.btn_test)
        tab_conn_layout.addLayout(test_btn_row)

        self.ca_group = QGroupBox()
        ca_group_layout = QVBoxLayout()
        self.chk_windows_ca = QCheckBox()
        self.chk_windows_ca.setChecked(self.settings.get_use_windows_ca_bundle())
        self.chk_windows_ca.toggled.connect(self.update_visibility)
        ca_group_layout.addWidget(self.chk_windows_ca)
        self.ca_encoding_layout = QHBoxLayout()
        self.ca_encoding_label = QLabel()
        self.ca_encoding_input = QLineEdit()
        self.ca_encoding_input.setText(self.settings.get_ca_bundle_cert_encoding())
        self.ca_encoding_layout.addWidget(self.ca_encoding_label)
        self.ca_encoding_layout.addWidget(self.ca_encoding_input)
        ca_group_layout.addLayout(self.ca_encoding_layout)
        self.ca_group.setLayout(ca_group_layout)
        tab_conn_layout.addWidget(self.ca_group)

        tab_conn_layout.addStretch()
        self.tab_widget.addTab(tab_conn, "")

        # ── Tab 2 : LLM ───────────────────────────────────────────────────
        tab_llm = QWidget()
        tab_llm_layout = QVBoxLayout()
        tab_llm.setLayout(tab_llm_layout)

        self.chk_stream = QCheckBox()
        try:
            self.chk_stream.setChecked(self.settings.get_streaming_enabled())
        except Exception:
            self.chk_stream.setChecked(False)
        tab_llm_layout.addWidget(self.chk_stream)

        self.history_layout = QHBoxLayout()
        self.history_label = QLabel()
        self.history_spin = QSpinBox()
        self.history_spin.setRange(0, 50)
        self.history_spin.setValue(int(self.settings.get("history_turns", 0)))
        self.history_layout.addWidget(self.history_label)
        self.history_layout.addWidget(self.history_spin)
        tab_llm_layout.addLayout(self.history_layout)

        self.agent_tokens_layout = QHBoxLayout()
        self.agent_tokens_label = QLabel()
        self.agent_tokens_spin = QSpinBox()
        self.agent_tokens_spin.setRange(512, 65536)
        self.agent_tokens_spin.setSingleStep(512)
        self.agent_tokens_spin.setValue(self.settings.get_agent_max_tokens())
        self.agent_tokens_layout.addWidget(self.agent_tokens_label)
        self.agent_tokens_layout.addWidget(self.agent_tokens_spin)
        tab_llm_layout.addLayout(self.agent_tokens_layout)

        self.ctx_layout = QHBoxLayout()
        self.ctx_check = QCheckBox()
        self.ctx_check.setChecked(self.settings.get_include_project_context())
        self.ctx_max_label = QLabel()
        self.ctx_max_spin = QSpinBox()
        self.ctx_max_spin.setRange(512, 524288)
        self.ctx_max_spin.setSingleStep(1024)
        self.ctx_max_spin.setValue(self.settings.get_project_context_max_tokens())
        self.ctx_layout.addWidget(self.ctx_check)
        self.ctx_layout.addWidget(self.ctx_max_label)
        self.ctx_layout.addWidget(self.ctx_max_spin)
        tab_llm_layout.addLayout(self.ctx_layout)

        tab_llm_layout.addStretch()
        self.tab_widget.addTab(tab_llm, "")

        # ── Tab 3 : Agent ─────────────────────────────────────────────────
        tab_agent = QWidget()
        tab_agent_layout = QVBoxLayout()
        tab_agent.setLayout(tab_agent_layout)

        self.chk_agent_mode = QCheckBox()
        self.chk_agent_mode.setChecked(self.settings.get_agent_mode_enabled())
        tab_agent_layout.addWidget(self.chk_agent_mode)

        self.agent_iter_layout = QHBoxLayout()
        self.agent_iter_label = QLabel()
        self.agent_iter_spin = QSpinBox()
        self.agent_iter_spin.setRange(1, 20)
        self.agent_iter_spin.setValue(self.settings.get_agent_max_iterations())
        self.agent_iter_layout.addWidget(self.agent_iter_label)
        self.agent_iter_layout.addWidget(self.agent_iter_spin)
        tab_agent_layout.addLayout(self.agent_iter_layout)

        self.chk_agent_show_steps = QCheckBox()
        self.chk_agent_show_steps.setChecked(self.settings.get_agent_show_steps())
        tab_agent_layout.addWidget(self.chk_agent_show_steps)

        self.chk_canvas_capture = QCheckBox()
        self.chk_canvas_capture.setChecked(self.settings.get_canvas_capture_enabled())
        tab_agent_layout.addWidget(self.chk_canvas_capture)

        tab_agent_layout.addStretch()
        self.tab_widget.addTab(tab_agent, "")

        # ── Tab 4 : Interface ─────────────────────────────────────────────
        tab_iface = QWidget()
        tab_iface_layout = QVBoxLayout()
        tab_iface.setLayout(tab_iface_layout)

        self.lang_layout = QHBoxLayout()
        self.lang_label = QLabel()
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["French", "English"])
        self.lang_combo.setCurrentText("French" if self.lang == "fr" else "English")
        self.lang_combo.currentTextChanged.connect(self.change_language)
        self.lang_layout.addWidget(self.lang_label)
        self.lang_layout.addWidget(self.lang_combo)
        tab_iface_layout.addLayout(self.lang_layout)

        self.verify_checkbox = QCheckBox()
        self.verify_checkbox.setChecked(self.settings.get_verify_before_execute())
        tab_iface_layout.addWidget(self.verify_checkbox)

        self.trace_checkbox = QCheckBox()
        self.trace_checkbox.setChecked(self.settings.get_export_traces())
        tab_iface_layout.addWidget(self.trace_checkbox)

        self.trace_path_layout = QHBoxLayout()
        self.trace_path_label = QLabel()
        self.trace_path_edit = QLineEdit()
        self.trace_path_browse = QPushButton()
        self.trace_path_edit.setText(self.settings.get_trace_dir())
        self.trace_path_browse.clicked.connect(self.browse_trace_dir)
        self.trace_path_layout.addWidget(self.trace_path_label)
        self.trace_path_layout.addWidget(self.trace_path_edit)
        self.trace_path_layout.addWidget(self.trace_path_browse)
        tab_iface_layout.addLayout(self.trace_path_layout)

        tab_iface_layout.addStretch()
        self.tab_widget.addTab(tab_iface, "")

        # ── Boutons globaux ───────────────────────────────────────────────
        self.btn_layout = QHBoxLayout()
        self.btn_help = QPushButton()
        self.btn_save = QPushButton()
        self.btn_cancel = QPushButton()
        self.btn_reset = QPushButton()
        self.btn_layout.addWidget(self.btn_help)
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.btn_save)
        self.btn_layout.addWidget(self.btn_cancel)
        self.btn_layout.addWidget(self.btn_reset)
        self.layout.addLayout(self.btn_layout)

        self.btn_test.clicked.connect(self.test_connection)
        self.btn_help.clicked.connect(self.open_help)
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_reset.clicked.connect(self.on_click_reset)

        # Connect here, not in update_visibility, to avoid duplicate connections
        self.trace_checkbox.toggled.connect(self.update_visibility)
        self.chk_agent_mode.toggled.connect(self.update_visibility)

        self.refresh_texts()
        self.update_visibility()


    # --- Windows CA bundle refresh ---
    def _refresh_ca_bundle(self):
        cert_enc = self.ca_encoding_input.text().strip()
        if not cert_enc:
            QMessageBox.warning(
                self, self.t.get("error", "Erreur"),
                self.t.get("ca_bundle_encoding_empty", "Le champ d'encodage des certificats est vide.")
            )
            return False
        try:
            from ..core.cert_manager import refresh_ca_bundle
            plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path, count = refresh_ca_bundle(plugin_dir, cert_encoding_filter=cert_enc)
            self.settings.set_ca_bundle_path(path)
            QMessageBox.information(
                self, self.t.get("success", "Succès"),
                self.t.get("ca_bundle_refreshed", "CA bundle mis à jour ({count} certificats exportés).").format(count=count)
            )
            return True
        except Exception as e:
            QMessageBox.critical(
                self, self.t.get("error", "Erreur"),
                self.t.get("ca_bundle_error", "Erreur lors de la mise à jour du CA bundle : {}").format(str(e))
            )
            return False

    # --- Trace export directory browser ---
    def browse_trace_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, 
            self.t.get("choose_folder", "Choisir un dossier")
        )
        if d:
            self.trace_path_edit.setText(d)

    # -------------------------
    # UI event handlers
    # -------------------------
    def refresh_texts(self):
        self.lang = "fr" if self.lang_combo.currentText() == "French" else "en"
        self.t = get_translations(self.lang)

        self.setWindowTitle(self.t["dock_title"])

        self.tab_widget.setTabText(0, self.t.get("tab_connection", "Connexion"))
        self.tab_widget.setTabText(1, self.t.get("tab_llm", "LLM"))
        self.tab_widget.setTabText(2, self.t.get("tab_agent", "Agent"))
        self.tab_widget.setTabText(3, self.t.get("tab_interface", "Interface"))
        self.ca_group.setTitle(self.t.get("ca_bundle_group", "Certificats réseau (avancé)"))

        self.mode_label.setText(self.t["mode"])
        self.mode_combo.setItemText(0, self.t.get("mode_local", "Local"))
        self.mode_combo.setItemText(1, self.t.get("mode_remote", "Distant"))
        self.lang_label.setText(self.t["language"])
        self.history_label.setText(self.t["history_count"])
        self.url_label.setText(self.t["url"])
        self.model_label.setText(self.t["model"])
        self.key_label.setText(self.t["api_key"])
        self.btn_test.setText(self.t["test"])
        self.btn_help.setText(self.t.get("help", "? Help"))
        self.btn_save.setText(self.t["save"])
        self.btn_cancel.setText(self.t["cancel"])
        self.btn_reset.setText(self.t["reset"])
        self.verify_checkbox.setText(self.t["verify_before_execute"])
        self.ctx_check.setText(
            self.t.get("include_project_context", "Inclure le contexte projet")
        )
        self.ctx_max_label.setText(
            self.t.get("project_context_max_tokens", "Tokens contexte (entrée) :")
        )
        self.trace_checkbox.setText(self.t.get("export_traces", "Exporter les requêtes (debug)"))
        self.trace_path_label.setText(self.t.get("trace_dir", "Dossier d'export :"))
        self.trace_path_browse.setText(self.t.get("browse", "Parcourir…"))

        self.chk_stream.setText(self.t["streaming_mode"])
        self.chk_stream.setToolTip(self.t.get("streaming_hint", ""))

        # Mode Agent
        self.chk_agent_mode.setText(self.t["agent_mode"])
        self.chk_agent_mode.setToolTip(self.t.get("agent_mode_hint", ""))
        self.agent_iter_label.setText(self.t["agent_max_iterations"])
        self.agent_iter_spin.setToolTip(self.t.get("agent_max_iterations_hint", ""))
        self.chk_agent_show_steps.setText(self.t["agent_show_steps"])
        self.chk_agent_show_steps.setToolTip(self.t.get("agent_show_steps_hint", ""))
        self.chk_canvas_capture.setText(self.t.get("canvas_capture_enabled", "Capture du canvas (vérification visuelle)"))
        self.chk_canvas_capture.setToolTip(self.t.get("canvas_capture_enabled_hint", ""))
        self.agent_tokens_label.setText(self.t.get("agent_max_tokens", "Tokens max (réponse) :"))
        self.agent_tokens_spin.setToolTip(self.t.get("agent_max_tokens_hint", ""))

        self.chk_windows_ca.setText(self.t.get("use_windows_ca_bundle", "Utiliser les certificats Windows (CA bundle)"))
        self.chk_windows_ca.setToolTip(self.t.get("use_windows_ca_bundle_hint", ""))
        self.ca_encoding_label.setText(self.t.get("ca_bundle_cert_encoding", "Encodage des certificats :"))
        self.ca_encoding_input.setToolTip(self.t.get("ca_bundle_cert_encoding_hint", ""))



    def change_language(self):
        self.refresh_texts()

    def update_visibility(self):
        is_distant = self.mode_combo.currentData() == "distant"
        # API key is only needed for remote mode
        self.key_label.setVisible(is_distant)
        self.api_key_input.setVisible(is_distant)

        trace_on = self.trace_checkbox.isChecked()
        self.trace_path_label.setEnabled(trace_on)
        self.trace_path_edit.setEnabled(trace_on)
        self.trace_path_browse.setEnabled(trace_on)

        ca_on = self.chk_windows_ca.isChecked()
        self.ca_encoding_label.setVisible(ca_on)
        self.ca_encoding_input.setVisible(ca_on)

        # Agent mode requires project context — force the checkbox on and lock it
        agent_on = self.chk_agent_mode.isChecked()
        if agent_on:
            self.ctx_check.setChecked(True)
            self.ctx_check.setEnabled(False)
        else:
            self.ctx_check.setEnabled(True)

    # -------------------------
    # Actions
    # -------------------------
    def open_help(self):
        QDesktopServices.openUrl(QUrl(
            "https://github.com/Julien1793/QGIS_AI_Agent_v2/blob/master/README.md#configuration"
        ))

    def test_connection(self):
        url = self.url_input.text().strip()
        model = (self.model_input.text().strip() or "gpt-4")
        headers = {}

        if self.mode_combo.currentData() == "distant":
            key = self.api_key_input.text().strip()
            if key:
                headers["Authorization"] = f"Bearer {key}"

        if not url:
            QMessageBox.warning(self, self.t["error"], self.t["url_required"])
            return

        try:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}]
            }
            response = requests.post(url, json=payload, headers=headers, timeout=10,
                                     verify=self.settings.get_ssl_verify())
            response.raise_for_status()

            # Some backends echo the model name in the response; use it to auto-fill the model field
            try:
                response_json = response.json()
                if isinstance(response_json, dict) and "model" in response_json:
                    self.model_input.setText(str(response_json["model"]))
            except Exception:
                pass

            QMessageBox.information(self, self.t["success"], self.t["connection_ok"])
        except Exception as e:
            QMessageBox.critical(self, self.t["error"], self.t["connection_failed"].format(str(e)))

    def save_settings(self):
        lang = "fr" if self.lang_combo.currentText() == "French" else "en"
        self.settings.set_language(lang)
        self.settings.set_mode(self.mode_combo.currentData())
        # Use the same key that MainDock and ConversationManager read
        self.settings.set("history_turns", int(self.history_spin.value()))
        self.settings.set_api_url(self.url_input.text().strip())
        self.settings.set_model(self.model_input.text().strip())
        self.settings.set_api_key(self.api_key_input.text().strip())
        self.settings.set_verify_before_execute(self.verify_checkbox.isChecked())
        self.settings.set_include_project_context(self.ctx_check.isChecked())
        self.settings.set_project_context_max_tokens(int(self.ctx_max_spin.value()))
        export_on = self.trace_checkbox.isChecked()
        self.settings.set_export_traces(export_on)

        path = self.trace_path_edit.text().strip()
        if export_on:
            if not path:
                QMessageBox.warning(self, self.t.get("error", "Erreur"),
                                    self.t.get("trace_dir_required", "Veuillez choisir un dossier d'export pour les traces."))
                return
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, self.t.get("error", "Erreur"),
                                     self.t.get("trace_dir_invalid", "Impossible d'utiliser ce dossier : {}").format(str(e)))
                return
        self.settings.set_trace_dir(path if export_on else "")
        self.settings.set_streaming_enabled(self.chk_stream.isChecked())

        # Agent mode settings
        self.settings.set_agent_mode_enabled(self.chk_agent_mode.isChecked())
        self.settings.set_agent_max_iterations(int(self.agent_iter_spin.value()))
        self.settings.set_agent_show_steps(self.chk_agent_show_steps.isChecked())
        self.settings.set_canvas_capture_enabled(self.chk_canvas_capture.isChecked())
        self.settings.set_agent_max_tokens(int(self.agent_tokens_spin.value()))

        # Windows CA bundle
        ca_enabled = self.chk_windows_ca.isChecked()
        self.settings.set_use_windows_ca_bundle(ca_enabled)
        cert_enc = self.ca_encoding_input.text().strip()
        self.settings.set_ca_bundle_cert_encoding(cert_enc)
        if ca_enabled:
            self._refresh_ca_bundle()

        self.accept()

    def on_click_reset(self):
        # Ask for confirmation before wiping all settings
        res = QMessageBox.question(
            self,
            self.t["reset"],
            self.t["reset_confirm"],
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return

        # 1) Clear all stored settings
        try:
            self.settings.clear_all()
        except Exception:
            pass

        # 2) Signal MainDock to purge conversation history, token counter, snapshot, and debug tab
        self.request_full_reset.emit()

        # 3) Reset the Options UI to visible defaults
        self.lang_combo.setCurrentText("French")
        self.mode_combo.setCurrentIndex(self.mode_combo.findData("local"))
        self.history_spin.setValue(0)
        self.url_input.setText(self.settings.get_api_url())  # retombe sur défaut
        self.model_input.setText(self.settings.get_model())
        self.api_key_input.setText("")
        if hasattr(self, "verify_checkbox"):
            self.verify_checkbox.setChecked(False)

        QMessageBox.information(self, self.t["reset"], self.t["reset_done"])

