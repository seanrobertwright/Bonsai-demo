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


def test_create_conversation(db):
    conv = db.create_conversation("Test Chat")
    assert conv["id"] is not None
    assert conv["title"] == "Test Chat"


def test_list_conversations(db):
    db.create_conversation("Chat 1")
    db.create_conversation("Chat 2")
    convs = db.list_conversations()
    assert len(convs) == 2
    assert convs[0]["title"] == "Chat 2"


def test_add_and_get_messages(db):
    conv = db.create_conversation("Test")
    db.add_message(conv["id"], "user", "Hello")
    db.add_message(conv["id"], "assistant", "Hi there!", tool_calls=[{"name": "web_search", "args": {"query": "test"}}])
    msgs = db.get_messages(conv["id"])
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["tool_calls"] == [{"name": "web_search", "args": {"query": "test"}}]


def test_delete_conversation(db):
    conv = db.create_conversation("To Delete")
    db.add_message(conv["id"], "user", "test")
    db.delete_conversation(conv["id"])
    assert db.list_conversations() == []
    assert db.get_messages(conv["id"]) == []


def test_update_title(db):
    conv = db.create_conversation("Old Title")
    db.update_title(conv["id"], "New Title")
    convs = db.list_conversations()
    assert convs[0]["title"] == "New Title"
