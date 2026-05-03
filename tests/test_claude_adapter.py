# Tests for the OpenAI -> Claude format conversion layer in agent_loop.py.
#
# These three functions (_to_claude_messages, _to_claude_tools,
# _parse_claude_llm_response) are the entire bridge between our internal
# OpenAI-shaped state and the Anthropic Messages API. A bug here breaks
# every Claude request and is hard to spot from logs because the API just
# returns 400 with a generic message. Pure functions on dicts -> easy to test.

from unittest.mock import MagicMock

import pytest

from qgis_ai_plugin.core.agent_loop import AgentLoop


@pytest.fixture
def loop():
    # AgentLoop only touches self.settings during HTTP calls, never inside
    # the conversion helpers — a MagicMock is enough.
    return AgentLoop(settings_manager=MagicMock())


# ─────────────────────────────────────────────────────────────────────────
# _to_claude_messages
# ─────────────────────────────────────────────────────────────────────────

def test_system_message_extracted_to_top_level(loop):
    msgs = [
        {"role": "system", "content": "You are a QGIS expert."},
        {"role": "user", "content": "Hello"},
    ]
    system, claude_msgs = loop._to_claude_messages(msgs)
    assert system == "You are a QGIS expert."
    assert claude_msgs == [{"role": "user", "content": "Hello"}]


def test_tool_role_becomes_tool_result_block_in_user_message(loop):
    msgs = [
        {"role": "user", "content": "buffer the layer"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "tool_1", "type": "function",
             "function": {"name": "buffer", "arguments": '{"d": 50}'}},
        ]},
        {"role": "tool", "tool_call_id": "tool_1",
         "content": '{"success": true}'},
    ]
    _, claude_msgs = loop._to_claude_messages(msgs)
    # Last message must be a user message containing the tool_result block.
    assert claude_msgs[-1]["role"] == "user"
    assert isinstance(claude_msgs[-1]["content"], list)
    block = claude_msgs[-1]["content"][0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "tool_1"
    assert block["content"] == '{"success": true}'


def test_consecutive_tool_results_merged_into_single_user_message(loop):
    # Claude rejects two consecutive `user` messages — they MUST be merged.
    msgs = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "type": "function",
             "function": {"name": "f1", "arguments": "{}"}},
            {"id": "t2", "type": "function",
             "function": {"name": "f2", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "t1", "content": "ok1"},
        {"role": "tool", "tool_call_id": "t2", "content": "ok2"},
    ]
    _, claude_msgs = loop._to_claude_messages(msgs)
    user_msgs = [m for m in claude_msgs if m["role"] == "user"]
    assert len(user_msgs) == 1, "tool results must be merged into a single user message"
    blocks = user_msgs[0]["content"]
    assert [b["tool_use_id"] for b in blocks] == ["t1", "t2"]


def test_assistant_with_text_and_tool_calls_produces_content_array(loop):
    msgs = [
        {"role": "assistant",
         "content": "Let me check the layer first.",
         "tool_calls": [
             {"id": "t1", "type": "function",
              "function": {"name": "get_layer_info",
                           "arguments": '{"layer_name": "roads"}'}},
         ]},
    ]
    _, claude_msgs = loop._to_claude_messages(msgs)
    assert claude_msgs[0]["role"] == "assistant"
    blocks = claude_msgs[0]["content"]
    # Text MUST come before tool_use — Claude rejects the inverse ordering.
    assert blocks[0] == {"type": "text", "text": "Let me check the layer first."}
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["name"] == "get_layer_info"
    assert blocks[1]["input"] == {"layer_name": "roads"}


def test_canvas_image_embedded_inside_last_tool_result(loop):
    # Claude does NOT allow mixing tool_result with other content blocks in
    # the same user message. The agent_loop solution: nest the image inside
    # the tool_result.content array instead of appending it as a sibling.
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    msgs = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "cap_1", "type": "function",
             "function": {"name": "capture_map_canvas", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "cap_1",
         "content": '{"success": true}'},
        {"role": "user", "content": [
            {"type": "text", "text": "Here is the canvas:"},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{png_b64}"}},
        ]},
    ]
    _, claude_msgs = loop._to_claude_messages(msgs)
    last_user = claude_msgs[-1]
    assert last_user["role"] == "user"
    # The user message must have exactly one block: the tool_result.
    blocks = last_user["content"]
    assert len(blocks) == 1
    assert blocks[0]["type"] == "tool_result"
    # The image must be embedded INSIDE the tool_result.content array.
    nested = blocks[0]["content"]
    assert isinstance(nested, list)
    assert any(b.get("type") == "image" for b in nested), \
        "image must be embedded inside the tool_result.content"


