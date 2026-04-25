# ui/workers.py
import threading
from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot
from ..utils.http import post_with_retry


class ChatWorker(QObject):
    finished = pyqtSignal(str, object)   # (response, usage)
    error = pyqtSignal(str)
    stream_chunk = pyqtSignal(str)

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
    step_event = pyqtSignal(object)
    tool_request = pyqtSignal(str, object)
    finished = pyqtSignal(str, int)
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
        import json
        try:
            api_url, headers, payload = self.agent.build_request(
                self.prompt, mode=self.mode, lang=self.lang, messages=self.messages
            )
            payload_stream = dict(payload)
            payload_stream["stream"] = True

            resp = post_with_retry(api_url, payload_stream, headers,
                                   timeout=self.agent.settings.get_request_timeout(), stream=True,
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
