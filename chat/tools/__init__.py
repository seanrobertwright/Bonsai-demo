"""Tool registry — discovers and manages available tools."""

from typing import Protocol


class Tool(Protocol):
    """Interface every tool must implement."""

    @property
    def definition(self) -> dict:
        """Return tool definition: {name, description, parameters (JSON Schema)}."""
        ...

    async def execute(self, params: dict) -> dict:
        """Run the tool with given params. Returns {result: str} or {error: str}."""
        ...


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.definition["name"]] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [t.definition for t in self._tools.values()]

    def list_names(self) -> list[str]:
        return list(self._tools.keys())


def create_registry() -> ToolRegistry:
    """Create registry with all built-in tools."""
    from chat.tools.calculator import CalculatorTool
    from chat.tools.file_io import FileIOTool
    from chat.tools.python_exec import PythonExecTool
    from chat.tools.url_fetch import URLFetchTool
    from chat.tools.weather import WeatherTool
    from chat.tools.web_search import WebSearchTool

    registry = ToolRegistry()
    registry.register(WebSearchTool())
    registry.register(URLFetchTool())
    registry.register(CalculatorTool())
    registry.register(FileIOTool())
    registry.register(WeatherTool())
    registry.register(PythonExecTool())
    return registry
