# Tests for the bilingual translation dictionary.
#
# The plugin advertises a fully bilingual interface FR/EN. The translation
# system has 259 keys per language — large enough that adding a string in
# one language and forgetting the other is a real risk.
#
# IMPORTANT: get_translations(lang) returns `{**en, **cur}` — an EN-merged
# fallback. This is great for runtime robustness but USELESS for parity
# tests, because a key only defined in EN silently appears in the FR result
# too. The tests below therefore inspect the *physical* dicts via AST
# parsing of translation.py, not the merged runtime view.

import ast
import inspect
import re

import pytest

from qgis_ai_plugin.utils import translation as translation_module
from qgis_ai_plugin.utils.translation import get_translations


PLACEHOLDER_RE = re.compile(r"\{(\w*)\}")


# Keys that are intentionally defined ONLY in the EN dict.
# Rationale: these strings are sent to the LLM (system prompts, agent
# instructions, prompt prefixes) and LLMs follow English instructions more
# reliably. The user's interface language is signalled inside the prompt
# itself ("Reply in the user's language"), not by translating the prompt.
#
# If you intentionally want to add a new EN-only LLM-facing key, append it
# here with a brief justification comment. If a key shows up here that
# should actually be translated for the UI, move its translation into the
# FR dict instead.
ENGLISH_ONLY_KEYS = {
    # Core agent system prompts
    "agent_system_prompt",
    "agent_system_prompt_canvas_rules",
    "agent_system_prompt_planning",
    "agent_system_prompt_reasoning",
    "system_prompt_chat",
    "system_prompt_code",
    # Intent classification (lightweight LLM pre-call)
    "agent_intent_system",
    "agent_intent_user",
    # Mid-loop instructions injected as user/assistant turns
    "agent_replan_after_expansion",
    "agent_vision_screenshot_intro",
    "project_snapshot_intro",
    # Error / warning auto-fix prompts (chat mode)
    "code_to_fix",
    "error_fix_header",
    "error_fix_instruction",
    "warn_fix_header",
    "warn_fix_instruction",
}


# ─────────────────────────────────────────────────────────────────────────
# Physical-dict extraction (AST-based)
# ─────────────────────────────────────────────────────────────────────────
#
# We parse translation.py at test time to read the literal `translations`
# dict assignment inside get_translations(). This bypasses the EN-fallback
# merge and lets us see exactly which keys are physically present in each
# language. The fixture has module scope so the parsing happens once per run.

def _extract_physical_dicts():
    src = inspect.getsource(translation_module.get_translations)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "translations"
            for t in node.targets
        ):
            result = {}
            for k_lang, v_dict in zip(node.value.keys, node.value.values):
                if not isinstance(v_dict, ast.Dict):
                    continue
                items = {}
                for k_node, v_node in zip(v_dict.keys, v_dict.values):
                    if not isinstance(k_node, ast.Constant):
                        continue
                    # Resolve the value if it's a literal string or an
                    # implicit concatenation like ("foo" "bar").
                    try:
                        items[k_node.value] = ast.literal_eval(v_node)
                    except Exception:
                        items[k_node.value] = None
                result[k_lang.value] = items
            return result
    raise RuntimeError("Could not locate the 'translations' dict in get_translations()")


@pytest.fixture(scope="module")
def physical():
    return _extract_physical_dicts()


@pytest.fixture(scope="module")
def fr_keys(physical):
    return set(physical["fr"])


@pytest.fixture(scope="module")
def en_keys(physical):
    return set(physical["en"])


# ─────────────────────────────────────────────────────────────────────────
# Both dicts present and non-empty
# ─────────────────────────────────────────────────────────────────────────

def test_fr_dict_is_non_empty(physical):
    assert "fr" in physical
    assert len(physical["fr"]) > 0


def test_en_dict_is_non_empty(physical):
    assert "en" in physical
    assert len(physical["en"]) > 0


# ─────────────────────────────────────────────────────────────────────────
# Physical key parity (the real test)
# ─────────────────────────────────────────────────────────────────────────

def test_no_french_key_is_missing_from_english(fr_keys, en_keys):
    missing = sorted(fr_keys - en_keys)
    assert not missing, (
        f"{len(missing)} key(s) defined in FR but missing in EN: "
        f"{missing[:10]}{'...' if len(missing) > 10 else ''}"
    )


