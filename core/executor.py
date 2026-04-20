# core/executor.py

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsProject, QgsVectorLayer, QgsApplication, Qgis
import processing
import traceback
import warnings

from ..utils.translation import get_translations


class CodeExecutor:
    def __init__(self, iface, on_error_callback=None, settings_manager=None):
        self.iface = iface
        self.on_error_callback = on_error_callback
        self.last_code = ""

        # Language and translations
        self.settings_manager = settings_manager
        try:
            lang = self.settings_manager.get_language()
        except Exception:
            lang = "en"
        self._lang = lang
        self.t = get_translations(self._lang)

        # Execution state flag and QGIS warning buffer (populated during execute_code).
        self._executing = False
        self._warnings = []
        try:
            QgsApplication.messageLog().messageReceived.connect(self._on_qgis_log)
        except Exception:
            pass

    def update_language(self, lang: str):
        """Refresh the active language; called when the user changes it in the Options dialog."""
        if not lang:
            return
        self._lang = lang
        self.t = get_translations(lang)

    def _on_qgis_log(self, msg: str, tag: str, level: Qgis.MessageLevel):
        """Collect QGIS Warning and Critical messages emitted during code execution only."""
        if not self._executing:
            return
        try:
            if level in (Qgis.Warning, Qgis.Critical):
                m = (msg or "").replace("\r\n", "\n").strip()
                t = (tag or "").strip() or "QGIS"
                self._warnings.append(f"[{t}] {m}")
        except Exception:
            pass

    # --- Public API ---
    def set_last_code(self, code: str):
        self.last_code = code

    def get_last_code(self) -> str:
        return self.last_code

    def clear_last_code(self):
        self.last_code = ""

    def execute_code(self, code: str):
        self.last_code = code or ""
        ok = False
        err_msg = None

        # Reset warning buffer and execution flag before running.
        self._warnings = []
        self._executing = True

        try:
            # Also capture Python-level warnings via the warnings module.
            with warnings.catch_warnings(record=True) as pywarns:
                warnings.simplefilter("always")

                exec(code, {
                    'iface': self.iface,
                    'QgsProject': QgsProject,
                    'QgsVectorLayer': QgsVectorLayer,
                    'processing': processing,
                    'Qgis': Qgis,
                })

                for w in pywarns:
                    try:
                        self._warnings.append(f"[PythonWarning] {str(w.message)}")
                    except Exception:
                        pass

            ok = True

        except Exception:
            err_msg = traceback.format_exc()

        finally:
            self._executing = False

            # --- Blocking error: code raised an exception ---
            if not ok:
                title = self.t.get("exec_error_title", "Execution error")
                self.iface.messageBar().pushCritical(title, (err_msg or ""))

                # Build the localised error string ready for the Debug tab.
                #err_label = "Erreur :" if self._lang == "fr" else "Error :"
                err_label = self.t.get("error_to_fix","Error :")
                composed = f"{err_label} {err_msg or ''}".strip()
                if self.on_error_callback:
                    self.on_error_callback(code, composed)
                return False, err_msg

            # --- Success with QGIS or Python warnings ---
            if self._warnings:
                # Show a non-blocking notification in the QGIS message bar.
                self.iface.messageBar().pushWarning(
                    self.t.get("dock_title", "AI Assistant"),
                    self.t.get("exec_warn_to_debug", "Execution finished with warnings — opening Debug tab.")
                )
                warn_label = f"{self.t.get('warnings', 'Warnings')} :"
                warn_prefix = self.t.get("warnings_prefix_debug", "QGIS warnings during execution:")
                warn_text = "\n".join(self._warnings)

                # Pre-compose the Debug tab text so the UI does not inject a second error prefix.
                composed = f"{warn_label} {warn_prefix}\n{warn_text}".strip()
                if self.on_error_callback:
                    self.on_error_callback(code, composed)
                return True, warn_text

            # --- Clean success: no errors, no warnings ---
            self.iface.messageBar().pushSuccess(
                self.t.get("dock_title", "AI Assistant"),
                self.t.get("exec_success", "Execution successful.")
            )
            return True, None
