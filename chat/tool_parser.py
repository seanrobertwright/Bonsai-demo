"""Hybrid tool call parser — extracts tool calls from model output.

Strategy:
1. Try to find JSON tool call objects (bare or in ```json blocks)
2. Fall back to intent/pattern matching on natural language
"""

import json
import re


def parse_tool_calls(text: str, available_tools: list[str]) -> list[dict]:
    """Parse model output for tool calls. Returns list of {name, arguments}."""
    # Phase 1: Try JSON extraction
    calls = _extract_json_calls(text, available_tools)
    if calls:
        return calls

    # Phase 2: Fallback intent matching
    return _extract_intent_calls(text, available_tools)


def _extract_json_calls(text: str, available_tools: list[str]) -> list[dict]:
    """Extract JSON tool call objects from text."""
    calls = []

    # Find JSON in ```json blocks
    json_blocks = re.findall(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)

    # Also try to find bare JSON objects
    bare_json = re.findall(r'\{[^{}]*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{[^}]*\}[^}]*\}', text)

    # Deduplicate: if we found json blocks, don't also search for bare JSON
    # (bare regex often re-matches content inside the blocks)
    candidates = json_blocks if json_blocks else bare_json

    for candidate in candidates:
        candidate = candidate.strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "name" in parsed and parsed["name"] in available_tools:
                calls.append({
                    "name": parsed["name"],
                    "arguments": parsed.get("arguments", {}),
                })
        except json.JSONDecodeError:
            continue

    return calls


def _extract_intent_calls(text: str, available_tools: list[str]) -> list[dict]:
    """Fall back to pattern matching for tool intent."""
    calls = []
    text_lower = text.lower()

    # Web search patterns
    if "web_search" in available_tools:
        patterns = [
            r'(?:let me |i\'ll |i will )?search(?:ing)? (?:for |the web for |the internet for )(?:"|\')?(.+?)(?:"|\')?(?:\.|$|for you)',
            r'(?:let me |i\'ll )look (?:up|into) (?:"|\')?(.+?)(?:"|\')?(?:\.|$)',
            r'search(?:ing)? for ["\'"]?(.+?)["\'"]?(?:\.|$)',
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                query = m.group(1).strip().rstrip(".")
                if len(query) > 3:
                    calls.append({"name": "web_search", "arguments": {"query": query}})
                    break

    # Weather patterns
    if "weather" in available_tools and not calls:
        patterns = [
            r'(?:check|get|look up) (?:the )?weather (?:in|for|at) (.+?)(?:\.|$)',
            r'weather (?:in|for|at) (.+?)(?:\.|$)',
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                location = m.group(1).strip().rstrip(".")
                if len(location) > 1:
                    calls.append({"name": "weather", "arguments": {"location": location}})
                    break

    # URL fetch patterns
    if "url_fetch" in available_tools and not calls:
        url_match = re.search(r'(https?://[^\s,)]+)', text)
        if url_match and any(kw in text_lower for kw in ["fetch", "read", "open", "visit", "check", "page at", "page from"]):
            calls.append({"name": "url_fetch", "arguments": {"url": url_match.group(1).rstrip(".")}})

    # Calculator patterns
    if "calculator" in available_tools and not calls:
        if any(kw in text_lower for kw in ["calculate", "compute", "evaluate", "math", "% of", "what is"]):
            patterns = [
                r'(?:calculate|compute|evaluate)\s*(?:that\s*)?:?\s*(.+?)(?:\.|$)',
                r'(\d+%?\s*(?:of|times|plus|minus|divided by)\s*\d+)',
            ]
            for pattern in patterns:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    expr = m.group(1).strip().rstrip(".")
                    if len(expr) > 1:
                        calls.append({"name": "calculator", "arguments": {"expression": expr}})
                        break

    return calls
