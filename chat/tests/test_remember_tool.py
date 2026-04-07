import os
import tempfile
import pytest
from chat.db import ChatDB
from chat.tools.remember import RememberTool


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    d = ChatDB(path)
    yield d
    d.close()
    os.unlink(path)


@pytest.fixture
def tool(db):
    return RememberTool(db)


def test_definition(tool):
    d = tool.definition
    assert d["name"] == "remember"
    assert "parameters" in d
    assert "content" in d["parameters"]["properties"]


@pytest.mark.asyncio
async def test_save_new_fact(tool, db):
    result = await tool.execute({"content": "User lives in Boston"})
    assert result["status"] == "saved"
    assert result["content"] == "User lives in Boston"
    assert "id" in result
    assert len(db.list_memories()) == 1


@pytest.mark.asyncio
async def test_save_duplicate(tool, db):
    await tool.execute({"content": "User lives in Boston"})
    result = await tool.execute({"content": "User lives in Boston"})
    assert result["status"] == "duplicate"
    assert len(db.list_memories()) == 1


@pytest.mark.asyncio
async def test_save_unrelated_facts_both_land(tool, db):
    # NOTE: prefix-dedup was dropped (see spec Implementation notes).
    # Two different factual statements should both land as separate rows.
    await tool.execute({"content": "User lives in Boston"})
    result = await tool.execute({"content": "User lives in Seattle"})
    assert result["status"] == "saved"  # not "updated" — prefix dedup is gone
    assert len(db.list_memories()) == 2


@pytest.mark.asyncio
async def test_reject_empty(tool):
    result = await tool.execute({"content": "   "})
    assert "error" in result


@pytest.mark.asyncio
async def test_reject_too_long(tool):
    result = await tool.execute({"content": "x" * 500})
    assert "error" in result


@pytest.mark.asyncio
async def test_stores_as_model_source(tool, db):
    # Verify the tool passes source='model' so manual and autonomous
    # memories are distinguishable downstream.
    await tool.execute({"content": "User lives in Boston"})
    mems = db.list_memories()
    assert mems[0]["source"] == "model"
