# core/agent.py
import requests, re, os, json, time
from qgis.core import Qgis
from ..utils.translation import get_translations

class AIAgent:
    def __init__(self, settings_manager):
        self.settings = settings_manager

    
    def _supports_zero_max_tokens(self, url: str) -> bool:
        # OpenAI and OpenRouter accept max_tokens=0; LM Studio (localhost:1234) does not.
        url = (url or "").lower()
        return ("api.openai.com" in url) or ("openrouter.ai" in url) or ("fireworks.ai" in url)

    def chat(self, user_input, mode="chat", lang="fr", messages=None, on_stream=None):
        """
        Send a chat request to the configured LLM backend.

        If streaming is enabled and on_stream is provided, attempts SSE streaming
        and calls on_stream(chunk) for each text delta received.
        Always returns (final_text, usage_dict | total_tokens).
        """
        qgis_version = Qgis.QGIS_VERSION
        mode_type = self.settings.get("mode", "local")
        api_url = self.settings.get("api_url", "http://localhost:1234/v1/chat/completions")
        model = self.settings.get("model", "mistral")

        # --- Build request headers
        headers = {"Content-Type": "application/json"}
        if mode_type == "distant":
            api_key = self.settings.get("api_key", "")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

        # --- Resolve the system prompt for the requested mode
        t = get_translations(lang)
        try:
            sys_chat = t["system_prompt_chat"].format(qgis_version=qgis_version)
            sys_code = t["system_prompt_code"].format(qgis_version=qgis_version)
        except Exception:
            sys_chat = f"You are a QGIS expert. QGIS={qgis_version}"
            sys_code = sys_chat
        system_prompt = sys_chat if mode == "chat" else sys_code

        # --- Normalise and assemble the message list
        def _norm_msgs(msgs):
            out = []
            for m in msgs or []:
                if not m:
                    continue
                role = (m.get("role") or "user") if isinstance(m, dict) else "user"
                content = (m.get("content") or "").strip() if isinstance(m, dict) else ""
                if not content:
                    continue
                if role not in ("system", "user", "assistant"):
                    role = "user"
                out.append({"role": role, "content": content})
            return out

        clean_messages = _norm_msgs(messages)
        built_messages = [{"role": "system", "content": system_prompt}] + clean_messages
        if not clean_messages:
            built_messages.append({"role": "user", "content": str(user_input).strip()})

        payload = {"model": model, "messages": built_messages}

        # --- Optional request/response trace logging
        export_traces = bool(self.settings.get_export_traces() or False)
        trace_dir = self.settings.get_trace_dir() or ""

        def _redact(h):
            hh = dict(h or {})
            if "Authorization" in hh:
                hh["Authorization"] = "Bearer ****"
            return hh

        def _write_trace(trace_obj):
            if not export_traces or not trace_dir:
                return ""
            try:
                os.makedirs(trace_dir, exist_ok=True)
                ts = time.strftime("%Y%m%d_%H%M%S")
                path = os.path.join(trace_dir, f"trace_{ts}.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(trace_obj, f, ensure_ascii=False, indent=2)
                return path
            except Exception:
                return ""

        # --- Send the request
        stream_enabled = bool(getattr(self.settings, "get_streaming_enabled", lambda: False)())
        t0 = time.time()
        resp = None

        try:
            # --- Streaming mode (SSE): deliver chunks to the callback as they arrive.
            if stream_enabled and on_stream:
                payload_stream = dict(payload)
                payload_stream["stream"] = True

                # Request usage stats in the final stream chunk (OpenAI-compatible).
                # Silently ignored by backends that do not support it (e.g. LM Studio).
                payload_stream["stream_options"] = {"include_usage": True}

                # Set SSE-specific request headers.
                hdrs = dict(headers)
                hdrs.setdefault("Accept", "text/event-stream")
                hdrs.setdefault("Content-Type", "application/json")

                resp = requests.post(
                    api_url, json=payload_stream, headers=hdrs,
                    timeout=300, stream=True
                )

                elapsed = round(time.time() - t0, 3)
                trace = {
                    "when": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "elapsed_sec": elapsed,
                    "request": {
                        "url": api_url,
                        "model": model,
                        "headers": _redact(hdrs),
                        "payload": payload_stream,
                        "payload_size_bytes": len(json.dumps(payload_stream, ensure_ascii=False)),
                    },
                    "response": {"status_code": resp.status_code, "text": "(streaming)"},
                }
                self._last_trace = trace

                if resp.status_code >= 400:
                    _write_trace(trace)
                    return f"{t['llm_request_error']} ({resp.status_code}): {resp.text}", 0

                final_parts = []
                usage = {}  # on tentera de le remplir pendant le flux

                # Read raw bytes to avoid encoding issues with some SSE implementations.
                for raw in resp.iter_lines(decode_unicode=False, delimiter=b"\n"):
                    if not raw:
                        continue

                    line = raw.decode("utf-8", errors="replace").strip()

                    # Strip the "data:" SSE prefix when present.
                    if line.startswith("data:"):
                        line = line[5:].strip()

                    if not line or line == "[DONE]" or line.startswith(":"):
                        # Skip keep-alive pings and the [DONE] sentinel.
                        continue

                    chunk_text = ""
                    try:
                        obj = json.loads(line)

                        # a) Standard OpenAI delta format.
                        if "choices" in obj and obj["choices"]:
                            ch0 = obj["choices"][0]
                            delta = ch0.get("delta") or {}
                            chunk_text = delta.get("content") or ""
                            if not chunk_text:
                                msg = ch0.get("message") or {}
                                chunk_text = msg.get("content") or ""

                        # b) Capture usage stats if the backend includes them in the final chunk.
                        if "usage" in obj and isinstance(obj["usage"], dict):
                            usage = obj["usage"]

                        # c) LM Studio non-standard format: content is at the root level.
                        if not chunk_text and isinstance(obj.get("content"), str):
                            chunk_text = obj["content"]

                    except Exception:
                        # Non-JSON chunk — treat as raw text.
                        chunk_text = line

                    if chunk_text:
                        on_stream(chunk_text)
                        final_parts.append(chunk_text)

                final = "".join(final_parts).strip()
                if not final:
                    final = t.get("llm_request_error", "LLM request error") + ": Empty streamed response"

                # Fallback: make a second lightweight non-streaming call to retrieve usage stats.
                # max_tokens=0 is accepted by OpenAI and most proxies; errors are silently ignored.
                if not usage:
                    try:
                        if self._supports_zero_max_tokens(api_url):
                            payload_usage = {"model": model, "messages": built_messages, "max_tokens": 0}
                            r2 = requests.post(api_url, json=payload_usage, headers=headers, timeout=15)
                            if r2.ok:
                                j2 = r2.json()
                                if isinstance(j2, dict):
                                    usage = j2.get("usage", {}) or {}
                        else:
                            # LM Studio requires at least 1 output token; use temperature=0 for minimal cost.
                            payload_usage = {
                                "model": model,
                                "messages": built_messages,
                                "max_tokens": 1,
                                "temperature": 0,
                            }
                            r2 = requests.post(api_url, json=payload_usage, headers=headers, timeout=15)
                            if r2.ok:
                                j2 = r2.json()
                                if isinstance(j2, dict):
                                    usage = j2.get("usage", {}) or {}
                    except Exception:
                        pass

                trace["response"]["json_parsed"] = True
                _write_trace(trace)

                # Return the full usage dict, or fall back to the total_tokens integer.
                return final, (usage or usage.get("total_tokens", 0) if isinstance(usage, dict) else 0)


            # --- Non-streaming mode: single blocking POST request.
            resp = requests.post(api_url, json=payload, headers=headers, timeout=300)
            trace = {
                "when": time.strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_sec": round(time.time() - t0, 3),
                "request": {
                    "url": api_url,
                    "model": model,
                    "headers": _redact(headers),
                    "payload": payload,
                    "payload_size_bytes": len(json.dumps(payload, ensure_ascii=False)),
                },
                "response": {"status_code": resp.status_code, "text": resp.text[:5000]},
            }
            self._last_trace = trace

            if resp.status_code >= 400:
                _write_trace(trace)
                return f"{t['llm_request_error']} ({resp.status_code}): {resp.text}", 0

            data = resp.json()
            trace["response"]["json_parsed"] = True
            _write_trace(trace)

            if "error" in data:
                return f"{t['llm_backend_error']}: {data['error']}", 0
            if not data.get("choices"):
                return f"{t['llm_request_error']}: Empty response", 0

            raw_content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            final_message = self._extract_final_message(raw_content)
            return final_message, (usage or usage.get("total_tokens", 0))

        except Exception as e:
            trace = {
                "when": time.strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_sec": round(time.time() - t0, 3),
                "request": {"url": api_url, "model": model, "headers": _redact(headers), "payload": payload,
                            "payload_size_bytes": len(json.dumps(payload, ensure_ascii=False))},
                "response": {"status_code": getattr(resp, "status_code", None), "error": str(e)},
            }
            self._last_trace = trace
            _write_trace(trace)
            return f"{t['llm_request_error']}: {str(e)}", 0


    def _extract_final_message(self, raw_response: str) -> str:
        m = re.search(r"<\|start\|>assistant<\|channel\|>final<\|message\|>(.*)", raw_response, re.DOTALL)
        return m.group(1).strip() if m else raw_response.strip()
