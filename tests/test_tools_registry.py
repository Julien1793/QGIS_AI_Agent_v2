# Tests for the tool registry integrity.
#
# The registry has 78 entries split across two files (tools_registry.py for
# schemas, tools_handlers.py for implementations) that MUST stay in sync.
# A typo in a handler name, a missing intent, or a duplicate tool name fails
# silently at runtime — the agent just gets "Unknown tool" or never sees the
# tool at all. These tests catch that at import time.

from qgis_ai_plugin.core import tools_handlers as handlers
from qgis_ai_plugin.core.tools_registry import (
    REGISTRY,
    TOOLS_BY_INTENT,
    get_handler_name,
    get_schemas_for_intent,
)


VALID_INTENTS = {
    "read", "stats", "process", "join", "select", "style", "label",
    "field", "layer", "view", "raster",
    "__always__", "__fallback__", "__plan__",
}


# ─────────────────────────────────────────────────────────────────────────
# Cross-file integrity (registry <-> handlers)
# ─────────────────────────────────────────────────────────────────────────

# Meta-tools handled inline in agent_loop._apply_tool_plan / _expand_tools.
# Their handler field is intentionally None — they bypass the tools_handlers
# dispatch entirely.
META_TOOLS = {"declare_tool_plan", "request_additional_tools"}


def test_every_registered_handler_exists_in_handlers_module():
    missing = []
    for tool_name, definition in REGISTRY.items():
        handler_name = definition["handler"]
        if handler_name is None:
            assert tool_name in META_TOOLS, (
                f"{tool_name} has handler=None but is not a known meta-tool")
            continue
        if not hasattr(handlers, handler_name):
            missing.append(f"{tool_name} -> {handler_name}")
    assert not missing, f"Handlers declared in registry but not implemented: {missing}"


def test_get_handler_name_returns_correct_value_for_known_tool():
    assert get_handler_name("buffer") == "buffer"
    assert get_handler_name("get_layer_fields") == "get_layer_fields"


def test_get_handler_name_returns_empty_for_unknown_tool():
    assert get_handler_name("does_not_exist") in ("", None)


# ─────────────────────────────────────────────────────────────────────────
# Schema shape
# ─────────────────────────────────────────────────────────────────────────

def test_every_schema_has_required_openai_fields():
    bad = []
    for tool_name, definition in REGISTRY.items():
        schema = definition["schema"]
        if schema.get("type") != "function":
            bad.append(f"{tool_name}: type != 'function'")
            continue
        fn = schema.get("function", {})
        if fn.get("name") != tool_name:
            bad.append(f"{tool_name}: schema.function.name mismatch ({fn.get('name')!r})")
        if not fn.get("description"):
            bad.append(f"{tool_name}: missing description")
        params = fn.get("parameters", {})
        if params.get("type") != "object":
            bad.append(f"{tool_name}: parameters.type must be 'object'")
    assert not bad, "Schema shape violations: " + "; ".join(bad)


def test_every_tool_declares_at_least_one_intent():
    orphans = [name for name, d in REGISTRY.items() if not d.get("intents")]
    assert not orphans, f"Tools without intents (will never be exposed): {orphans}"


def test_every_intent_is_in_the_known_set():
    bad = []
    for name, d in REGISTRY.items():
        for intent in d["intents"]:
            if intent not in VALID_INTENTS:
                bad.append(f"{name}: unknown intent {intent!r}")
    assert not bad, "Unknown intents: " + "; ".join(bad)


# ─────────────────────────────────────────────────────────────────────────
# Intent-based tool selection
# ─────────────────────────────────────────────────────────────────────────

def test_chat_only_intent_still_includes_always_and_fallback_tools():
    # Pure chat requests still need request_additional_tools (escape hatch)
    # and run_pyqgis_code (last resort).
    schemas = get_schemas_for_intent(["chat"])
    names = {s["function"]["name"] for s in schemas}
    assert "request_additional_tools" in names
    assert "run_pyqgis_code" in names


def test_read_intent_includes_core_inspection_tools():
    schemas = get_schemas_for_intent(["read"])
    names = {s["function"]["name"] for s in schemas}
    for tool in ("get_project_info", "get_layer_info", "get_layer_fields"):
        assert tool in names, f"{tool} should be exposed for the 'read' intent"


def test_multiple_intents_do_not_produce_duplicate_tools():
    # __always__ tools are added for every intent — the registry helper
    # must dedupe them before returning the schema list.
    schemas = get_schemas_for_intent(["read", "stats", "style"])
    names = [s["function"]["name"] for s in schemas]
    assert len(names) == len(set(names)), \
        f"Duplicates in tool list: {[n for n in names if names.count(n) > 1]}"


def test_fallback_tools_appear_after_intent_tools_in_ordering():
    schemas = get_schemas_for_intent(["read"])
    names = [s["function"]["name"] for s in schemas]
    # run_pyqgis_code should be last so a smart LLM tries native tools first.
    assert names[-1] == "run_pyqgis_code"


def test_no_duplicate_tool_names_in_registry():
    # The dict structure prevents this at the language level, but a dev who
    # forgets to rename when copy-pasting can collapse two entries silently.
    # This test just ensures every tool maps back to itself via its schema.
    for name, d in REGISTRY.items():
        assert d["schema"]["function"]["name"] == name, \
            f"Registry key {name!r} disagrees with schema name {d['schema']['function']['name']!r}"


def test_intent_index_matches_registry():
    # TOOLS_BY_INTENT is built from REGISTRY at import — verify it's consistent.
    for tool_name, definition in REGISTRY.items():
        for intent in definition["intents"]:
            assert tool_name in TOOLS_BY_INTENT[intent], \
                f"{tool_name} declared for {intent} but missing from index"
