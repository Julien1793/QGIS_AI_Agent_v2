import os
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QMessageBox, QSpinBox, QCheckBox, QFileDialog
)
from qgis.PyQt.QtCore import pyqtSignal
import requests
from ..utils.translation import get_translations


class OptionsDialog(QDialog):
    request_full_reset = pyqtSignal()
    def __init__(self, settings_manager):
        super().__init__()
        self.settings = settings_manager

        # Language and translations
        self.lang = self.settings.get_language()
        if self.lang not in ["fr", "en"]:
            self.lang = "fr"
        self.t = get_translations(self.lang)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # --- Connection mode (local / remote) ---
        self.mode_layout = QHBoxLayout()
        self.mode_label = QLabel()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["local", "distant"])
        self.mode_combo.setCurrentText(self.settings.get_mode())
        self.mode_combo.currentTextChanged.connect(self.update_visibility)
        self.mode_layout.addWidget(self.mode_label)
        self.mode_layout.addWidget(self.mode_combo)
        self.layout.addLayout(self.mode_layout)

        # --- Interface language ---
        self.lang_layout = QHBoxLayout()
        self.lang_label = QLabel()
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["French", "English"])
        self.lang_combo.setCurrentText("French" if self.lang == "fr" else "English")
        self.lang_combo.currentTextChanged.connect(self.change_language)
        self.lang_layout.addWidget(self.lang_label)
        self.lang_layout.addWidget(self.lang_combo)
        self.layout.addLayout(self.lang_layout)

        # --- Conversation history depth ---
        self.history_layout = QHBoxLayout()
        self.history_label = QLabel()
        self.history_spin = QSpinBox()
        self.history_spin.setRange(0, 50)  # 0 = no history sent to the API
        self.history_spin.setValue(int(self.settings.get("history_turns", 0)))
        self.history_layout.addWidget(self.history_label)
        self.history_layout.addWidget(self.history_spin)
        self.layout.addLayout(self.history_layout)

        # --- SSE streaming mode ---
        self.chk_stream = QCheckBox()
        try:
            self.chk_stream.setChecked(self.settings.get_streaming_enabled())
        except Exception:
            self.chk_stream.setChecked(False)
        self.layout.addWidget(self.chk_stream)



        # --- QGIS project context snapshot ---
        self.ctx_layout = QHBoxLayout()
        self.ctx_check = QCheckBox()
        self.ctx_check.setChecked(self.settings.get_include_project_context())
        self.ctx_max_label = QLabel()
        self.ctx_max_spin = QSpinBox()
        self.ctx_max_spin.setRange(8, 1024)  # 8 KB to 1 MB
        self.ctx_max_spin.setValue(self.settings.get_project_context_max_kb())
        self.ctx_layout.addWidget(self.ctx_check)
        self.ctx_layout.addWidget(self.ctx_max_label)
        self.ctx_layout.addWidget(self.ctx_max_spin)
        self.layout.addLayout(self.ctx_layout)


        # --- API endpoint URL ---
        self.url_layout = QHBoxLayout()
        self.url_label = QLabel()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("http://localhost:1234/v1/chat/completions")
        self.url_input.setText(self.settings.get_api_url())
        self.url_layout.addWidget(self.url_label)
        self.url_layout.addWidget(self.url_input)
        self.layout.addLayout(self.url_layout)

        # --- Model identifier ---
        self.model_layout = QHBoxLayout()
        self.model_label = QLabel()
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("mistral, llama3, gpt-4...")
        self.model_input.setText(self.settings.get_model())
        self.model_layout.addWidget(self.model_label)
        self.model_layout.addWidget(self.model_input)
        self.layout.addLayout(self.model_layout)

        # --- API key (remote mode only) ---
        self.key_layout = QHBoxLayout()
        self.key_label = QLabel()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("sk-...")
        self.api_key_input.setText(self.settings.get_api_key())
        self.key_layout.addWidget(self.key_label)
        self.key_layout.addWidget(self.api_key_input)
        self.layout.addLayout(self.key_layout)

        # --- Request/response trace export (debug) ---
        self.trace_checkbox = QCheckBox()
        self.trace_checkbox.setChecked(self.settings.get_export_traces())
        self.layout.addWidget(self.trace_checkbox)

        # Export directory path selector
        self.trace_path_layout = QHBoxLayout()
        self.trace_path_label = QLabel()
        self.trace_path_edit = QLineEdit()
        self.trace_path_browse = QPushButton()
        self.trace_path_edit.setText(self.settings.get_trace_dir())
        self.trace_path_browse.clicked.connect(self.browse_trace_dir)
        self.trace_path_layout.addWidget(self.trace_path_label)
        self.trace_path_layout.addWidget(self.trace_path_edit)
        self.trace_path_layout.addWidget(self.trace_path_browse)
        self.layout.addLayout(self.trace_path_layout)


        # --- Code review dialog before execution ---
        self.verify_checkbox = QCheckBox()
        self.verify_checkbox.setChecked(self.settings.get_verify_before_execute())
        self.layout.addWidget(self.verify_checkbox)

        # --- Agent mode (function calling with native QGIS tools) ---
        self.chk_agent_mode = QCheckBox()
        self.chk_agent_mode.setChecked(self.settings.get_agent_mode_enabled())
        self.layout.addWidget(self.chk_agent_mode)

        self.agent_iter_layout = QHBoxLayout()
        self.agent_iter_label = QLabel()
        self.agent_iter_spin = QSpinBox()
        self.agent_iter_spin.setRange(1, 20)
        self.agent_iter_spin.setValue(self.settings.get_agent_max_iterations())
        self.agent_iter_layout.addWidget(self.agent_iter_label)
        self.agent_iter_layout.addWidget(self.agent_iter_spin)
        self.layout.addLayout(self.agent_iter_layout)

        self.chk_agent_show_steps = QCheckBox()
        self.chk_agent_show_steps.setChecked(self.settings.get_agent_show_steps())
        self.layout.addWidget(self.chk_agent_show_steps)

        self.chk_canvas_capture = QCheckBox()
        self.chk_canvas_capture.setChecked(self.settings.get_canvas_capture_enabled())
        self.layout.addWidget(self.chk_canvas_capture)

        # --- Windows CA bundle ---
        self.chk_windows_ca = QCheckBox()
        self.chk_windows_ca.setChecked(self.settings.get_use_windows_ca_bundle())
        self.chk_windows_ca.toggled.connect(self.update_visibility)
        self.layout.addWidget(self.chk_windows_ca)

        self.ca_encoding_layout = QHBoxLayout()
        self.ca_encoding_label = QLabel()
        self.ca_encoding_input = QLineEdit()
        self.ca_encoding_input.setText(self.settings.get_ca_bundle_cert_encoding())
        self.ca_encoding_layout.addWidget(self.ca_encoding_label)
        self.ca_encoding_layout.addWidget(self.ca_encoding_input)
        self.layout.addLayout(self.ca_encoding_layout)

        # --- Action buttons ---
        self.btn_layout = QHBoxLayout()
        self.btn_test = QPushButton()
        self.btn_save = QPushButton()
        self.btn_cancel = QPushButton()
        self.btn_reset = QPushButton() 
        self.btn_layout.addWidget(self.btn_test)
        self.btn_layout.addWidget(self.btn_save)
        self.btn_layout.addWidget(self.btn_cancel)
        self.btn_layout.addWidget(self.btn_reset)
        self.layout.addLayout(self.btn_layout)

        # Button signal connections
        self.btn_test.clicked.connect(self.test_connection)
        self.btn_save.clicked.connect(self.save_settings)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_reset.clicked.connect(self.on_click_reset)

        # Connect here, not in update_visibility, to avoid creating duplicate connections on each call
        self.trace_checkbox.toggled.connect(self.update_visibility)

        # Populate all labels and apply initial visibility rules
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
        self.mode_label.setText(self.t["mode"])
        self.lang_label.setText(self.t["language"])
        self.history_label.setText(self.t["history_count"])
        self.url_label.setText(self.t["url"])
        self.model_label.setText(self.t["model"])
        self.key_label.setText(self.t["api_key"])
        self.btn_test.setText(self.t["test"])
        self.btn_save.setText(self.t["save"])
        self.btn_cancel.setText(self.t["cancel"])
        self.btn_reset.setText(self.t["reset"])
        self.verify_checkbox.setText(self.t["verify_before_execute"])
        self.ctx_check.setText(
            self.t.get("include_project_context", "Inclure le contexte projet")
        )
        self.ctx_max_label.setText(
            self.t.get("project_context_max_kb", "Taille max (Ko) :")
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

        self.chk_windows_ca.setText(self.t.get("use_windows_ca_bundle", "Utiliser les certificats Windows (CA bundle)"))
        self.chk_windows_ca.setToolTip(self.t.get("use_windows_ca_bundle_hint", ""))
        self.ca_encoding_label.setText(self.t.get("ca_bundle_cert_encoding", "Encodage des certificats :"))
        self.ca_encoding_input.setToolTip(self.t.get("ca_bundle_cert_encoding_hint", ""))



    def change_language(self):
        self.refresh_texts()

    def update_visibility(self):
        is_distant = self.mode_combo.currentText() == "distant"
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

    # -------------------------
    # Actions
    # -------------------------
    def test_connection(self):
        url = self.url_input.text().strip()
        model = (self.model_input.text().strip() or "gpt-4")
        headers = {}

        if self.mode_combo.currentText() == "distant":
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
        self.settings.set_mode(self.mode_combo.currentText())
        # Use the same key that MainDock and ConversationManager read
        self.settings.set("history_turns", int(self.history_spin.value()))
        self.settings.set_api_url(self.url_input.text().strip())
        self.settings.set_model(self.model_input.text().strip())
        self.settings.set_api_key(self.api_key_input.text().strip())
        self.settings.set_verify_before_execute(self.verify_checkbox.isChecked())
        self.settings.set_include_project_context(self.ctx_check.isChecked())
        self.settings.set_project_context_max_kb(int(self.ctx_max_spin.value()))
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
        self.mode_combo.setCurrentText("local")
        self.history_spin.setValue(0)
        self.url_input.setText(self.settings.get_api_url())  # retombe sur défaut
        self.model_input.setText(self.settings.get_model())
        self.api_key_input.setText("")
        if hasattr(self, "verify_checkbox"):
            self.verify_checkbox.setChecked(False)

        QMessageBox.information(self, self.t["reset"], self.t["reset_done"])

