# core/agent_loop.py
#
# Agent orchestrator:
#   1. Classifies the user intent via a lightweight LLM call
#   2. Selects tools from the registry based on the detected intents
#   3. Runs the agentic loop: LLM call → tool execution → tool result → next LLM call
#   4. Emits structured events via on_step() for the UI to render progressively
#   5. Returns the final text response and cumulative token usage
#
# All user-facing text is sourced from the translation dictionary.

import json
import re
import time

from .tools_registry import get_schemas_for_intent, get_handler_name, REGISTRY
from . import tools_handlers as handlers
from ..utils.translation import get_translations
from ..utils.http import post_with_retry


class AgentLoop:
    def __init__(self, settings_manager, iface=None, executor=None):
        self.settings = settings_manager
        self.iface = iface
        self.executor = executor

    # ══════════════════════════════════════════════════════════
    # API publique
    # ══════════════════════════════════════════════════════════

    def run(self, user_prompt: str, snapshot_json: str,
            on_step=None, tool_executor=None,
            history_messages: list = None) -> tuple:
        """
        Run the full agentic loop.

        Args:
            user_prompt   : the user's request text
            snapshot_json : JSON snapshot of the QGIS project (from project_indexer)
            on_step       : callback(event_dict) called for each agent step so the UI
                            can render progress in real time. Each event_dict contains:
                              - type : 'thinking', 'intent', 'iteration',
                                       'tool_call', 'tool_result',
                                       'final', 'max_iterations'
                              - text : already-translated display string
                              - data : raw data (optional, for detail panels)
            tool_executor : optional callable(tool_name, args) that executes tools on the
                            main thread (required when running in a background worker thread)
            history_messages : previous conversation turns to include as context

        Returns:
            (final_text: str, total_tokens: int)
        """
        lang = self._get_lang()
        t = get_translations(lang)
        max_iter = self._get_max_iterations()

        # 1 — Emit a "thinking" event so the UI can show a loading indicator.
        self._emit(on_step, "thinking", t["agent_step_thinking"])

        # 2 — Classify the user intent to narrow down the tool set.
        intents = self._classify_intent(user_prompt, t)

        # 3 — Retrieve the tool schemas for the detected intents.
        tools = get_schemas_for_intent(intents)
        # Deduplicate by name (get_schemas_for_intent includes __always__ tools for every
        # intent, so multiple intents like ["style", "label"] produce duplicate entries).
        _seen_names: set = set()
        _deduped = []
        for s in tools:
            _n = s["function"]["name"]
            if _n not in _seen_names:
                _seen_names.add(_n)
                _deduped.append(s)
        tools = _deduped

        if not self.settings.get_canvas_capture_enabled():
            _hint = " ALWAYS call capture_map_canvas afterwards to verify the result."
            cleaned = []
            for s in tools:
                if s["function"]["name"] == "capture_map_canvas":
                    continue
                desc = s["function"].get("description", "")
                if _hint in desc:
                    import copy
                    s = copy.deepcopy(s)
                    s["function"]["description"] = desc.replace(_hint, "")
                cleaned.append(s)
            tools = cleaned
        # For non-chat intents, prepend declare_tool_plan (planning phase, iter 0 only).
        # Fetch the schema directly from REGISTRY — get_schemas_for_intent would also inject
        # __always__ / __fallback__ tools here, which would reintroduce duplicates.
        _plan_tool = "declare_tool_plan"
        is_chat_only = intents == ["chat"]
        if not is_chat_only:
            tools = [REGISTRY[_plan_tool]["schema"]] + tools

        tool_names = [tt["function"]["name"] for tt in tools
                      if tt["function"]["name"] != _plan_tool]

        # 4 — Emit the detected intents and selected tools to the UI.
        intent_text = t["agent_step_intent_detected"].format(
            intents=", ".join(intents)
        )
        tools_text = t["agent_step_tools_selected"].format(
            count=len(tool_names),
            names=", ".join(tool_names),
        )
        self._emit(on_step, "intent",
                   f"{intent_text}\n{tools_text}",
                   data={"intents": intents, "tools": tool_names})

        # 5 — Build the initial message list (system prompt + history + current user message).
        # For pure chat, skip the project snapshot to avoid sending thousands of tokens
        # for a request that doesn't need GIS context.
        history = [m for m in (history_messages or [])
                   if m.get("role") in ("user", "assistant")]
        if is_chat_only or not snapshot_json:
            user_content = user_prompt
        else:
            user_content = (
                f"{t['project_snapshot_intro']}\n```json\n{snapshot_json}\n```\n\n"
                f"{user_prompt}"
            )
        system_prompt = t["agent_system_prompt"]
        if self.settings.get_canvas_capture_enabled():
            system_prompt += "\n" + t["agent_system_prompt_canvas_rules"]
        if not is_chat_only:
            system_prompt += t.get("agent_system_prompt_planning", "")
        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": user_content},
        ]

        # 6 — Agentic loop: LLM call → tool execution → tool result → next LLM call.
        _trace_entries = []
        import datetime as _dt
        _run_ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        def _flush_traces():
            if not _trace_entries:
                return
            export_traces = bool(self.settings.get_export_traces() or False)
            trace_dir = self.settings.get_trace_dir() or ""
            if not export_traces or not trace_dir:
                return
            try:
                import os
                os.makedirs(trace_dir, exist_ok=True)
                path = os.path.join(trace_dir, f"agent_trace_{_run_ts}.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(_trace_entries, f, ensure_ascii=False, indent=2)
            except Exception as ex:
                try:
                    from qgis.core import QgsMessageLog, Qgis
                    QgsMessageLog.logMessage(
                        f"[AgentLoop] trace write failed: {ex}", "AI Agent", Qgis.Warning)
                except Exception:
                    pass

        total_tokens = 0
        total_input_tokens = 0
        total_output_tokens = 0
        ctx_max = self.settings.get_project_context_max_tokens()
        _fail_count = 0  # consecutive batches containing a non-pyqgis failure
        # last_prompt_tokens: input size of the most recent LLM call — grows each iteration as tool results accumulate.
        # last_completion_tokens: output size of the most recent call = what gets added to history next turn.
        # Mid-loop: gauge shows last_prompt_tokens only (loop still running, no final response yet).
        # At exit: gauge shows last_prompt_tokens + last_completion_tokens (full next-request estimate).
        last_prompt_tokens = 0
        last_completion_tokens = 0

        def _emit_gauge(mid_loop=False):
            estimated = last_prompt_tokens if mid_loop else last_prompt_tokens + last_completion_tokens
            self._emit(on_step, "context_usage", "",
                       data={"prompt_tokens": estimated, "context_max": ctx_max})
            if ctx_max > 0 and estimated > 0:
                ratio = estimated / ctx_max
                if ratio >= 0.90:
                    self._emit(on_step, "context_warning",
                               t["agent_context_overflow"].format(used=estimated, max=ctx_max))
                elif ratio >= 0.75:
                    self._emit(on_step, "context_warning",
                               t["agent_context_warning"].format(used=estimated, max=ctx_max))

        for iteration in range(max_iter):

            # At iter 1, the planning phase is over — remove declare_tool_plan from the live
            # tools list so subsequent calls don't waste tokens on the planning schema.
            if iteration == 1:
                tools[:] = [s for s in tools if s["function"]["name"] != _plan_tool]

            # Skip the iteration event on the first turn to avoid cluttering the UI.
            if iteration > 0:
                self._emit(on_step, "iteration",
                           t["agent_step_iteration"].format(
                               current=iteration + 1, max=max_iter))

            response, usage, prompt_tokens = self._llm_call(messages, tools, _trace_entries)
            total_tokens += usage
            last_prompt_tokens = prompt_tokens
            last_completion_tokens = max(usage - prompt_tokens, 0)
            total_input_tokens += prompt_tokens
            total_output_tokens += last_completion_tokens

            # LLM call failed — emit an error event and abort the loop.
            if response is None:
                detail = getattr(self, "_last_llm_error", "")
                err_text = t["llm_request_error"] + (f": {detail}" if detail else "")
                _emit_gauge()
                self._emit(on_step, "final", err_text)
                _flush_traces()
                return err_text, total_tokens, total_input_tokens, total_output_tokens

            # The LLM returned a final text response with no further tool calls.
            if not response.get("tool_calls"):
                final_text = response.get("content") or ""
                _emit_gauge()
                self._emit(on_step, "final", final_text)
                _flush_traces()
                return final_text, total_tokens, total_input_tokens, total_output_tokens

            # The LLM requested one or more tool calls — update gauge and execute them.
            _emit_gauge(mid_loop=True)
            messages.append({"role": "assistant", **response})

            # Emit any intermediate text the LLM produced alongside its tool calls.
            thought = (response.get("content") or "").strip()
            if thought:
                self._emit(on_step, "llm_thought", thought)

            batch_results = []
            for tool_call in response["tool_calls"]:
                tool_name = tool_call["function"]["name"]
                try:
                    tool_args = json.loads(tool_call["function"]["arguments"])
                except Exception as e:
                    tool_args = {}
                    try:
                        from qgis.core import QgsMessageLog, Qgis
                        QgsMessageLog.logMessage(
                            f"[AgentLoop] Failed to parse arguments for tool '{tool_name}': {e}\n"
                            f"Raw: {tool_call['function'].get('arguments', '')!r}",
                            "AI Agent", Qgis.Warning)
                    except Exception:
                        pass

                # Emit the tool call event before execution so the UI can show it immediately.
                tool_call_text = t["agent_step_tool_calling"].format(tool=tool_name)
                self._emit(on_step, "tool_call", tool_call_text,
                           data={"name": tool_name, "args": tool_args})

                # Meta-tools: handle without calling a QGIS handler.
                if tool_name == _plan_tool:
                    result = self._apply_tool_plan(tool_args, tools)
                elif tool_name == "request_additional_tools":
                    result = self._expand_tools(tool_args, tools)
                else:
                    # Delegate to the external tool_executor (main thread) if provided, otherwise run locally.
                    _execute = tool_executor or self._execute_tool
                    result = _execute(tool_name, tool_args)

                batch_results.append(result)

                # Emit the tool result with a human-readable translated summary.
                if result.get("success"):
                    summary = self._format_result_summary(result, t)
                    result_text = t["agent_step_tool_success"].format(summary=summary)
                    event_type = "tool_result"
                else:
                    error = result.get("error", "?")
                    # Truncate very long error messages to avoid flooding the chat.
                    if len(error) > 500:
                        error = error[:500] + "..."
                    result_text = t["agent_step_tool_error"].format(error=error)
                    event_type = "tool_error"

                self._emit(on_step, event_type, result_text,
                           data={"name": tool_name, "result": result})

                # Append the tool result to the message history so the LLM can reason about it.
                # Exclude image_base64 from the tool message (too large); injected separately below.
                result_for_msg = {k: v for k, v in result.items() if k != "image_base64"}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result_for_msg, ensure_ascii=False),
                })

                # If the tool returned a canvas screenshot, inject it as a vision user message.
                if result.get("success") and result.get("image_base64"):
                    b64 = result["image_base64"]
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Here is the screenshot of the QGIS canvas after the operation:"},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                        ],
                    })

            # Update failure counter from this batch.
            non_pyqgis_failures = [
                r for r in batch_results
                if not r.get("success") and r.get("tool") != "run_pyqgis_code"
            ]
            if non_pyqgis_failures:
                _fail_count += 1
            else:
                _fail_count = 0

            # Inject a soft reflection hint if signals warrant it.
            checkpoint_msg, checkpoint_label = self._get_checkpoint_msg(
                batch_results, _fail_count,
            )
            if checkpoint_msg:
                messages.append({"role": "user", "content": checkpoint_msg})
                self._emit(on_step, "checkpoint", checkpoint_label)

        # The agent hit the iteration cap without reaching a final answer.
        max_text = t["agent_step_max_iterations"].format(max=max_iter)
        _emit_gauge()
        self._emit(on_step, "max_iterations", max_text)
        _flush_traces()
        return max_text, total_tokens, total_input_tokens, total_output_tokens

    # ══════════════════════════════════════════════════════════
    # Détection d'intention (LLM léger)
    # ══════════════════════════════════════════════════════════

    def _classify_intent(self, prompt: str, t: dict) -> list:
        """
        Lightweight LLM call to classify the user's intent.
        Falls back to ["chat"] if the call fails or returns no valid intents.
        """
        api_url = self.settings.get("api_url", "http://localhost:1234/v1/chat/completions")
        model = self.settings.get("model", "mistral")
        api_format = self.settings.get_api_format()
        headers = self._build_headers()

        if api_format == "claude":
            payload = {
                "model": model,
                "max_tokens": 150,
                "system": t["agent_intent_system"],
                "messages": [{"role": "user",
                               "content": t["agent_intent_user"].format(prompt=prompt)}],
            }
        else:
            # o-series models require max_completion_tokens and don't support temperature != 1.
            is_o_series = bool(re.match(r"^(o\d|gpt-5)", model))
            token_key = "max_completion_tokens" if is_o_series else "max_tokens"
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": t["agent_intent_system"]},
                    {"role": "user",
                     "content": t["agent_intent_user"].format(prompt=prompt)},
                ],
                token_key: 150,
            }
            if not is_o_series:
                payload["temperature"] = 0

        try:
            resp = post_with_retry(api_url, payload, headers, timeout=30,
                                   verify=self.settings.get_ssl_verify())
            if not resp.ok:
                try:
                    from qgis.core import QgsMessageLog, Qgis
                    QgsMessageLog.logMessage(
                        f"[AgentLoop] Intent classification HTTP {resp.status_code}: {resp.text[:500]}",
                        "AI Agent", Qgis.Warning)
                except Exception:
                    pass
            resp.raise_for_status()
            data = resp.json()

            if api_format == "claude":
                content_blocks = data.get("content", [])
                raw = next((b.get("text", "") for b in content_blocks if b.get("type") == "text"), "").strip()
            else:
                raw = data["choices"][0]["message"]["content"].strip()

            # Robustly extract the JSON object (the LLM may add surrounding prose).
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                intents = parsed.get("intents", [])
                if isinstance(intents, list) and intents:
                    # Keep only known intent values; discard anything unrecognised.
                    valid = {
                        "chat", "read", "stats",
                        "process", "join", "select",
                        "style", "label",
                        "field", "layer",
                        "view", "raster",
                    }
                    filtered = [i for i in intents if i in valid]
                    if filtered:
                        return filtered
            # Log why classification produced no usable intents.
            try:
                from qgis.core import QgsMessageLog, Qgis
                QgsMessageLog.logMessage(
                    f"[AgentLoop] Intent classification returned no valid intents. Raw: {raw!r}",
                    "AI Agent", Qgis.Warning)
            except Exception:
                pass
        except Exception:
            import traceback
            try:
                from qgis.core import QgsMessageLog, Qgis
                QgsMessageLog.logMessage(
                    f"[AgentLoop] Intent classification failed: {traceback.format_exc()}",
                    "AI Agent", Qgis.Warning)
            except Exception:
                pass

        return ["chat"]

    # ══════════════════════════════════════════════════════════
    # Appel LLM principal (avec tools)
    # ══════════════════════════════════════════════════════════

    def _llm_call(self, messages: list, tools: list, trace_entries: list = None) -> tuple:
        """
        Call the LLM with the current message history and tool schemas.
        Handles both OpenAI-compatible and Claude (Anthropic) native API formats.
        Returns (response_dict, tokens_used, prompt_tokens). Returns (None, 0, 0) on failure.
        If trace_entries is provided, appends one entry dict per call (written as a single
        file by the caller at the end of the run).
        """
        api_url = self.settings.get("api_url", "http://localhost:1234/v1/chat/completions")
        model = self.settings.get("model", "mistral")
        api_format = self.settings.get_api_format()
        headers = self._build_headers()
        max_tokens = self.settings.get_agent_max_tokens()

        if api_format == "claude":
            system, claude_msgs = self._to_claude_messages(messages)
            claude_tools = self._to_claude_tools(tools)
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": claude_msgs,
                "tool_choice": {"type": "auto"},
            }
            if claude_tools:
                payload["tools"] = claude_tools
        else:
            is_o_series = bool(re.match(r"^(o\d|gpt-5)", model))
            token_key = "max_completion_tokens" if is_o_series else "max_tokens"
            payload = {
                "model": model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                token_key: max_tokens,
            }

        def _redact(h):
            hh = dict(h or {})
            if "Authorization" in hh:
                hh["Authorization"] = "Bearer ****"
            if "x-api-key" in hh:
                hh["x-api-key"] = "****"
            return hh

        try:
            t0 = time.time()
            resp = post_with_retry(api_url, payload, headers, timeout=self.settings.get_request_timeout(),
                                   verify=self.settings.get_ssl_verify())
            resp.raise_for_status()
            data = resp.json()
            if trace_entries is not None:
                trace_entries.append({
                    "url": api_url,
                    "headers": _redact(headers),
                    "request": payload,
                    "response": data,
                    "elapsed_s": round(time.time() - t0, 3),
                })

            if api_format == "claude":
                return self._parse_claude_llm_response(data)

            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
            prompt_tokens = usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0

            choice = data["choices"][0]
            msg = choice["message"]

            response = {"content": msg.get("content") or ""}

            raw_calls = msg.get("tool_calls") or []
            if raw_calls:
                response["tool_calls"] = []
                for tc in raw_calls:
                    response["tool_calls"].append({
                        "id": tc.get("id", f"call_{int(time.time())}"),
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"].get("arguments", "{}"),
                        },
                    })

            return response, tokens, prompt_tokens

        except Exception as e:
            import traceback
            body = ""
            if hasattr(e, "response") and e.response is not None:
                body = e.response.text[:400]
            self._last_llm_error = str(e) + (f" — {body}" if body else "")
            try:
                from qgis.core import QgsMessageLog, Qgis
                QgsMessageLog.logMessage(
                    f"[AgentLoop] LLM call failed: {traceback.format_exc()}"
                    + (f"\nResponse body: {body}" if body else ""),
                    "AI Agent", Qgis.Critical)
            except Exception:
                pass
            return None, 0, 0

    # ══════════════════════════════════════════════════════════
    # Expansion dynamique des tools mid-loop
    # ══════════════════════════════════════════════════════════

    def _expand_tools(self, args: dict, tools: list) -> dict:
        """Inject additional tool schemas into the live tools list based on requested intents."""
        valid_intents = {
            "read", "stats", "process", "join", "select",
            "style", "label", "field", "layer", "view", "raster",
        }
        requested = [i for i in args.get("intents", []) if i in valid_intents]
        if not requested:
            return {"success": False, "tool": "request_additional_tools",
                    "error": "No valid intent provided."}

        existing_names = {s["function"]["name"] for s in tools}
        canvas_enabled = self.settings.get_canvas_capture_enabled()
        added = []
        for schema in get_schemas_for_intent(requested):
            name = schema["function"]["name"]
            if name == "capture_map_canvas" and not canvas_enabled:
                continue
            if name not in existing_names:
                tools.append(schema)
                existing_names.add(name)
                added.append(name)

        return {"success": True, "tool": "request_additional_tools",
                "added_tools": added, "requested_intents": requested}

    def _apply_tool_plan(self, args: dict, tools: list) -> dict:
        """Filter the live tools list down to the LLM-declared subset, keeping safety tools."""
        declared = [str(n) for n in args.get("tools", [])]
        _always_keep = {"request_additional_tools", "run_pyqgis_code"}
        if self.settings.get_canvas_capture_enabled():
            _always_keep.add("capture_map_canvas")
        declared_set = set(declared)
        new_tools = [
            s for s in tools
            if s["function"]["name"] in declared_set
            or s["function"]["name"] in _always_keep
        ]
        tools.clear()
        tools.extend(new_tools)
        return {"success": True, "tool": "declare_tool_plan", "planned_tools": declared}

    # ══════════════════════════════════════════════════════════
    # Dispatch vers les handlers
    # ══════════════════════════════════════════════════════════

    def _execute_tool(self, tool_name: str, args: dict) -> dict:
        """Resolve and call the Python handler registered for tool_name."""
        handler_name = get_handler_name(tool_name)
        if not handler_name:
            return {
                "success": False,
                "tool": tool_name,
                "error": f"Unknown tool: {tool_name}",
            }

        handler_fn = getattr(handlers, handler_name, None)
        if handler_fn is None:
            return {
                "success": False,
                "tool": tool_name,
                "error": f"Handler not found: {handler_name}",
            }

        # Dynamically inject iface and executor only if the handler signature declares them.
        import inspect
        sig = inspect.signature(handler_fn)
        if "iface" in sig.parameters:
            args = {**args, "iface": self.iface}
        if "executor" in sig.parameters:
            args = {**args, "executor": self.executor}

        try:
            return handler_fn(**args)
        except TypeError as e:
            return {
                "success": False,
                "tool": tool_name,
                "error": f"Invalid arguments: {str(e)}",
            }
        except Exception as e:
            import traceback
            return {
                "success": False,
                "tool": tool_name,
                "error": traceback.format_exc(),
            }

    # ══════════════════════════════════════════════════════════
    # Formatage des résultats (traduit)
    # ══════════════════════════════════════════════════════════

    def _format_result_summary(self, result: dict, t: dict) -> str:
        """Build a translated summary string for a tool result to display in the UI."""
        tool = result.get("tool", "")

        # Geoprocessing tools — output layer was created.
        if tool in ("buffer", "clip", "intersection", "dissolve",
                    "difference", "union", "centroids", "fix_geometries",
                    "reproject_layer", "join_by_location",
                    "run_processing_algorithm", "calculate_geometry"):
            return t["agent_result_layer_created"].format(
                name=result.get("output_layer", "?"),
                count=result.get("feature_count_out", "?"),
            )

        # Selection tools.
        if tool in ("select_by_expression", "select_by_location"):
            return t["agent_result_selection"].format(
                selected=result.get("selected_count", "?"),
                total=result.get("total_count", "?"),
                layer=result.get("layer", "?"),
            )

        # Layer filter.
        if tool == "set_layer_filter":
            return t["agent_result_filter_applied"].format(
                layer=result.get("layer", "?"),
                count=result.get("visible_count", "?"),
            )

        # Styling tools.
        if tool in ("set_single_symbol", "set_categorized_style",
                    "set_graduated_style", "set_layer_opacity"):
            return t["agent_result_style_applied"].format(
                layer=result.get("layer", "?"),
            )

        # Tool plan declaration.
        if tool == "declare_tool_plan":
            planned = result.get("planned_tools", [])
            return t.get("agent_result_tool_plan", "Tool plan set: {tools}").format(
                tools=", ".join(planned) if planned else "—")

        # Dynamic tool expansion.
        if tool == "request_additional_tools":
            added = result.get("added_tools", [])
            return t["agent_result_tools_expanded"].format(
                tools=", ".join(added) if added else t["agent_no_new_tools"])

        # Canvas screenshot.
        if tool == "capture_map_canvas":
            return t["agent_result_canvas_captured"].format(
                width=result.get("width", "?"),
                height=result.get("height", "?"),
            )

        # Layer visibility.
        if tool == "set_layer_visibility":
            if result.get("visible"):
                return t["agent_result_visibility_on"].format(
                    layer=result.get("layer", "?"))
            return t["agent_result_visibility_off"].format(
                layer=result.get("layer", "?"))

        # Field editing.
        if tool == "calculate_field":
            return t["agent_result_field_calculated"].format(
                field=result.get("field", "?"),
                count=result.get("updated_count", "?"),
            )
        if tool == "add_field":
            return t["agent_result_field_added"].format(
                field=result.get("field", "?"),
                layer=result.get("layer", "?"),
            )

        # Layer I/O.
        if tool == "load_layer":
            return t["agent_result_layer_loaded"].format(
                name=result.get("layer", "?"),
                count=result.get("feature_count", "?"),
            )
        if tool == "export_layer":
            return t["agent_result_layer_exported"].format(
                layer=result.get("layer", "?"),
                path=result.get("output_path", "?"),
            )

        # Free-form PyQGIS code execution.
        if tool == "run_pyqgis_code":
            return t["agent_result_code_executed"]

        # Read / inspect tools.
        if tool == "get_project_info":
            return t["agent_result_project_info"].format(
                count=result.get("layer_count", "?"))
        if tool == "get_layer_info":
            return t["agent_result_layer_info"].format(
                layer=result.get("name", "?"))
        if tool == "get_layer_fields":
            return t["agent_result_fields_info"].format(
                count=result.get("count", "?"),
                layer=result.get("layer", "?"))
        if tool == "get_layer_features":
            return t["agent_result_features_info"].format(
                returned=result.get("returned", "?"),
                total=result.get("total", "?"))
        if tool == "get_layer_statistics":
            return t["agent_result_stats"].format(
                field=result.get("field", "?"),
                layer=result.get("layer", "?"))

        # Map navigation.
        if tool in ("zoom_to_layer", "zoom_to_feature"):
            return t["agent_result_zoom"].format(
                target=result.get("layer", "?"))

        # Generic fallback for unlisted tools.
        return t["agent_result_generic"].format(tool=tool)

    # ══════════════════════════════════════════════════════════
    # Checkpoint de réflexion post-batch
    # ══════════════════════════════════════════════════════════

    def _get_checkpoint_msg(self, batch_results: list, fail_count: int):
        """
        Analyse les résultats d'un batch.
        Retourne (message_to_inject, ui_label) ou (None, "") si rien à signaler.
        """
        parts = []
        label = ""

        # Cas 1 & 2 — failures non-pyqgis (avec escalade progressive).
        if fail_count >= 2:
            parts.append(
                "Note: multiple consecutive tool failures. Your current approach may not be "
                "the right one. Step back and consider whether a different set of tools or a "
                "different strategy would better achieve the user's goal before continuing."
            )
            label = "Approach check: multiple failures"
        elif fail_count == 1:
            parts.append(
                "Note: the last tool call failed. If this was a parameter issue "
                "(wrong layer name, invalid expression syntax), fix and continue. "
                "If you're uncertain your approach is correct, consider whether a "
                "different tool or strategy would better achieve the goal."
            )
            label = "Approach check: last tool failed"

        # Cas 3 & 4 — résultat vide sur un tool réussi.
        for r in batch_results:
            if not r.get("success"):
                continue
            if r.get("feature_count_out") == 0:
                parts.append(
                    "Note: the output layer contains 0 features. If this is unexpected, "
                    "check your input parameters or expression — the operation may have "
                    "filtered out everything. Consider whether a different approach would "
                    "produce a meaningful result."
                )
                if not label:
                    label = "Approach check: output is empty"
                break
            if r.get("selected_count") == 0:
                parts.append(
                    "Note: the selection matched 0 features. Verify that the expression "
                    "targets the correct field and values. If unexpected, consider revising "
                    "the expression or using a different selection strategy."
                )
                if not label:
                    label = "Approach check: selection matched nothing"
                break

        if parts:
            return "\n\n".join(parts), label
        return None, ""

    # ══════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════

    def _emit(self, callback, event_type: str, text: str, data: dict = None):
        """
        Emit a structured event dict to the UI callback.
        Exceptions are silently swallowed to prevent UI errors from crashing the agent loop.
        """
        if callback is None:
            return
        try:
            callback({
                "type": event_type,
                "text": text,
                "data": data or {},
            })
        except Exception:
            pass

    def _get_lang(self) -> str:
        try:
            return self.settings.get_language() or "fr"
        except Exception:
            return "fr"

    def _get_max_iterations(self) -> int:
        try:
            val = self.settings.get("agent_max_iterations", 8)
            return int(val) if val else 8
        except Exception:
            return 8

    def _build_headers(self) -> dict:
        """Build API request headers based on the configured api_format (openai or claude)."""
        api_format = self.settings.get_api_format()
        headers = {"Content-Type": "application/json"}
        if api_format == "claude":
            headers["x-api-key"] = self.settings.get("api_key", "")
            headers["anthropic-version"] = "2023-06-01"
        elif self.settings.get("mode") == "distant":
            key = self.settings.get("api_key", "")
            if key:
                headers["Authorization"] = f"Bearer {key}"
        return headers

    def _to_claude_messages(self, messages: list) -> tuple:
        """Convert an OpenAI-format messages list to Claude format.

        Returns (system_prompt: str, claude_messages: list).
        Rules:
          - system role → extracted as top-level system string
          - tool role   → merged into a user message as tool_result content blocks
          - assistant with tool_calls → content array with text + tool_use blocks
          - user with image_url parts → converted to Claude image source blocks
          Consecutive user messages are merged into a single user message to satisfy
          Claude's strict user/assistant alternation requirement.
        """
        system = ""
        claude_msgs = []

        def _last_is_user_list():
            return (claude_msgs
                    and claude_msgs[-1]["role"] == "user"
                    and isinstance(claude_msgs[-1]["content"], list))

        for m in messages:
            role = m.get("role")
            content = m.get("content")

            if role == "system":
                system = content or ""
                continue

            if role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": content or "",
                }
                if _last_is_user_list():
                    claude_msgs[-1]["content"].append(block)
                else:
                    claude_msgs.append({"role": "user", "content": [block]})
                continue

            if role == "assistant":
                tool_calls = m.get("tool_calls") or []
                if tool_calls:
                    claude_content = []
                    if content:
                        claude_content.append({"type": "text", "text": content})
                    for tc in tool_calls:
                        try:
                            args = json.loads(tc["function"]["arguments"])
                        except Exception:
                            args = {}
                        claude_content.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": tc["function"]["name"],
                            "input": args,
                        })
                    claude_msgs.append({"role": "assistant", "content": claude_content})
                else:
                    claude_msgs.append({"role": "assistant", "content": content or ""})
                continue

            if role == "user":
                if isinstance(content, list):
                    # Multipart user message — convert image_url to Claude image source.
                    parts = []
                    for part in content:
                        if part.get("type") == "text":
                            parts.append({"type": "text", "text": part["text"]})
                        elif part.get("type") == "image_url":
                            url = (part.get("image_url") or {}).get("url", "")
                            if url.startswith("data:image/"):
                                header, b64data = url.split(",", 1)
                                # Detect the real format from base64 magic bytes.
                                # The declared media type in the URL can be wrong
                                # (e.g. QGIS saves JPEG but labels it image/png).
                                if b64data.startswith("/9j/"):
                                    media_type = "image/jpeg"
                                elif b64data.startswith("iVBOR"):
                                    media_type = "image/png"
                                elif b64data.startswith("R0lGO"):
                                    media_type = "image/gif"
                                elif b64data.startswith("UklGR"):
                                    media_type = "image/webp"
                                else:
                                    media_type = header.split(";")[0].split(":")[1]
                                parts.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": b64data,
                                    },
                                })

                    if _last_is_user_list():
                        last_content = claude_msgs[-1]["content"]
                        # Claude does not allow mixing tool_result with other content types
                        # in the same user message. Instead embed the vision parts directly
                        # inside the last tool_result block's content field (explicitly
                        # allowed by the Claude spec: tool_result.content can be an array).
                        if last_content and last_content[-1].get("type") == "tool_result":
                            tr = last_content[-1]
                            existing = tr.get("content", "")
                            if isinstance(existing, str):
                                new_content = ([{"type": "text", "text": existing}]
                                               if existing else [])
                            else:
                                new_content = list(existing)
                            tr["content"] = new_content + parts
                        else:
                            last_content.extend(parts)
                    else:
                        claude_msgs.append({"role": "user", "content": parts})
                else:
                    claude_msgs.append({"role": "user", "content": content or ""})

        return system, claude_msgs

    def _to_claude_tools(self, tools: list) -> list:
        """Convert OpenAI-format tool schemas to Claude format."""
        result = []
        for t in tools:
            fn = t.get("function", {})
            result.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return result

    def _parse_claude_llm_response(self, data: dict) -> tuple:
        """Parse a Claude Messages API response into the internal response dict format."""
        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0) if isinstance(usage, dict) else 0
        output_tokens = usage.get("output_tokens", 0) if isinstance(usage, dict) else 0

        text = ""
        tool_calls = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", f"toolu_{int(time.time())}"),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                    },
                })

        response = {"content": text.strip()}
        if tool_calls:
            response["tool_calls"] = tool_calls

        total = input_tokens + output_tokens
        return response, total, input_tokens
