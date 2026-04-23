import os
from qgis.PyQt.QtCore import QSettings

class SettingsManager:
    def __init__(self):
        self.settings = QSettings()
        # All plugin settings are stored under this prefix to avoid collisions with other QGIS settings.
        self._prefix = "ai_assistant"

    # ---------- Internal helpers ----------
    def _k(self, key: str) -> str:
        """Build the namespaced QSettings key for a given setting name."""
        return f"{self._prefix}/{key}"

    # ---------- Core read/write operations ----------
    def get(self, key, default=None):
        return self.settings.value(self._k(key), default)

    def set(self, key, value):
        self.settings.setValue(self._k(key), value)

    def get_int(self, key, default=0):
        val = self.settings.value(self._k(key), default)
        try:
            return int(val)
        except Exception:
            return default

    def remove(self, key: str):
        self.settings.remove(self._k(key))

    def clear_all(self):
        self.settings.beginGroup(self._prefix)
        self.settings.remove("")   # supprime tout le groupe
        self.settings.endGroup()
        self.settings.sync()       # force l’écriture sur disque

    def sync(self):
        """Force QSettings to flush pending writes to disk."""
        self.settings.sync()

    # ---------- Settings accessors ----------
    # Language
    def get_language(self):
        return self.get("language", "fr")

    def set_language(self, lang_code):
        self.set("language", lang_code)

    # API endpoint URL
    def get_api_url(self):
        return self.get("api_url", "http://localhost:1234/v1/chat/completions")

    def set_api_url(self, url):
        self.set("api_url", url)

    # Connection mode: "local" (LM Studio/Ollama) or "distant" (OpenAI/OpenRouter/etc.)
    def get_mode(self):
        return self.get("mode", "local")

    def set_mode(self, mode):
        self.set("mode", mode)

    # Model identifier sent in every API request
    def get_model(self):
        return self.get("model", "mistral")

    def set_model(self, model):
        self.set("model", model)

    # Display name for the model (optional, shown in the status bar)
    def get_model_name(self):
        return self.get("model_name", "")

    def set_model_name(self, name):
        self.set("model_name", name)

    # API key (used for remote mode only)
    def get_api_key(self):
        return self.get("api_key", "")

    def set_api_key(self, key):
        self.set("api_key", key)

    # Number of recent conversation turns to include in each API request (0 = no history)
    def get_history_turns(self):
        return self.get_int("history_turns", 0)

    def set_history_turns(self, n: int):
        self.set("history_turns", int(n))

    # Cumulative token count persisted across sessions (reset on conversation clear)
    def get_token_total_since_clear(self):
        return self.get_int("token_total_since_clear", 0)

    def set_token_total_since_clear(self, n: int):
        self.set("token_total_since_clear", int(n))

    # Custom system prompt override (if empty, the default translation key is used)
    def get_system_prompt(self):
        return self.get("system_prompt", "")

    def set_system_prompt(self, txt: str):
        self.set("system_prompt", txt or "")

    # Whether to show a code review dialog before executing generated code
    def get_verify_before_execute(self) -> bool:
        val = self.get("verify_before_execute", False)
        s = str(val).strip().lower()
        return s in ("1", "true", "yes", "on")

    def set_verify_before_execute(self, enabled: bool):
        self.set("verify_before_execute", bool(enabled))

    # QGIS project context: include a JSON snapshot of the open project in each request
    def get_include_project_context(self) -> bool:
        val = self.get("include_project_context", False)
        s = str(val).strip().lower()
        return s in ("1", "true", "yes", "on")

    def set_include_project_context(self, enabled: bool):
        self.set("include_project_context", bool(enabled))

    def get_project_context_max_tokens(self) -> int:
        return self.get_int("project_context_max_tokens", 32768)

    def set_project_context_max_tokens(self, n: int):
        self.set("project_context_max_tokens", int(n))

    # Request trace export: write each API request/response pair to a JSON file for debugging
    def get_export_traces(self) -> bool:
        val = self.get("export_traces", False)
        s = str(val).strip().lower()
        return s in ("1", "true", "yes", "on")

    def set_export_traces(self, enabled: bool):
        self.set("export_traces", bool(enabled))

    def get_trace_dir(self) -> str:
        return self.get("trace_dir", "")

    def set_trace_dir(self, path: str):
        self.set("trace_dir", path or "")

    # --- Streaming (SSE) ---
    def get_streaming_enabled(self) -> bool:
        val = self.get("streaming_enabled", False)
        s = str(val).strip().lower()
        return s in ("1", "true", "yes", "on")

    def set_streaming_enabled(self, enabled: bool):
        self.set("streaming_enabled", bool(enabled))

    # --- Agent mode (function calling with native QGIS tools) ---
    def get_agent_mode_enabled(self) -> bool:
        val = self.get("agent_mode_enabled", False)
        s = str(val).strip().lower()
        return s in ("1", "true", "yes", "on")

    def set_agent_mode_enabled(self, enabled: bool):
        self.set("agent_mode_enabled", bool(enabled))

    def get_canvas_capture_enabled(self) -> bool:
        val = self.get("canvas_capture_enabled", True)
        s = str(val).strip().lower()
        return s in ("1", "true", "yes", "on")

    def set_canvas_capture_enabled(self, enabled: bool):
        self.set("canvas_capture_enabled", bool(enabled))

    def get_agent_max_iterations(self) -> int:
        return self.get_int("agent_max_iterations", 8)

    def set_agent_max_iterations(self, n: int):
        self.set("agent_max_iterations", int(n))

    def get_agent_show_steps(self) -> bool:
        val = self.get("agent_show_steps", True)
        s = str(val).strip().lower()
        return s in ("1", "true", "yes", "on")

    def set_agent_show_steps(self, enabled: bool):
        self.set("agent_show_steps", bool(enabled))

    def get_agent_max_tokens(self) -> int:
        return self.get_int("agent_max_tokens", 8192)

    def set_agent_max_tokens(self, n: int):
        self.set("agent_max_tokens", int(n))

    # --- Custom processes ---
    def get_processes_folder(self) -> str:
        import os
        default = os.path.join(os.path.expanduser("~"), "qgis_ai_processes")
        return self.get("processes_folder", default)

    def set_processes_folder(self, path: str):
        self.set("processes_folder", path or "")

    # --- Windows CA bundle (on-premise HTTPS certificate fix) ---
    def get_use_windows_ca_bundle(self) -> bool:
        val = self.get("use_windows_ca_bundle", False)
        return str(val).strip().lower() in ("1", "true", "yes", "on")

    def set_use_windows_ca_bundle(self, enabled: bool):
        self.set("use_windows_ca_bundle", bool(enabled))

    def get_ca_bundle_cert_encoding(self) -> str:
        return self.get("ca_bundle_cert_encoding", "")

    def set_ca_bundle_cert_encoding(self, encoding: str):
        self.set("ca_bundle_cert_encoding", encoding)

    def get_ca_bundle_path(self) -> str:
        return self.get("ca_bundle_path", "")

    def set_ca_bundle_path(self, path: str):
        self.set("ca_bundle_path", path or "")

    def get_ssl_verify(self):
        """Returns the requests verify param: True (default) or path to CA bundle."""
        if not self.get_use_windows_ca_bundle():
            return True
        path = self.get_ca_bundle_path()
        if path and os.path.isfile(path):
            return path
        return True
