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
    # NOTE: we can't use f"fact {i}" here because the prefix-signature dedup
    # (Task 4) strips digits via the [a-z]+ tokenizer, which would collapse
    # every inserted row into a single "fact" signature and break this test.
    # The prefix signature also drops the trailing significant word, so the
    # distinguishing tag has to live at a NON-last position in the string.
    # We build 55 distinct 3-letter tags of the form "<c1><c2>x" so that:
    #   - every tag is purely alphabetic (survives the [a-z]+ tokenizer),
    #   - no tag is a stopword (two-letter stopwords like "is"/"an" would
    #     collapse to an empty-tag signature),
    #   - no tag ends in s/es/ing/e (so the crude stemmer leaves it alone),
    #   - the suffix "x" guarantees distinct signatures per index.
    # We then sandwich the tag between two constant words so the tag is
    # preserved when the last significant word is dropped.
    import string
    tags = [c1 + c2 + "x" for c1 in string.ascii_lowercase for c2 in string.ascii_lowercase][:55]
    for tag in tags:
        db.add_memory(f"{tag} factoid flavor")
    mems = db.list_memories()
    assert len(mems) == 50
    # Oldest should be evicted; newest kept. list_memories returns newest-first.
    assert mems[0]["content"] == f"{tags[54]} factoid flavor"
    # First 5 inserted should be gone; 6th should survive.
    contents = {m["content"] for m in mems}
    assert f"{tags[0]} factoid flavor" not in contents
    assert f"{tags[4]} factoid flavor" not in contents
    assert f"{tags[5]} factoid flavor" in contents


def test_prefix_dedup_replaces_stale_fact(db):
    first = db.add_memory("User lives in Boston", source="model")
    second = db.add_memory("User lives in Seattle", source="model")
    assert second["status"] == "updated"
    assert second["replaced_id"] == first["id"]
    assert second["replaced_content"] == "User lives in Boston"
    mems = db.list_memories()
    assert len(mems) == 1
    assert mems[0]["content"] == "User lives in Seattle"


def test_prefix_dedup_ignores_stopwords(db):
    # "I live in Boston" and "User lives in Boston" should collide
    # after dropping stopwords (I, user) and normalizing lives/live.
    # We only require: the 4-significant-word prefix signature matches.
    db.add_memory("I live in Boston", source="model")
    dup = db.add_memory("The user lives in Boston", source="model")
    # Exact-match won't catch this; prefix dedup should either UPDATE or mark DUPLICATE.
    # Since content differs, we expect UPDATE (replace first with second).
    assert dup["status"] in ("updated", "duplicate")
    assert len(db.list_memories()) == 1


def test_prefix_dedup_allows_unrelated_facts(db):
    db.add_memory("User lives in Boston", source="model")
    other = db.add_memory("User prefers terse answers", source="model")
    assert other["status"] == "saved"
    assert len(db.list_memories()) == 2
