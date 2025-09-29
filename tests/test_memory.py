from jox.orchestrator import memory

def test_entries_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    memory.add_entry("Topic", "Desc")
    e = memory.load_entries()
    assert len(e) == 1
