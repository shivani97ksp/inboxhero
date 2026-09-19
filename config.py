# inboxHero -- Shivani Singh, evernorth-aai-1192468
"""Runtime configuration, read from the environment only.

Nothing about the model provider is hardcoded. Copy .env.example to .env and
edit it; .env is never committed.

    INBOXHERO_PROVIDER   ollama | gemini | offline   (default: ollama)
    OLLAMA_BASE_URL      default http://localhost:11434
    OLLAMA_MODEL         default qwen2.5:7b
    GOOGLE_API_KEY       required when provider=gemini
    GEMINI_MODEL         default gemini-1.5-flash
    INBOXHERO_RPM_DELAY  seconds to wait between model calls (default 4.0)
    INBOXHERO_BATCH      messages per classification call (default 8)
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    """Read .env into the environment. Hand-rolled to keep the project
    dependency-free; real environment variables always win."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if "#" in value:
            value = value.split("#", 1)[0].rstrip()
        os.environ.setdefault(key.strip(), value.strip("'\""))


_load_dotenv()

INBOX_PATH = Path(os.getenv("INBOXHERO_INBOX", ROOT / "data" / "inbox.json"))
OUTBOX_DIR = ROOT / "outbox"
STATE_DIR = ROOT / "state"
CACHE_DIR = ROOT / ".cache"

TRACE_PATH = ROOT / "trace.jsonl"
GATE_LOG_PATH = STATE_DIR / "gate_log.jsonl"
PREFS_PATH = STATE_DIR / "prefs.json"
DECISIONS_PATH = STATE_DIR / "decisions.json"
DASHBOARD_JSON = ROOT / "dashboard.json"
DASHBOARD_HTML = ROOT / "dashboard.html"
RUN_SUMMARY = ROOT / "run_summary.txt"

OWNER = os.getenv("INBOXHERO_OWNER", "sam@paperjet.io")
OWNER_DOMAIN = OWNER.split("@")[-1]

PROVIDER = os.getenv("INBOXHERO_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Free tiers are typically ~15 requests/minute with a daily cap, so calls are
# spaced out, batched, and retried on HTTP 429 (see llm.py).
RPM_DELAY = float(os.getenv("INBOXHERO_RPM_DELAY", "4.0"))
BATCH_SIZE = int(os.getenv("INBOXHERO_BATCH", "8"))
MAX_RETRIES = int(os.getenv("INBOXHERO_MAX_RETRIES", "4"))

# The five dispositions. Exactly one is assigned to every message.
DISPOSITIONS = ("reply", "archive", "defer", "delegate", "escalate")

# Actions that cannot be taken back in this design, and so must pass the gate.
IRREVERSIBLE_ACTIONS = ("send", "delete")
REVERSIBLE_ACTIONS = ("draft", "label", "archive", "defer", "flag")


def model_label() -> str:
    if PROVIDER == "gemini":
        return f"gemini:{GEMINI_MODEL}"
    if PROVIDER == "ollama":
        return f"ollama:{OLLAMA_MODEL}"
    return "offline-heuristic"


def ensure_dirs() -> None:
    for d in (OUTBOX_DIR, STATE_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