def test_image_media_type_detected_from_jpeg_magic_bytes(loop):
    # QGIS sometimes saves a JPEG but labels the data URL as image/png.
    # The adapter must trust the magic bytes, not the URL header.
    jpeg_b64 = "/9j/4AAQSkZJRgABAQEASABIAAD/"
    msgs = [
        {"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{jpeg_b64}"}},
        ]},
    ]
    _, claude_msgs = loop._to_claude_messages(msgs)
    img_block = claude_msgs[0]["content"][0]
    assert img_block["source"]["media_type"] == "image/jpeg"


def test_image_media_type_detected_from_png_magic_bytes(loop):
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4"
    msgs = [
        {"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{png_b64}"}},
        ]},
    ]
    _, claude_msgs = loop._to_claude_messages(msgs)
    assert claude_msgs[0]["content"][0]["source"]["media_type"] == "image/png"


# ─────────────────────────────────────────────────────────────────────────
# _to_claude_tools
# ─────────────────────────────────────────────────────────────────────────

def test_openai_tool_schema_converted_to_claude_format(loop):
    openai_tools = [{
        "type": "function",
        "function": {
            "name": "buffer",
            "description": "Apply a buffer.",
            "parameters": {
                "type": "object",
                "properties": {"distance": {"type": "number"}},
                "required": ["distance"],
            },
        },
    }]
    claude_tools = loop._to_claude_tools(openai_tools)
    assert claude_tools == [{
        "name": "buffer",
        "description": "Apply a buffer.",
        "input_schema": {
            "type": "object",
            "properties": {"distance": {"type": "number"}},
            "required": ["distance"],
        },
    }]


def test_tool_schema_with_no_parameters_falls_back_to_empty_object(loop):
    openai_tools = [{
        "type": "function",
        "function": {"name": "ping", "description": "ping"},
    }]
    claude_tools = loop._to_claude_tools(openai_tools)
    assert claude_tools[0]["input_schema"] == {"type": "object", "properties": {}}


# ─────────────────────────────────────────────────────────────────────────
# _parse_claude_llm_response
# ─────────────────────────────────────────────────────────────────────────

def test_parse_text_only_response(loop):
    data = {
        "content": [{"type": "text", "text": "Done."}],
        "usage": {"input_tokens": 100, "output_tokens": 5},
    }
    response, total, prompt = loop._parse_claude_llm_response(data)
    assert response == {"content": "Done."}
    assert total == 105
    assert prompt == 100


def test_parse_response_with_tool_use_block(loop):
    data = {
        "content": [
            {"type": "text", "text": "Calling buffer."},
            {"type": "tool_use", "id": "toolu_42",
             "name": "buffer", "input": {"distance": 50}},
        ],
        "usage": {"input_tokens": 200, "output_tokens": 30},
    }
    response, total, prompt = loop._parse_claude_llm_response(data)
    assert response["content"] == "Calling buffer."
    assert len(response["tool_calls"]) == 1
    tc = response["tool_calls"][0]
    assert tc["id"] == "toolu_42"
    assert tc["function"]["name"] == "buffer"
    # Arguments are JSON-serialized to stay compatible with the OpenAI shape.
    import json
    assert json.loads(tc["function"]["arguments"]) == {"distance": 50}
    assert total == 230
    assert prompt == 200


def test_parse_empty_response_returns_no_tool_calls_key(loop):
    data = {"content": [{"type": "text", "text": ""}],
            "usage": {"input_tokens": 0, "output_tokens": 0}}
    response, _, _ = loop._parse_claude_llm_response(data)
    assert response == {"content": ""}
    assert "tool_calls" not in response
