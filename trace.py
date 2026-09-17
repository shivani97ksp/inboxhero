# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""Append-only run log. Every event carries the capability that produced it,
so `--cap X5` can replay the chain of decisions for any single message.
"""

import json
import time
from typing import Any, Dict, List

import config

_run_id = time.strftime("%Y%m%dT%H%M%S")


def run_id() -> str:
    return _run_id


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def reset() -> None:
    """Start a fresh trace file (used by --reset and by the full run)."""
    config.TRACE_PATH.write_text("", encoding="utf-8")


def emit(event: str, cap: str = "-", **fields: Any) -> Dict[str, Any]:
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "run": _run_id,
        "cap": cap,
        "event": event,
    }
    record.update(fields)
    with open(config.TRACE_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_all() -> List[Dict[str, Any]]:
    if not config.TRACE_PATH.exists():
        return []
    out = []
    for line in config.TRACE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def for_message(msg_id: str) -> List[Dict[str, Any]]:
    return [e for e in read_all() if e.get("msg_id") == msg_id]
