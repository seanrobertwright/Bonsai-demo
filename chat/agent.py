"""Agent loop — orchestrates model calls, tool parsing, and execution."""

import json
from typing import AsyncGenerator

import httpx

from chat.config import MAX_TOOL_ROUNDS, LLAMA_BASE_URL
from chat.tool_parser import parse_tool_calls
from chat.tools import ToolRegistry


class AgentLoop:
    def __init__(self, registry: ToolRegistry, llama_base_url: str | None = None):
        self.registry = registry
        self.llama_url = llama_base_url or LLAMA_BASE_URL

    def _build_system_prompt(self) -> str:
        """Build system prompt with tool definitions."""
        tools = self.registry.list_tools()
        tool_docs = []
        for t in tools:
            tool_docs.append(
                f"- **{t['name']}**: {t['description']}\n"
                f"  Parameters: {json.dumps(t['parameters'])}"
            )

        return (
            "You are Bonsai, a helpful AI assistant running locally. "
            "You have access to tools and MUST use them when the user's question requires "
            "current information, calculations, file operations, or code execution.\n\n"
            "IMPORTANT RULES:\n"
            "- If the user asks about current events, versions, weather, or anything time-sensitive, "
            "you MUST use the web_search tool. Do NOT say you don't have access to real-time information.\n"
            "- If the user asks you to fetch a URL, use the url_fetch tool.\n"
            "- If the user asks for math or calculations, use the calculator tool.\n"
            "- If the user asks about weather, use the weather tool.\n"
            "- If the user asks to read/write files, use the file_io tool.\n"
            "- If the user asks to run code, use the python_exec tool.\n\n"
            "Available tools:\n\n"
            + "\n".join(tool_docs)
            + "\n\n"
            "To use a tool, output ONLY a JSON object (no other text before it) with 'name' and 'arguments' fields:\n"
            '{"name": "web_search", "arguments": {"query": "your search query"}}\n\n'
            "After you receive the tool results, write a helpful response using that information. "
            "Do NOT output the JSON tool call and a response in the same message — "
            "output ONLY the JSON tool call, wait for results, then respond."
        )

    def _format_tool_result(self, tool_name: str, result: dict) -> str:
        """Format a tool result for feeding back to the model."""
        return f"[Tool Result: {tool_name}]\n{json.dumps(result, indent=2)}"

    async def run(
        self,
        messages: list[dict],
        on_token=None,
        on_tool_start=None,
        on_tool_end=None,
    ) -> dict:
        """Run the agent loop. Returns {content, tool_calls}.

        Callbacks:
          on_token(token: str) — called for each streamed token
          on_tool_start(name: str, args: dict) — called when tool execution starts
          on_tool_end(name: str, result: dict) — called when tool execution ends
        """
        system_prompt = self._build_system_prompt()
        all_tool_calls = []

        # Build messages with system prompt
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        for round_num in range(MAX_TOOL_ROUNDS + 1):
            # Collect full response first (don't stream yet — need to check for tool calls)
            full_response = ""
            async for token in self._stream_completion(full_messages):
                full_response += token

            # Parse for tool calls
            tool_calls = parse_tool_calls(full_response, self.registry.list_names())

            if not tool_calls or round_num == MAX_TOOL_ROUNDS:
                # No tools to call (or hit max rounds) — stream response to user
                if on_token:
                    # Strip any leftover JSON tool call attempts from the response
                    display_text = self._strip_tool_json(full_response)
                    for char in display_text:
                        await on_token(char)
                return {"content": full_response, "tool_calls": all_tool_calls}

            # Execute tools
            full_messages.append({"role": "assistant", "content": full_response})

            for tc in tool_calls:
                tool = self.registry.get(tc["name"])
                if not tool:
                    continue

                if on_tool_start:
                    await on_tool_start(tc["name"], tc["arguments"])

                result = await tool.execute(tc["arguments"])

                if on_tool_end:
                    await on_tool_end(tc["name"], result)

                all_tool_calls.append({"name": tc["name"], "arguments": tc["arguments"], "result": result})
                full_messages.append({
                    "role": "user",
                    "content": self._format_tool_result(tc["name"], result),
                })

    @staticmethod
    def _strip_tool_json(text: str) -> str:
        """Remove JSON tool call blocks from text meant for display."""
        import re
        # Remove ```json ... ``` blocks containing tool calls
        text = re.sub(r'```(?:json)?\s*\n?\{[^}]*"name"\s*:.*?\}.*?```', '', text, flags=re.DOTALL)
        # Remove bare JSON tool calls
        text = re.sub(r'\{[^{}]*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{[^}]*\}[^}]*\}', '', text)
        return text.strip()

    async def _stream_completion(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Stream tokens from llama-server's /v1/chat/completions endpoint."""
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.llama_url}/v1/chat/completions",
                json={
                    "messages": messages,
                    "stream": True,
                    "temperature": 0.5,
                    "top_p": 0.85,
                    "top_k": 20,
                },
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
