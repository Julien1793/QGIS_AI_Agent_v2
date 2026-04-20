# core/process_runner.py
#
# Loads and replays .aiprocess.json files.
# Variable placeholders ({v_xxx}) are substituted with user-supplied values
# before each step is dispatched to the existing AgentLoop tool executor.

import json
import os
import re


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

    def __init__(self, agent_loop):
        self._loop = agent_loop

    def run(self, process_dict: dict, variable_values: dict):
        """
        Generator — yields progress event dicts as steps execute.

        variable_values: {variable_id: value_string}
        """
        steps = process_dict.get("steps", [])
        total = len(steps)

        yield _evt("start", f"Démarrage du traitement « {process_dict.get('name', '')} » ({total} étapes)")

        for idx, step in enumerate(steps):
            tool_name = step.get("tool", "")
            raw_params = step.get("params", {})

            # Substitute {v_xxx} placeholders
            params = _substitute(raw_params, variable_values)

            # Handle run_pyqgis_code: also substitute the "code" field
            if tool_name == "run_pyqgis_code" and "code" in step:
                raw_code = step["code"]
                params["code"] = _substitute_str(raw_code, variable_values)

            yield _evt("tool_call",
                       f"Étape {idx + 1}/{total} : {tool_name}",
                       data={"name": tool_name, "args": params})

            result = self._loop._execute_tool(tool_name, params)

            if result.get("success"):
                yield _evt("tool_result",
                           f"✓ Étape {idx + 1} réussie",
                           data={"name": tool_name, "result": result})
            else:
                error = result.get("error", "Erreur inconnue")
                if len(error) > 400:
                    error = error[:400] + "..."
                yield _evt("tool_error",
                           f"✗ Étape {idx + 1} échouée : {error}",
                           data={"name": tool_name, "result": result})
                yield _evt("aborted", f"Traitement interrompu à l'étape {idx + 1}.")
                return

        yield _evt("done", f"Traitement « {process_dict.get('name', '')} » terminé ({total} étapes).")


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _substitute(params: dict, values: dict) -> dict:
    result = {}
    for k, v in params.items():
        if isinstance(v, str):
            result[k] = _substitute_str(v, values)
        else:
            result[k] = v
    return result


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
