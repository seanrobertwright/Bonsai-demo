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
    assert mem["source"] == "user"


def test_memory_add_with_explicit_source(db):
    mem = db.add_memory("User lives in Boston", source="model")
    assert mem["source"] == "model"
