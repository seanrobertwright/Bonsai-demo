import os
import tempfile
import pytest
from chat.db import ChatDB


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = ChatDB(path)
    yield database
    database.close()
    os.unlink(path)


def test_memory_has_source_column_defaulting_to_user(db):
    mem = db.add_memory("User lives in Boston")
    assert mem["status"] == "saved"
    assert mem["source"] == "user"


def test_memory_add_with_explicit_source(db):
    mem = db.add_memory("User lives in Boston", source="model")
    assert mem["status"] == "saved"
    assert mem["source"] == "model"


def test_exact_duplicate_returns_duplicate_status(db):
    first = db.add_memory("User lives in Boston", source="model")
    assert first["status"] == "saved"
    second = db.add_memory("User lives in Boston", source="model")
    assert second["status"] == "duplicate"
    mems = db.list_memories()
    assert len(mems) == 1


def test_exact_dedup_is_case_and_whitespace_insensitive(db):
    db.add_memory("User lives in Boston", source="model")
    dup = db.add_memory("  USER lives in boston  ", source="model")
    assert dup["status"] == "duplicate"
    assert len(db.list_memories()) == 1


def test_memory_cap_at_50(db):
    for i in range(55):
        db.add_memory(f"fact {i}")
    mems = db.list_memories()
    assert len(mems) == 50
    # Oldest should be evicted; newest kept. list_memories returns newest-first.
    assert mems[0]["content"] == "fact 54"
    # "fact 0" through "fact 4" should be gone.
    contents = {m["content"] for m in mems}
    assert "fact 0" not in contents
    assert "fact 4" not in contents
    assert "fact 5" in contents
