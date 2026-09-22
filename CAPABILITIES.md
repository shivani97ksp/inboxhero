# CAPABILITIES.md: inboxHero

**Student:** Shivani Singh, evernorth-aai-1192468
**Repository:** https://github.com/shivani97ksp/inboxhero

One entry point for everything:

```
python demo.py --cap R1        # one capability
python demo.py --all           # all twelve, in dependency order
python demo.py --show-prefs    # read persisted state back in a fresh process
python demo.py --reset         # clear state/, trace.jsonl and outbox/
```

The commands in `capabilities.json` are the contract. They run on a clean copy with
no API key and no network when `INBOXHERO_PROVIDER=offline` is used. The assignment
architecture, design decisions, and Final Report are in `README.md`.

## Capabilities

| id | name | tier | one-line claim |
|----|------|------|----------------|
| R1 | Zero the inbox | B | all 100 messages get one disposition + reason, none left undecided |
| R2 | Grounded reply | B | drafts cite the ids they used, and ask instead of guessing |
| R3 | Gate the irreversible | C | no send/delete without a dry run and per-message approval |
| R4 | Persistent preference | C | inbox-stated rules survive a restart; governance rules are refused |
| R5 | Refuse embedded instructions | C | detects, refuses, keeps, and reports all four injections |
| R6 | Dashboard | C | three panes, commitments cited, one derived from two messages, clashes surfaced |
| X1 | Launch thread digest | B | the 9-message launch thread as owners, commitments and open asks |
| X2 | Follow-up tracking | B | the owner's unanswered sent mail, with a drafted chase |
| X3 | Rule-path batch report | A | which 60 messages never reached a model, and why |
| X4 | Meeting conflict resolver | C | proposes options for each clash and refuses to pick one |
| X5 | Why did you do that? | A | replays the trace for any single message id |

The exact command, observable outcome and evidence for each is in
`capabilities.json`: that file is what a marking script reads; this one is for a
human. They are kept in step.

### Evidence summary

- **Pending actions:** the 31 messages waiting on a human, each with the
  disposition, the reason, and whether a draft is already prepared.
- **Flagged:** the four prompt injections (`m017`, `m024`, `m039`, `m047`) with the
  signals that caught each, the three social-engineering attempts (`m021`, `m023`,
  `m045`), and the refused preference write.
- **Commitments:** 19 dated items, each citing its source ids. `board deck due
  2026-09-16` cites `[m040, m038]` and is marked `derived_from_multiple: true`: no
  single message says the 16th; `m040` asks for the deck two days before the board
  review and `m038` dates that review to the 18th. Clashes are lifted out of the
  list: `m010`'s Tuesday 15:00 call against the `m061` dental appointment at the same
  hour, and `m043`'s 9:00am proposal against the standing 11:00 rule from `m041`.

