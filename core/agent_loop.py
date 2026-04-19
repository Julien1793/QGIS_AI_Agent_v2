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
import requests

from .tools_registry import get_schemas_for_intent, get_handler_name, REGISTRY
from . import tools_handlers as handlers
from ..utils.translation import get_translations


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
        tool_names = [tt["function"]["name"] for tt in tools]

        # 4 — Emit the detected intents and selected tools to the UI.
        intent_text = t["agent_step_intent_detected"].format(
            intents=", ".join(intents)
        )
        tools_text = t["agent_step_tools_selected"].format(
            count=len(tools),
            names=", ".join(tool_names),
        )
        self._emit(on_step, "intent",
                   f"{intent_text}\n{tools_text}",
                   data={"intents": intents, "tools": tool_names})

        # 5 — Build the initial message list (system prompt + history + current user message).
        history = [m for m in (history_messages or [])
                   if m.get("role") in ("user", "assistant")]
        messages = [
            {"role": "system", "content": t["agent_system_prompt"]},
            *history,
            {
                "role": "user",
                "content": (
                    f"{t['project_snapshot_intro']}\n```json\n{snapshot_json}\n```\n\n"
                    f"{user_prompt}"
                ),
            },
        ]

        # 6 — Agentic loop: LLM call → tool execution → tool result → next LLM call.
        total_tokens = 0
        for iteration in range(max_iter):

            # Skip the iteration event on the first turn to avoid cluttering the UI.
            if iteration > 0:
                self._emit(on_step, "iteration",
                           t["agent_step_iteration"].format(
                               current=iteration + 1, max=max_iter))

            response, usage = self._llm_call(messages, tools)
            total_tokens += usage

            # LLM call failed — emit an error event and abort the loop.
            if response is None:
                err_text = t["llm_request_error"]
                self._emit(on_step, "final", err_text)
                return err_text, total_tokens

            # The LLM returned a final text response with no further tool calls.
            if not response.get("tool_calls"):
                final_text = response.get("content") or ""
                self._emit(on_step, "final", final_text)
                return final_text, total_tokens

            # The LLM requested one or more tool calls — execute them.
            messages.append({"role": "assistant", **response})

            for tool_call in response["tool_calls"]:
                tool_name = tool_call["function"]["name"]
                try:
                    tool_args = json.loads(tool_call["function"]["arguments"])
                except Exception:
                    tool_args = {}

                # Emit the tool call event before execution so the UI can show it immediately.
                tool_call_text = t["agent_step_tool_calling"].format(tool=tool_name)
                self._emit(on_step, "tool_call", tool_call_text,
                           data={"name": tool_name, "args": tool_args})

                # Delegate to the external tool_executor (main thread) if provided, otherwise run locally.
                _execute = tool_executor or self._execute_tool
                result = _execute(tool_name, tool_args)

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
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

        # The agent hit the iteration cap without reaching a final answer.
        max_text = t["agent_step_max_iterations"].format(max=max_iter)
        self._emit(on_step, "max_iterations", max_text)
        return max_text, total_tokens

    # ══════════════════════════════════════════════════════════
    # Détection d'intention (LLM léger)
    # ══════════════════════════════════════════════════════════

    def _classify_intent(self, prompt: str, t: dict) -> list:
        """
        Lightweight LLM call to classify the user's intent.
        Falls back to ["read", "process"] if the call fails or returns no valid intents.
        """
        api_url = self.settings.get(
            "api_url", "http://localhost:1234/v1/chat/completions"
        )
        model = self.settings.get("model", "mistral")
        headers = {"Content-Type": "application/json"}
        if self.settings.get("mode") == "distant":
            key = self.settings.get("api_key", "")
            if key:
                headers["Authorization"] = f"Bearer {key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": t["agent_intent_system"]},
                {"role": "user",
                 "content": t["agent_intent_user"].format(prompt=prompt)},
            ],
            "max_tokens": 150,
            "temperature": 0,
        }

        try:
            resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()

            # Robustly extract the JSON object (the LLM may add surrounding prose).
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                intents = parsed.get("intents", [])
                if isinstance(intents, list) and intents:
                    # Keep only known intent values; discard anything unrecognised.
                    valid = {"read", "process", "select", "style",
                             "edit", "export", "analyse", "view"}
                    filtered = [i for i in intents if i in valid]
                    if filtered:
                        return filtered
        except Exception:
            pass

        return ["read", "process"]

    # ══════════════════════════════════════════════════════════
    # Appel LLM principal (avec tools)
    # ══════════════════════════════════════════════════════════

    def _llm_call(self, messages: list, tools: list) -> tuple:
        """
        Call the LLM with the current message history and tool schemas.
        Returns (response_dict, tokens_used). Returns (None, 0) on failure.
        """
        api_url = self.settings.get(
            "api_url", "http://localhost:1234/v1/chat/completions"
        )
        model = self.settings.get("model", "mistral")
        headers = {"Content-Type": "application/json"}
        if self.settings.get("mode") == "distant":
            key = self.settings.get("api_key", "")
            if key:
                headers["Authorization"] = f"Bearer {key}"

        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        try:
            resp = requests.post(api_url, json=payload, headers=headers, timeout=300)
            resp.raise_for_status()
            data = resp.json()

            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0

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

            return response, tokens

        except Exception:
            return None, 0

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
