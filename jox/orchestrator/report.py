from __future__ import annotations
from typing import List, Dict, Any
from pathlib import Path
from jox.utils.files import write_json
from jox.utils.dates import today_compact

def write_session_report(dest_dir: str | Path, payload: Dict[str, Any]) -> str:
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    name = f"session_report_{today_compact()}.json"
    out = Path(dest_dir) / name
    write_json(out, payload)
    return str(out)
