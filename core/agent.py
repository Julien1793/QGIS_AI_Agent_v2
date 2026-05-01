# core/agent.py
import requests, re, os, json, time
from qgis.core import Qgis
from ..utils.translation import get_translations
from ..utils.http import post_with_retry

class AIAgent:
    def __init__(self, settings_manager):
        self.settings = settings_manager

    def _supports_zero_max_tokens(self, url: str, model: str = "") -> bool:
        # OpenAI, OpenRouter, Fireworks and Mistral-family models accept max_tokens=0.
        # LM Studio (localhost:1234) does not.
        url = (url or "").lower()
        model = (model or "").lower()
        known_url = ("api.openai.com" in url) or ("openrouter.ai" in url) or ("fireworks.ai" in url) or ("api.mistral.ai" in url)
        mistral_model = any(k in model for k in ("mistral", "mixtral", "codestral", "devstral"))
        return known_url or mistral_model

    def chat(self, user_input, mode="chat", lang="fr", messages=None, on_stream=None):
        """
        Send a chat request to the configured LLM backend.

        Supports two API formats (configured via SettingsManager.get_api_format()):
          - "openai"  : OpenAI-compatible format (default) — works with LM Studio, Ollama,
                        OpenAI, OpenRouter, Fireworks, Mistral, etc.
          - "claude"  : Anthropic native Messages API — uses x-api-key auth, system as a
                        top-level field, and Claude-specific SSE event names.

        If streaming is enabled and on_stream is provided, attempts SSE streaming
        and calls on_stream(chunk) for each text delta received.
        Always returns (final_text, usage_dict | total_tokens).
        """
        qgis_version = Qgis.QGIS_VERSION
        mode_type = self.settings.get("mode", "local")
        api_url = self.settings.get("api_url", "http://localhost:1234/v1/chat/completions")
        model = self.settings.get("model", "mistral")
        api_format = self.settings.get_api_format()

        # --- Build request headers (format-specific auth)
        api_key = self.settings.get("api_key", "") if mode_type == "distant" else ""
        headers = {"Content-Type": "application/json"}
        if api_format == "claude":
            # Claude native API: x-api-key + required version header
            headers["x-api-key"] = self.settings.get("api_key", "")
            headers["anthropic-version"] = "2023-06-01"
        elif mode_type == "distant" and api_key:
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

        # --- Build format-specific payload
        if api_format == "claude":
            # Claude: system is a top-level field; messages array must not contain system role;
            # max_tokens is required.
            claude_messages = [m for m in clean_messages if m["role"] != "system"]
            if not claude_messages:
                claude_messages = [{"role": "user", "content": str(user_input).strip()}]
            payload = {
                "model": model,
                "max_tokens": self.settings.get_agent_max_tokens(),
                "system": system_prompt,
                "messages": claude_messages,
            }
            built_messages = claude_messages
        else:
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
            if "x-api-key" in hh:
                hh["x-api-key"] = "****"
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

                if api_format != "claude":
                    # Request usage stats in the final stream chunk (OpenAI-compatible).
                    # Silently ignored by backends that do not support it (e.g. LM Studio).
                    payload_stream["stream_options"] = {"include_usage": True}

                # Set SSE-specific request headers.
                hdrs = dict(headers)
                hdrs.setdefault("Accept", "text/event-stream")
                hdrs.setdefault("Content-Type", "application/json")

                resp = post_with_retry(
                    api_url, payload_stream, hdrs,
                    timeout=self.settings.get_request_timeout(), stream=True,
                    verify=self.settings.get_ssl_verify()
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
                usage = {}

                # Read raw bytes to avoid encoding issues with some SSE implementations.
                for raw in resp.iter_lines(decode_unicode=False, delimiter=b"\n"):
                    if not raw:
                        continue

                    line = raw.decode("utf-8", errors="replace").strip()

                    # Skip SSE event-type lines and keep-alive pings.
                    # Claude sends "event: content_block_delta" etc. before each data line.
                    if line.startswith("event:") or line.startswith(":"):
                        continue

                    # Strip the "data:" SSE prefix when present.
                    if line.startswith("data:"):
                        line = line[5:].strip()

                    if not line or line == "[DONE]":
                        continue

                    chunk_text = ""
                    try:
                        obj = json.loads(line)

                        if api_format == "claude":
                            # Claude SSE event types:
                            # - message_start    : contains input token count in usage
                            # - content_block_delta : contains text delta
                            # - message_delta    : contains output token count in usage
                            event_type = obj.get("type", "")
                            if event_type == "content_block_delta":
                                delta = obj.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    chunk_text = delta.get("text", "")
                            elif event_type == "message_start":
                                msg_usage = obj.get("message", {}).get("usage", {})
                                if msg_usage:
                                    usage.update(msg_usage)
                            elif event_type == "message_delta":
                                delta_usage = obj.get("usage", {})
                                if delta_usage:
                                    usage.update(delta_usage)
                        else:
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
                # Skipped for Claude — usage is always included in message_start / message_delta events.
                if not usage and api_format != "claude":
                    try:
                        if self._supports_zero_max_tokens(api_url, model):
                            payload_usage = {"model": model, "messages": built_messages, "max_tokens": 0}
                            r2 = requests.post(api_url, json=payload_usage, headers=headers, timeout=15,
                                               verify=self.settings.get_ssl_verify())
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
                            r2 = requests.post(api_url, json=payload_usage, headers=headers, timeout=15,
                                               verify=self.settings.get_ssl_verify())
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
            resp = post_with_retry(api_url, payload, headers, timeout=self.settings.get_request_timeout(),
                                         verify=self.settings.get_ssl_verify())
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

            if api_format == "claude":
                if "error" in data:
                    err = data["error"]
                    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    return f"{t['llm_backend_error']}: {msg}", 0
                content_blocks = data.get("content", [])
                if not content_blocks:
                    return f"{t['llm_request_error']}: Empty response", 0
                raw_content = next((b["text"] for b in content_blocks if b.get("type") == "text"), "")
                usage = data.get("usage", {})
            else:
                if "error" in data:
                    return f"{t['llm_backend_error']}: {data['error']}", 0
                if not data.get("choices"):
                    return f"{t['llm_request_error']}: Empty response", 0
                raw_content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})

            final_message = self._extract_final_message(raw_content)
            return final_message, (usage or usage.get("total_tokens", 0) if isinstance(usage, dict) else 0)

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
