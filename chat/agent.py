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
            "You are Bonsai, a helpful AI assistant running locally on the user's machine. "
            "You are PRIMARILY a conversational assistant. Most of the time you should just "
            "reply directly using your own knowledge — tools are the exception, not the rule.\n\n"

            "## DEFAULT BEHAVIOR: Respond directly (no tools)\n"
            "For the vast majority of messages, DO NOT call any tool. Just reply conversationally. "
            "This includes:\n"
            "- Greetings and small talk: 'hello', 'hi', 'how are you', 'thanks', 'bye'\n"
            "- Questions you already know the answer to: definitions, explanations, concepts, "
            "history, science, programming help, how-to questions, famous people, places, events "
            "from before your training cutoff\n"
            "- Opinions, creative writing, jokes, roleplay, brainstorming\n"
            "- Simple arithmetic you can do in your head (e.g., 2+2, 15% of 200)\n"
            "- Clarifications, follow-ups, or anything the user is clearly just chatting about\n"
            "- Meta questions about yourself ('who are you?', 'what can you do?')\n\n"
            "When in doubt, DO NOT use a tool. Just answer from your knowledge.\n\n"

            "## WHEN TO USE TOOLS (the exception)\n"
            "Only call a tool when you genuinely cannot answer without real-world data the model "
            "doesn't have. Available tools:\n\n"
            + "\n".join(tool_docs)
            + "\n\n"

            "Specific tool rules:\n"
            "- **web_search**: ONLY for current/recent information the model can't know — today's "
            "news, recent sports results, current stock prices, latest software versions, "
            "real-time events. NEVER for greetings, general knowledge, concepts, or established "
            "facts. If the user asks 'what is X?' about a well-known concept, answer from your "
            "own knowledge — do NOT search.\n"
            "- **url_fetch**: ONLY when the user explicitly provides a URL and asks you to read "
            "or fetch it. Never guess URLs or fabricate them.\n"
            "- **calculator**: ONLY for math you genuinely cannot do reliably in your head — "
            "complex expressions, calculus, symbolic algebra, unit conversions. For simple "
            "arithmetic (anything up to basic multi-digit multiplication), just compute it yourself.\n"
            "- **weather**: ONLY when the user asks about current weather or a forecast for a "
            "specific location.\n"
            "- **file_io**: ONLY when the user explicitly asks to read, write, or list files.\n"
            "- **python_exec**: ONLY when the user explicitly asks you to run or execute code.\n"
            "- **remember**: When the user states a durable fact about themselves "
            "('I live in X', 'I'm a Y', 'my name is Z', 'I prefer X over Y', 'I work as X', "
            "'my dog is named W') that isn't already in 'Facts you already know about the user', "
            "call remember to save it BEFORE you reply. Save stable facts only: location, job, "
            "family, pets, long-running projects, explicit behavior preferences. NEVER for "
            "trivia, passing remarks, or facts about topics the user asked about. Save at most "
            "one fact per turn.\n\n"

            "## Tool call format\n"
            "To call a tool, output ONLY a JSON object with 'name' and 'arguments' fields and "
            "nothing else — no prose before or after:\n"
            '{"name": "web_search", "arguments": {"query": "your search query"}}\n\n'
            "After you receive the tool result, write a helpful reply. Never mix a tool call "
            "and a conversational response in the same message.\n\n"

            "## Examples\n"
            "User: hello\n"
            "You: Hello! How can I help you today?\n\n"
            "User: what is recursion?\n"
            "You: Recursion is a programming technique where a function calls itself to solve "
            "a smaller instance of the same problem. [...continues from your knowledge...]\n\n"
            "User: thanks!\n"
            "You: You're welcome! Let me know if you need anything else.\n\n"
            "User: what's 12 * 8?\n"
            "You: 12 × 8 = 96.\n\n"
            "User: who wrote Hamlet?\n"
            "You: William Shakespeare wrote Hamlet, around 1600.\n\n"
            "User: what's the weather in Paris?\n"
            'You: {"name": "weather", "arguments": {"location": "Paris"}}\n\n'
            "User: who won the Super Bowl last week?\n"
            'You: {"name": "web_search", "arguments": {"query": "Super Bowl winner last week"}}\n\n'
            "User: I just moved to Seattle last month.\n"
            'You: {"name": "remember", "arguments": {"content": "User lives in Seattle"}}\n\n'
            "User: run this python: print(2**10)\n"
            'You: {"name": "python_exec", "arguments": {"code": "print(2**10)"}}'
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
        cancel_event=None,
        custom_context="",
    ) -> dict:
        """Run the agent loop. Returns {content, tool_calls}.

        Callbacks:
          on_token(token: str) — called for each streamed token
          on_tool_start(name: str, args: dict) — called when tool execution starts
          on_tool_end(name: str, result: dict) — called when tool execution ends
        """
        system_prompt = self._build_system_prompt()
        if custom_context:
            system_prompt = custom_context + "\n\n" + system_prompt
        all_tool_calls = []

        # Build messages with system prompt
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        for round_num in range(MAX_TOOL_ROUNDS + 1):
            # Collect full response first (don't stream yet — need to check for tool calls)
            full_response = ""
            async for token in self._stream_completion(full_messages):
                if cancel_event and cancel_event.is_set():
                    break
                full_response += token

            if cancel_event and cancel_event.is_set():
                # Stream what we have so far and return
                if on_token and full_response:
                    display_text = self._strip_tool_json(full_response)
                    for char in display_text:
                        await on_token(char)
                return {"content": full_response, "tool_calls": all_tool_calls}

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
        """Remove JSON tool call blocks from text, converting code calls to markdown."""
        import re

        def _replace_tool_json(json_str: str) -> str:
            """Convert a tool call JSON string to markdown (code block for python_exec, empty otherwise)."""
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, dict) and "name" in parsed:
                    if parsed["name"] == "python_exec" and "code" in parsed.get("arguments", {}):
                        code = parsed["arguments"]["code"]
                        return f"\n```python\n{code}\n```\n"
                    return ""
            except (json.JSONDecodeError, TypeError):
                pass
            return json_str

        # Handle ```json ... ``` blocks containing tool calls
        def replace_fenced(m):
            content = m.group(1).strip()
            if '"name"' in content and '"arguments"' in content:
                return _replace_tool_json(content)
            return m.group(0)
        text = re.sub(r'```(?:json)?\s*\n?(.*?)\n?```', replace_fenced, text, flags=re.DOTALL)

        # Handle bare JSON tool calls using bracket-counting
        from chat.tool_parser import _find_bare_json_objects
        for obj_str in _find_bare_json_objects(text):
            replacement = _replace_tool_json(obj_str)
            text = text.replace(obj_str, replacement, 1)

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
