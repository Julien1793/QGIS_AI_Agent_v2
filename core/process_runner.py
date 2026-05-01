# core/process_runner.py
#
# Loads and replays .aiprocess.json files.
# Variable placeholders ({v_xxx}) are substituted with user-supplied values
# before each step is dispatched to the existing AgentLoop tool executor.

import json
import os
import re

from ..utils.translation import get_translations


PROCESS_EXTENSION = ".aiprocess.json"


# ──────────────────────────────────────────────────────────────
# I/O helpers
# ──────────────────────────────────────────────────────────────

def save_process(process_dict: dict, base_folder: str) -> str:
    """
    Write process_dict to <base_folder>/<folder>/<safe_name>.aiprocess.json.
    Returns the absolute path of the written file.
    Raises OSError on failure.
    """
    folder_name = _safe_filename(process_dict.get("folder", "").strip() or "General")
    name = _safe_filename(process_dict.get("name", "").strip() or "process")

    target_dir = os.path.join(base_folder, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    filepath = os.path.join(target_dir, name + PROCESS_EXTENSION)
    # Avoid silently overwriting — append a counter if needed.
    counter = 1
    base_path = filepath
    while os.path.exists(filepath):
        filepath = base_path.replace(PROCESS_EXTENSION,
                                     f"_{counter}{PROCESS_EXTENSION}")
        counter += 1

    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(process_dict, fh, ensure_ascii=False, indent=2)

    return filepath


def load_process(filepath: str) -> dict:
    """Load and return a process dict from a .aiprocess.json file."""
    with open(filepath, "r", encoding="utf-8") as fh:
        return json.load(fh)


def list_processes(base_folder):
    """
    Walk base_folder recursively and return a list of dicts:
        { path, name, description, folder }
    sorted by folder then name.
    """
    results = []
    if not os.path.isdir(base_folder):
        return results
    for root, dirs, files in os.walk(base_folder):
        dirs.sort()
        for fname in sorted(files):
            if fname.endswith(PROCESS_EXTENSION):
                fpath = os.path.join(root, fname)
                try:
                    p = load_process(fpath)
                    results.append({
                        "path": fpath,
                        "name": p.get("name", fname),
                        "description": p.get("description", ""),
                        "folder": p.get("folder", ""),
                    })
                except Exception:
                    pass
    return results


def delete_process(filepath: str):
    """Delete a saved process file."""
    os.remove(filepath)


def overwrite_process(process_dict: dict, filepath: str) -> str:
    """
    Overwrite an existing process file at the given path.
    Returns the filepath.
    """
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(process_dict, fh, ensure_ascii=False, indent=2)
    return filepath


# ──────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────

class ProcessRunner:
    """
    Replays a saved process with user-supplied variable values.

    Usage:
        runner = ProcessRunner(agent_loop)
        for event in runner.run(process_dict, variable_values):
            # event is {"type", "text", "data", "success" (optional)}
            ...
    """

    def __init__(self, agent_loop, language="en"):
        self._loop = agent_loop
        self._language = language

    def run(self, process_dict: dict, variable_values: dict, tool_executor=None):
        """
        Generator — yields progress event dicts as steps execute.

        variable_values: {variable_id: value_string}
        tool_executor: optional callable(tool_name, args) -> dict that runs
                       tool calls on the correct thread.  When omitted,
                       _execute_tool is called directly (safe only on the
                       main thread).
        """
        t = get_translations(self._language)
        steps = process_dict.get("steps", [])
        total = len(steps)
        variables = {v["id"]: v for v in process_dict.get("variables", [])}
        name = process_dict.get("name", "")

        execute_fn = tool_executor if tool_executor is not None else self._loop._execute_tool

        yield _evt("start", t["process_evt_start"].format(name=name, total=total))

        for idx, step in enumerate(steps):
            tool_name = step.get("tool", "")
            raw_params = step.get("params", {})

            # Substitute {v_xxx} placeholders
            params = _substitute(raw_params, variable_values, variables)

            # Handle run_pyqgis_code: also substitute the "code" field
            if tool_name == "run_pyqgis_code" and "code" in step:
                raw_code = step["code"]
                params["code"] = _substitute_str(raw_code, variable_values)

            yield _evt("tool_call",
                       t["process_evt_step_call"].format(idx=idx + 1, total=total, tool=tool_name),
                       data={"name": tool_name, "args": params})

            result = execute_fn(tool_name, params)

            if result.get("success"):
                yield _evt("tool_result",
                           t["process_evt_step_ok"].format(idx=idx + 1),
                           data={"name": tool_name, "result": result})
            else:
                error = result.get("error", t["process_evt_unknown_error"])
                if len(error) > 400:
                    error = error[:400] + "..."
                yield _evt("tool_error",
                           t["process_evt_step_error"].format(idx=idx + 1, error=error),
                           data={"name": tool_name, "result": result})
                yield _evt("aborted", t["process_evt_aborted"].format(idx=idx + 1))
                return

        yield _evt("done", t["process_evt_done"].format(name=name, total=total))


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

_PLACEHOLDER_RE = re.compile(r"^\{(v_[a-zA-Z0-9_]+)\}$")


def _substitute(params: dict, values: dict, variables: dict = None) -> dict:
    result = {}
    for k, v in params.items():
        if isinstance(v, str):
            substituted = _substitute_str(v, values)
            # When the entire value was a single placeholder, coerce back to
            # the original type so handlers receive float/int/bool, not str.
            m = _PLACEHOLDER_RE.match(v)
            if m and variables:
                default = variables.get(m.group(1), {}).get("default")
                substituted = _coerce(substituted, default)
            result[k] = substituted
        else:
            result[k] = v
    return result


def _coerce(s: str, default):
    """Cast string s to the same Python type as default."""
    if isinstance(default, bool):
        return s.lower() in ("true", "1", "yes")
    if isinstance(default, int):
        try:
            return int(s)
        except (ValueError, TypeError):
            return s
    if isinstance(default, float):
        try:
            return float(s)
        except (ValueError, TypeError):
            return s
    # default is itself a string — infer numeric/bool type from its content
    if isinstance(default, str):
        dl = default.strip().lower()
        if dl in ("true", "false"):
            return s.strip().lower() in ("true", "1", "yes")
        try:
            if "." in default:
                return float(s)
            # default looks like an integer ("9"), but s may be "9.0" from a
            # QDoubleSpinBox — int("9.0") would raise, so go through float first.
            int(default)
            return int(float(s))
        except (ValueError, TypeError):
            pass
    return s


def _substitute_str(s: str, values: dict) -> str:
    def replacer(m):
        var_id = m.group(1)
        return str(values.get(var_id, m.group(0)))
    return re.sub(r"\{(v_[a-zA-Z0-9_]+)\}", replacer, s)


def _safe_filename(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "_", s)
    return s.strip(".").strip() or "process"


def _evt(event_type: str, text: str, data: dict = None) -> dict:
    return {"type": event_type, "text": text, "data": data or {}}
