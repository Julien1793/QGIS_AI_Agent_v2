# core/process_recorder.py
#
# Accumulates tool calls emitted by the agent loop so they can later be
# saved as a reusable custom process (.aiprocess.json).

import re


# Parameter names that are candidates for becoming user-facing variables.
_LAYER_PARAMS   = {"layer_name", "layer", "source_layer", "input_layer",
                   "target_layer", "join_layer", "overlay_layer"}
_FIELD_PARAMS   = {"field_name", "field", "join_field", "target_field",
                   "source_field", "color_field", "value_field"}
_FILE_PARAMS    = {"output_path", "file_path", "path", "output", "filepath"}
_CRS_PARAMS     = {"crs", "crs_code", "target_crs", "source_crs"}
_COLOR_PARAMS   = {"color", "text_color", "buffer_color", "halo_color",
                   "fill_color", "stroke_color", "outline_color",
                   "background_color", "shadow_color"}
_NUMBER_PARAMS  = {"opacity", "size", "distance", "width", "min_value",
                   "max_value", "num_classes", "buffer_size", "offset_x",
                   "offset_y", "rotation", "min_scale", "max_scale",
                   "stroke_width", "blur_radius", "offset_distance",
                   "offset_angle", "font_size", "size_x", "size_y"}
_BOOL_PARAMS    = {"enabled", "visible", "bold", "italic", "underline"}
_VALUE_PARAMS   = {"value", "expression", "filter_expression", "label"}


class ProcessRecorder:
    """Listens to agent-loop step events and records tool calls."""

    def __init__(self):
        self.steps = []      # list of {tool, params, code (optional)}
        self._recording = False
        self._pending = None  # tool call awaiting result confirmation

    def start(self):
        self.steps = []
        self._recording = True
        self._pending = None

    def stop(self):
        self._recording = False
        self._pending = None

    def on_step(self, event):
        if not self._recording:
            return
        event_type = event.get("type")
        data = event.get("data", {})

        if event_type == "tool_call":
            tool_name = data.get("name", "")
            args = dict(data.get("args") or {})
            step = {"tool": tool_name, "params": args}
            # Keep the raw PyQGIS code separately so it can be displayed in the editor.
            if tool_name == "run_pyqgis_code" and "code" in args:
                step["code"] = args["code"]
            # Hold every tool call until we know whether it succeeded.
            self._pending = step

        elif event_type == "tool_result":
            # Tool succeeded — commit it.
            if self._pending is not None:
                self.steps.append(self._pending)
                self._pending = None

        elif event_type == "tool_error":
            # Tool failed — discard it silently.
            self._pending = None

    # ------------------------------------------------------------------
    # Variable detection
    # ------------------------------------------------------------------

    def detect_variables(self):
        """
        Scan all recorded step params and return a list of candidate variable dicts.

        Each variable dict has keys:
            id        - unique identifier, e.g. "v_layer_0"
            label     - human-friendly default label
            type      - "layer" | "field" | "file" | "crs" | "color" | "number" | "boolean" | "value" | "code"
            default   - the value captured from the agent run
            step_tool - tool name of the first step that defines this variable
            step_num  - 1-based index of that step
            refs      - list of (step_index, param_key) where this value appears
        """
        # Key: (type, param_name, value) — param_name prevents merging semantically
        # distinct params that happen to share the same value (e.g. stroke_color and
        # label color both "#FFFFFF" would otherwise become the same variable).
        # Same-named params across different steps ARE still merged (e.g. layer_name).
        seen = {}

        for step_idx, step in enumerate(self.steps):
            tool = step["tool"]
            params = step.get("params", {})

            for key, value in params.items():
                if key in ("iface", "executor") or value is None:
                    continue
                var_type = _infer_type(key)
                if var_type is None:
                    continue
                sig = (var_type, key, str(value))
                if sig not in seen:
                    idx = len(seen)
                    seen[sig] = {
                        "id": "v_{}_{}".format(var_type, idx),
                        "label": _default_label(key),
                        "type": var_type,
                        "default": value,
                        "step_tool": tool,
                        "step_num": step_idx + 1,
                        "refs": [],
                    }
                seen[sig]["refs"].append((step_idx, key))

            # PyQGIS code blocks get their own "code" variable
            if tool == "run_pyqgis_code" and "code" in step:
                sig = ("code", step["code"])
                if sig not in seen:
                    idx = len(seen)
                    seen[sig] = {
                        "id": "v_code_{}".format(idx),
                        "label": "Code PyQGIS",
                        "type": "code",
                        "default": step["code"],
                        "refs": [(step_idx, "code")],
                    }
                else:
                    seen[sig]["refs"].append((step_idx, "code"))

        # Return in step order (first reference of each variable)
        all_vars = list(seen.values())
        all_vars.sort(key=lambda v: v["refs"][0][0] if v["refs"] else 9999)
        return all_vars

    def build_process_dict(self, name, description, folder, variables):
        """
        Build the complete .aiprocess.json structure ready to be saved.

        variables - the (possibly user-edited) list returned by detect_variables().
        """
        # Build a lookup: (step_idx, param_key) -> variable id
        ref_map = {}
        for var in variables:
            for ref in var.get("refs", []):
                ref_map[tuple(ref)] = var["id"]

        # Rebuild steps with {v_xxx} placeholders
        templated_steps = []
        for step_idx, step in enumerate(self.steps):
            new_params = {}
            for key, value in step.get("params", {}).items():
                ref = (step_idx, key)
                if ref in ref_map:
                    new_params[key] = "{" + ref_map[ref] + "}"
                else:
                    new_params[key] = value
            ts = {"tool": step["tool"], "params": new_params}
            if "code" in step:
                ref = (step_idx, "code")
                if ref in ref_map:
                    ts["code"] = "{" + ref_map[ref] + "}"
                else:
                    ts["code"] = step["code"]
            templated_steps.append(ts)

        return {
            "version": 1,
            "name": name,
            "description": description,
            "folder": folder,
            "variables": [
                {k: v for k, v in var.items() if k != "refs"}
                for var in variables
            ],
            "steps": templated_steps,
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _infer_type(param_key):
    key = param_key.lower()
    if key in _LAYER_PARAMS:
        return "layer"
    if key in _FIELD_PARAMS:
        return "field"
    if key in _FILE_PARAMS:
        return "file"
    if key in _CRS_PARAMS:
        return "crs"
    if key in _COLOR_PARAMS:
        return "color"
    if key in _NUMBER_PARAMS:
        return "number"
    if key in _BOOL_PARAMS:
        return "boolean"
    if key in _VALUE_PARAMS:
        return "value"
    if key.endswith("_layer") or ("layer" in key and key.endswith("_name")):
        return "layer"
    if key.endswith("_field"):
        return "field"
    if key.endswith("_path") or key.endswith("_file"):
        return "file"
    if key.endswith("_color"):
        return "color"
    if key.endswith(("_opacity", "_size", "_width", "_distance", "_radius")):
        return "number"
    return None


def _default_label(param_key):
    return param_key.replace("_", " ").capitalize()
