import app.core.memory as mem


def test_memory_block_merges_profile_and_facts(monkeypatch):
    monkeypatch.setattr(
        mem,
        "get_profile",
        lambda uid: {"full_name": "Ann", "age": 30, "city": "NYC",
                     "gender": None, "phone": "", "bio": None},
    )
    monkeypatch.setattr(mem, "list_memories", lambda uid: [{"content": "likes blue"}])
    block = mem.memory_block("u")
    assert "Name: Ann" in block
    assert "Age: 30" in block
    assert "City: NYC" in block
    assert "likes blue" in block  # 'remember' facts still included
    assert "Gender" not in block  # empty/None fields skipped
    assert "Phone" not in block


def test_memory_block_profile_only(monkeypatch):
    monkeypatch.setattr(mem, "get_profile", lambda uid: {"full_name": "Bob"})
    monkeypatch.setattr(mem, "list_memories", lambda uid: [])
    assert "Name: Bob" in mem.memory_block("u")


def test_memory_block_empty_when_nothing(monkeypatch):
    monkeypatch.setattr(mem, "get_profile", lambda uid: {})
    monkeypatch.setattr(mem, "list_memories", lambda uid: [])
    assert mem.memory_block("u") == ""
