import pytest
from chat.tool_parser import parse_tool_calls


def test_parse_json_tool_call():
    """Model outputs clean JSON tool call."""
    text = '{"name": "web_search", "arguments": {"query": "python tutorials"}}'
    calls = parse_tool_calls(text, ["web_search", "calculator", "weather"])
    assert len(calls) == 1
    assert calls[0]["name"] == "web_search"
    assert calls[0]["arguments"]["query"] == "python tutorials"


def test_parse_json_in_markdown_block():
    """Model wraps tool call in ```json block."""
    text = '''Let me search for that.
```json
{"name": "web_search", "arguments": {"query": "best restaurants Portland"}}
```'''
    calls = parse_tool_calls(text, ["web_search", "calculator"])
    assert len(calls) == 1
    assert calls[0]["name"] == "web_search"


def test_parse_multiple_json_calls():
    """Model outputs multiple tool calls."""
    text = '''```json
{"name": "web_search", "arguments": {"query": "Portland activities"}}
```
```json
{"name": "weather", "arguments": {"location": "Portland, OR"}}
```'''
    calls = parse_tool_calls(text, ["web_search", "weather"])
    assert len(calls) == 2


def test_fallback_search_intent():
    """No JSON, but model expresses search intent."""
    text = "Let me search for the best restaurants in Portland for you."
    calls = parse_tool_calls(text, ["web_search", "calculator"])
    assert len(calls) == 1
    assert calls[0]["name"] == "web_search"
    assert "restaurants" in calls[0]["arguments"]["query"].lower()


def test_fallback_weather_intent():
    text = "Let me check the weather in Portland, OR."
    calls = parse_tool_calls(text, ["web_search", "weather"])
    assert len(calls) == 1
    assert calls[0]["name"] == "weather"


def test_fallback_url_intent():
    text = "Let me fetch the page at https://example.com/article for you."
    calls = parse_tool_calls(text, ["url_fetch", "web_search"])
    assert len(calls) == 1
    assert calls[0]["name"] == "url_fetch"
    assert calls[0]["arguments"]["url"] == "https://example.com/article"


def test_fallback_calculator_intent():
    text = "Let me calculate that: 15% of 250 is"
    calls = parse_tool_calls(text, ["calculator", "web_search"])
    assert len(calls) == 1
    assert calls[0]["name"] == "calculator"


def test_no_tool_call():
    """Regular response with no tool intent."""
    text = "The capital of France is Paris. It's a beautiful city."
    calls = parse_tool_calls(text, ["web_search", "calculator"])
    assert len(calls) == 0


def test_invalid_json_ignored():
    text = '{"name": "unknown_tool", "arguments": {}}'
    calls = parse_tool_calls(text, ["web_search", "calculator"])
    assert len(calls) == 0
