# inboxHero

Repository: https://github.com/shivani97ksp/inboxhero

An email assistant for a 100-message mock inbox: it dispositions every message,
drafts replies that cite the messages they came from, learns preferences that survive
a restart, refuses instructions embedded in mail, gates anything irreversible behind a
human, and renders a three-pane dashboard.

Pure Python, standard library only. No framework, no dependencies to install.

- `CAPABILITIES.md`: short human-readable capability and evidence index
- `capabilities.json`: machine-readable manifest with one command per capability

## Architecture and decisions

This is a plain Python pipeline with no agent framework or external dependencies. The
main components are `guard.py`, `rules.py`, `triage.py`, `retrieve.py`, `draft.py`,
`gate.py`, `commitments.py`, and `dashboard.py`, connected in that order by `demo.py`.
The system uses the disposition vocabulary `reply`, `archive`, `defer`, `delegate`,
and `escalate`; the deterministic rules handle routine messages before the model path.

`send` and `delete` are irreversible because they affect communication or mailbox
state, so both require a dry-run preview and explicit per-message approval through
`gate.py`. Drafts, labels, flags, archives, and deferrals are reversible and can run
without approval. The default `both` gate mode writes the preview and still blocks the
action until the owner approves it.

Retrieval uses a thread-walk first because `thread_id` gives the inbox a precise local
structure. `retrieve.py` only uses concrete, overlapping facts from the thread, and
uses keyword search across threads as a fallback when the thread has no answer. For
example, R2 handles `m008` using facts from `m001` and `m003`, while `m012` receives a
clarifying question because the inbox does not contain enough information.

## Final Report

### 1. What did you refuse to automate?

The system refuses to send or delete anything without a named human approval. In R3,
the proposed reply for `m008` and the delete request for phishing message `m045` are
written to the dry-run area but neither action happens automatically. It also refuses
the governance change in `m039`, which asks for autonomous operation and no approval.
I drew the line there because a wrong archive can be corrected, while a wrong external
message or deletion cannot be reliably taken back.

### 2. Where does untrusted text enter the system?

Every field in `data/inbox.json` is untrusted, including `from`, `subject`, `body`,
and quoted forwarded text. The architecture keeps that text inside the store and
passes it to the model only as data for classification; `guard.py` can escalate it,
`retrieve.py` can cite it, and `gate.py` controls any irreversible effect. An attacker
would have to defeat the guard, the restricted disposition output, the citation-only
drafting path, and the approval gate before the message could cause an external action.
Message `m047` demonstrates that an instruction hidden inside a forwarded message is
still detected and left in the inbox.

### 3. Who is accountable when it sends the wrong thing?

The human who explicitly approved the send is accountable for an approved action, and
the system is accountable if it bypasses the gate. `gate.py` records the proposal,
recipients, rendered body, approver, outcome, and artifact in `state/gate_log.jsonl`
before the action runs. `trace.jsonl` records the retrieval and cited message IDs, so
a wrong fact in a reply can be traced back to the messages read by `draft.py`. This
makes it possible to distinguish an approved but poorly worded message from an
unauthorized send.

### 4. What machinery plays the framework roles?

The modules `triage.py`, `retrieve.py`, `draft.py`, `guard.py`, and `commitments.py`
play the roles of focused Agents, while each `cap_*` function in `demo.py` is a Task
with a command, observable result, and evidence entry in `capabilities.json`. The
`--all` order in `demo.py` is the Crew orchestration, and `rules.py` plus `guard.py`
are the router that chooses the cheap rule path or the model path. A framework would
have provided a planner and an agent-to-agent protocol, but this fixed pipeline does
not need open-ended planning. Using a framework here would add indirection around the
gate and make the finite set of callers for `send` and `delete` harder to inspect.

## Run it

