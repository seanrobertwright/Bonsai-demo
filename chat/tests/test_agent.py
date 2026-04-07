import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from chat.agent import AgentLoop


class FakeToolRegistry:
    def __init__(self):
        self._tools = {}

    def register_fake(self, name, result):
        tool = MagicMock()
        tool.definition = {"name": name, "description": f"Fake {name}", "parameters": {"type": "object", "properties": {}}}
        tool.execute = AsyncMock(return_value=result)
        self._tools[name] = tool

    def get(self, name):
        return self._tools.get(name)

    def list_tools(self):
        return [t.definition for t in self._tools.values()]

    def list_names(self):
        return list(self._tools.keys())


@pytest.fixture
def registry():
    reg = FakeToolRegistry()
    reg.register_fake("web_search", {"results": [{"title": "Test", "snippet": "A test result", "url": "https://example.com"}]})
    reg.register_fake("calculator", {"result": "42"})
    return reg


def test_build_system_prompt(registry):
    agent = AgentLoop(registry, llama_base_url="http://localhost:8080")
    prompt = agent._build_system_prompt()
    assert "web_search" in prompt
    assert "calculator" in prompt
    assert "JSON" in prompt


def test_format_tool_result():
    agent = AgentLoop(MagicMock(), llama_base_url="http://localhost:8080")
    result = agent._format_tool_result("web_search", {"results": [{"title": "Test"}]})
    assert "web_search" in result
    assert "Test" in result
