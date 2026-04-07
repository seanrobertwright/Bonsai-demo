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

    # Also try to find bare JSON objects using bracket-counting
    bare_json = _find_bare_json_objects(text) if not json_blocks else []

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


def _find_bare_json_objects(text: str) -> list[str]:
    """Extract JSON objects from text using bracket-counting (handles nested braces in strings)."""
    results = []
    i = 0
    while i < len(text):
        if text[i] == '{':
            # Try to extract a balanced JSON object
            depth = 0
            in_string = False
            escape_next = False
            start = i
            for j in range(i, len(text)):
                ch = text[j]
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = text[start:j + 1]
                        # Quick check: does it look like a tool call?
                        if '"name"' in candidate and '"arguments"' in candidate:
                            results.append(candidate)
                        i = j + 1
                        break
            else:
                i += 1
        else:
            i += 1
    return results


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
