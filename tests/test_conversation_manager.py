# Tests for ConversationManager.
#
# This class persists chat history to disk and slices it into "last N turns"
# for the context window. The windowing logic is non-trivial — a turn boundary
# is defined as "a user message", which means a dangling assistant response
# (no preceding user message) needs special handling. Mistakes here either
# lose recent context or send way too much history (token waste).

import json
import os

import pytest

from qgis_ai_plugin.core.conversation_manager import ConversationManager


@pytest.fixture
def store(tmp_path):
    return ConversationManager(str(tmp_path), max_messages=20)


# ─────────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────────

def test_append_persists_message_to_disk(store, tmp_path):
    store.append("user", "hello")
    store.append("assistant", "hi")

    history_file = os.path.join(str(tmp_path), "conversation_history.json")
    assert os.path.exists(history_file)
    with open(history_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_messages_reload_from_disk_on_new_instance(tmp_path):
    a = ConversationManager(str(tmp_path), max_messages=20)
    a.append("user", "first")
    a.append("assistant", "second")

    b = ConversationManager(str(tmp_path), max_messages=20)
    assert b.get_messages() == a.get_messages()


def test_clear_purges_in_memory_and_writes_empty_file(store, tmp_path):
    store.append("user", "x")
    store.clear()
    assert store.get_messages() == []
    with open(os.path.join(str(tmp_path), "conversation_history.json")) as f:
        assert json.load(f) == []


def test_malformed_history_file_falls_back_to_empty(tmp_path):
    bad = os.path.join(str(tmp_path), "conversation_history.json")
    with open(bad, "w", encoding="utf-8") as f:
        f.write("{not json[")
    cm = ConversationManager(str(tmp_path), max_messages=20)
    assert cm.get_messages() == []


def test_entries_with_invalid_shape_are_silently_dropped(tmp_path):
    bad = os.path.join(str(tmp_path), "conversation_history.json")
    with open(bad, "w", encoding="utf-8") as f:
        json.dump([
            {"role": "user", "content": "ok"},
            {"role": "user"},                 # missing content
            {"content": "no role"},           # missing role
            "not a dict",
            {"role": "user", "content": 42},  # non-string content
        ], f)
    cm = ConversationManager(str(tmp_path), max_messages=20)
    assert cm.get_messages() == [{"role": "user", "content": "ok"}]


# ─────────────────────────────────────────────────────────────────────────
# Trimming
# ─────────────────────────────────────────────────────────────────────────

def test_history_is_trimmed_to_max_messages(tmp_path):
    cm = ConversationManager(str(tmp_path), max_messages=4)
    for i in range(10):
        cm.append("user", f"msg {i}")
    msgs = cm.get_messages()
    assert len(msgs) == 4
    # The oldest messages must be the ones discarded.
    assert msgs[0]["content"] == "msg 6"
    assert msgs[-1]["content"] == "msg 9"


# ─────────────────────────────────────────────────────────────────────────
# Turn windowing
# ─────────────────────────────────────────────────────────────────────────

def test_get_last_turns_with_zero_returns_empty(store):
    store.append("user", "hi")
    store.append("assistant", "hello")
    assert store.get_last_turns_messages(0) == []


def test_get_last_turns_with_none_returns_empty(store):
    store.append("user", "hi")
    assert store.get_last_turns_messages(None) == []


def test_get_last_turn_returns_only_the_most_recent_pair(store):
    store.append("user", "Q1")
    store.append("assistant", "A1")
    store.append("user", "Q2")
    store.append("assistant", "A2")
    out = store.get_last_turns_messages(1)
    assert out == [
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
    ]


def test_get_last_two_turns_returns_both_pairs(store):
    store.append("user", "Q1")
    store.append("assistant", "A1")
    store.append("user", "Q2")
    store.append("assistant", "A2")
    out = store.get_last_turns_messages(2)
    assert [m["content"] for m in out] == ["Q1", "A1", "Q2", "A2"]


def test_system_messages_excluded_from_turn_window(store):
    store.append("system", "system prompt")
    store.append("user", "Q1")
    store.append("assistant", "A1")
    out = store.get_last_turns_messages(5)
    assert all(m["role"] in ("user", "assistant") for m in out)
    assert [m["content"] for m in out] == ["Q1", "A1"]


def test_dangling_assistant_message_included_in_window(store):
    # If the conversation starts with an assistant message (e.g. an error or
    # a greeting before any user input), we still want to include it.
    store.append("assistant", "greeting before any user input")
    store.append("user", "Q1")
    store.append("assistant", "A1")
    out = store.get_last_turns_messages(5)
    assert [m["content"] for m in out] == [
        "greeting before any user input", "Q1", "A1",
    ]
