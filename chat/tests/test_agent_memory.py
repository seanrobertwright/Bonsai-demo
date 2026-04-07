"""Integration test: agent loop emits remember tool call and DB is updated."""

import os
import tempfile
import pytest
from unittest.mock import patch

from chat.db import ChatDB
from chat.tools import create_registry
from chat.agent import AgentLoop


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    d = ChatDB(path)
    yield d
    d.close()
    os.unlink(path)


@pytest.fixture
def agent(db):
    return AgentLoop(create_registry(db=db))


@pytest.mark.asyncio
async def test_agent_remember_tool_writes_to_db(agent, db):
    # Fake two-round stream: first round emits a remember tool call,
    # second round emits a normal reply.
    rounds = [
        '{"name": "remember", "arguments": {"content": "User lives in Boston"}}',
        "Got it - I'll remember that.",
    ]
    call_count = {"n": 0}

    async def fake_stream(self, messages):
        idx = call_count["n"]
        call_count["n"] += 1
        for ch in rounds[idx]:
            yield ch

    with patch.object(AgentLoop, "_stream_completion", new=fake_stream):
        result = await agent.run(
            messages=[{"role": "user", "content": "I live in Boston."}],
        )

    mems = db.list_memories()
    assert len(mems) == 1
    assert mems[0]["content"] == "User lives in Boston"
    assert mems[0]["source"] == "model"
    assert result["content"] == "Got it - I'll remember that."


@pytest.mark.asyncio
async def test_agent_remember_duplicate_does_not_insert_twice(agent, db):
    # Seed an existing memory.
    db.add_memory("User lives in Boston", source="user")

    rounds = [
        '{"name": "remember", "arguments": {"content": "User lives in Boston"}}',
        "Noted.",
    ]
    call_count = {"n": 0}

    async def fake_stream(self, messages):
        idx = call_count["n"]
        call_count["n"] += 1
        for ch in rounds[idx]:
            yield ch

    with patch.object(AgentLoop, "_stream_completion", new=fake_stream):
        await agent.run(messages=[{"role": "user", "content": "Boston."}])

    assert len(db.list_memories()) == 1
