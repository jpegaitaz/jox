from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
from jox.utils.files import read_json, write_json
from jox.utils.dates import iso_now

ENTRIES_PATH = Path("data/entries.json")
OUTCOMES_PATH = Path("data/outcomes.json")

def load_entries() -> List[Dict[str, str]]:
    return read_json(ENTRIES_PATH, default=[])

def add_entry(topic: str, description: str) -> None:
    entries = load_entries()
    entries.append({"date": iso_now(), "topic": topic, "description": description})
    write_json(ENTRIES_PATH, entries)

def load_outcomes() -> List[Dict[str, Any]]:
    return read_json(OUTCOMES_PATH, default=[])

def add_outcome(session_id: str, topic: str, description: str, files: list[str], notes: str="") -> None:
    outcomes = load_outcomes()
    outcomes.append({
        "session_id": session_id,
        "date": iso_now(),
        "topic": topic,
        "description": description,
        "files": files,
        "notes": notes,
    })
    write_json(OUTCOMES_PATH, outcomes)

def knowledge_snapshot() -> str:
    # simple concatenation for few-shot context
    lines = []
    for e in load_entries()[-20:]:
        lines.append(f"[ENTRY] {e['date']} | {e['topic']}: {e['description']}")
    for o in load_outcomes()[-20:]:
        lines.append(f"[OUTCOME] {o['date']} | {o['topic']}: {o['description']}")
    return "\n".join(lines)