```bash
# no model, no key, no network -- everything still works
INBOXHERO_PROVIDER=offline python demo.py --all

# one capability at a time
python demo.py --cap R1
python demo.py --cap R2 --msg m008
python demo.py --cap R3
python demo.py --cap R3 --gate dry-run
python demo.py --cap R3 --gate both --approve m008     # approve one send
python demo.py --cap R3 --interactive                  # be asked y/n
python demo.py --cap R4
python demo.py --show-prefs                            # fresh process, state read off disk
python demo.py --cap R5
python demo.py --cap R6                                # writes dashboard.html
python demo.py --cap X1
python demo.py --cap X2
python demo.py --cap X3
python demo.py --cap X4
python demo.py --cap X5 --msg m024

python demo.py --reset                                 # clear state/, trace.jsonl, outbox/
```

## Choosing a model

Copy `.env.example` to `.env` (never commit `.env`) and set `INBOXHERO_PROVIDER`:

| value | what it uses | when |
|-------|--------------|------|
| `ollama` | `OLLAMA_MODEL` at `OLLAMA_BASE_URL` | local development, no quota |
| `gemini` | `GEMINI_MODEL` with `GOOGLE_API_KEY` | the final run |
| `offline` | deterministic heuristics, no model | verification with no key |

Local model:

```bash
ollama serve
ollama pull llama3.1:8b
INBOXHERO_PROVIDER=ollama python demo.py --all
```

Free-tier pacing is configuration, not code: `INBOXHERO_RPM_DELAY` (seconds between
calls), `INBOXHERO_BATCH_SIZE` (messages per classification call),
`INBOXHERO_MAX_RETRIES` (retries on HTTP 429/5xx, exponential backoff). Responses are
cached in `.cache/` by prompt hash, so re-running a capability costs nothing. If the
provider is unreachable or keeps failing, the run degrades to the offline heuristics
instead of crashing.

## Layout

```
demo.py            one CLI entry point; one function per capability
config.py          env-driven configuration and paths (reads .env if present)
store.py           loads inbox.json, tracks which messages were actually read
guard.py           the untrusted-data boundary: injection and phishing detection
rules.py           deterministic dispositions, before any model call
llm.py             ollama / gemini / offline adapter, batching, backoff, cache
triage.py          R1: exactly one disposition per message
retrieve.py        thread-walk retrieval, keyword fallback
draft.py           grounded drafting; asks a question when grounding is missing
gate.py            dry-run + per-message approval for irreversible actions
actions.py         the effects themselves (outbox/, tombstones, labels)
prefs.py           persistent preferences; refuses governance changes
commitments.py     dated commitments, multi-message derivation, clashes
dashboard.py       the three panes, as JSON and HTML

data/inbox.json    input
outbox/            "sent" mail and drafts; outbox/_dryrun/ for previews
state/             prefs.json, decisions.json, gate_log.jsonl, deleted.json
trace.jsonl        every step of every run, tagged with the capability id
dashboard.json     the three panes
dashboard.html     the same, for a human
run_summary.txt    written by --all
```

## Evidence

`trace.jsonl` is the audit trail; each line carries a timestamp, a run id, the
capability id and the event. To see everything that happened to one message:

```bash
python demo.py --cap X5 --msg m024
```

## Malformed input

`data/inbox.json` is treated as untrusted input. Before any field is read,
`store.py` checks that the file is a list of objects, that each message has the
seven required fields, that all of them are text, and that ids are unique. A bad
file produces one structured report of every problem and exit code 2, never a
traceback:

```bash
echo '{"messages": []}' > /tmp/bad.json
INBOXHERO_INBOX=/tmp/bad.json python demo.py --cap R1   # exit 2, "invalid_inbox"
python demo.py --cap X5 --msg m999                      # exit 2, "unknown_message_id"
```

An id passed to `--msg` is checked against the inbox rather than silently
replaced by a default, so a typo cannot look like a successful run.

Nothing in this project sends real mail or contacts a mail server. "Sending" writes a
file under `outbox/`. "Deleting" writes a tombstone to `state/deleted.json`.
`data/inbox.json` is never modified, so flagged messages cannot be made to disappear.