def test_english_only_keys_match_documented_allowlist(fr_keys, en_keys):
    en_only = en_keys - fr_keys

    unexpected_en_only = en_only - ENGLISH_ONLY_KEYS
    assert not unexpected_en_only, (
        f"{len(unexpected_en_only)} new EN-only key(s) detected. "
        "If they are LLM-facing prompts, add them to ENGLISH_ONLY_KEYS at the "
        "top of this test file with a justification comment. If they are UI "
        "strings, translate them in the FR dict.\n"
        f"Unexpected EN-only keys: {sorted(unexpected_en_only)}"
    )

    stale_allowlist_entries = ENGLISH_ONLY_KEYS - en_only
    assert not stale_allowlist_entries, (
        f"ENGLISH_ONLY_KEYS contains entries that no longer exist in EN-only: "
        f"{sorted(stale_allowlist_entries)}. Remove them from the allowlist."
    )


# ─────────────────────────────────────────────────────────────────────────
# Placeholder parity (only on keys that exist in both)
# ─────────────────────────────────────────────────────────────────────────

def test_format_placeholders_match_between_languages(physical):
    fr = physical["fr"]
    en = physical["en"]
    mismatches = []
    for key in set(fr) & set(en):
        fr_placeholders = sorted(PLACEHOLDER_RE.findall(str(fr[key])))
        en_placeholders = sorted(PLACEHOLDER_RE.findall(str(en[key])))
        if fr_placeholders != en_placeholders:
            mismatches.append((key, fr_placeholders, en_placeholders))
    assert not mismatches, (
        "Placeholder mismatch between FR and EN:\n  "
        + "\n  ".join(f"{k}: FR={f}, EN={e}" for k, f, e in mismatches)
    )


# ─────────────────────────────────────────────────────────────────────────
# Value sanity
# ─────────────────────────────────────────────────────────────────────────

def test_no_empty_strings_in_either_dict(physical):
    bad = []
    for lang, d in physical.items():
        for k, v in d.items():
            if isinstance(v, str) and not v.strip():
                bad.append(f"{lang}:{k}")
    assert not bad, f"Empty translation values: {bad}"


def test_every_value_is_a_string(physical):
    bad = {}
    for lang, d in physical.items():
        for k, v in d.items():
            if not isinstance(v, str):
                bad[f"{lang}:{k}"] = type(v).__name__
    assert not bad, f"Non-string translation values: {bad}"


def test_french_values_are_actually_translated_and_not_raw_english_keys(physical):
    fr = physical["fr"]
    same_as_key = [k for k, v in fr.items() if v == k]
    # A few keys legitimately equal their value ("Mode": "Mode") — allow up
    # to 10% of the dict before flagging as suspicious.
    assert len(same_as_key) < len(fr) * 0.1, (
        f"{len(same_as_key)} FR values equal their key — possible untranslated: "
        f"{same_as_key[:5]}"
    )


# ─────────────────────────────────────────────────────────────────────────
# Runtime fallback behaviour (the merged view)
# ─────────────────────────────────────────────────────────────────────────

def test_unknown_language_falls_back_to_english():
    en = get_translations("en")
    result = get_translations("klingon")
    assert result == en, "unknown lang must produce the EN dict verbatim"


def test_french_runtime_view_inherits_english_only_keys():
    # The merge fallback is the documented behaviour — verify it works for
    # every EN-only key listed in the allowlist.
    fr_runtime = get_translations("fr")
    en_runtime = get_translations("en")
    for key in ENGLISH_ONLY_KEYS:
        if key in en_runtime:
            assert fr_runtime.get(key) == en_runtime[key], (
                f"EN-only key {key!r} should fall back to its EN value at runtime"
            )


# ─────────────────────────────────────────────────────────────────────────
# Smoke test on critical user-facing keys
# ─────────────────────────────────────────────────────────────────────────
#
# These keys are referenced from agent_loop.py with .format() calls. They
# MUST be in both physical dicts (not just inherited via fallback) because
# they are part of the UI experience that should be translated.

CRITICAL_UI_KEYS = [
    "agent_step_thinking",
    "agent_step_intent_detected",
    "agent_step_tools_selected",
    "agent_step_iteration",
    "agent_step_tool_calling",
    "agent_step_tool_success",
    "agent_step_tool_error",
    "agent_step_max_iterations",
    "llm_request_error",
    "llm_backend_error",
]


@pytest.mark.parametrize("key", CRITICAL_UI_KEYS)
def test_critical_ui_key_exists_physically_in_both_languages(physical, key):
    assert key in physical["fr"], (
        f"Critical UI key {key!r} missing from physical FR dict — it would "
        "silently fall back to EN at runtime, breaking the bilingual UI."
    )
    assert key in physical["en"], f"Critical UI key {key!r} missing from EN"
