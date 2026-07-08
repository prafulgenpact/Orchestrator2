# Plan: fix irrelevant results + show all papers

## Two problems (both confirmed)

1. **Only one result shown** — display bug. arXiv returns ~5 papers; the clean view truncates to
   ~500 chars so only the first shows. Not by design.
2. **Irrelevant results presented as answers** — accuracy gap. arXiv fuzzy-matches anything
   ("Virat Kohli" → "OD-VIRAT" object detection). We show whatever the app returns without
   checking it actually matches the task. "Grounded" currently means "from a real app", not
   "relevant".

## Fix 1 — list the results (clean display)

In the clean `--execute` output, when a result is a list, show a count + the top items
(title / id), not a truncated blob:
```
  [t1] ArXiv Paper Guide  — 5 results
       1. ExpertFlow: Efficient Mixture-of-Experts Inference …
       2. Not All Experts are Equal …
       … (2 more)
       source: …
```
`--verbose` still shows the full raw payload.

## Fix 2 — relevance guard (the accuracy fix)

After an app returns results, one small LLM check judges: **do these actually address the task?**
- **Relevant** → show them as today.
- **Not relevant** → do NOT show the garbage. Report:
  `no relevant results found — <one-line reason>` (e.g. "arXiv has no papers on this topic").

This directly enforces "never present useless/unrelated results." It costs one extra LLM call per
executed subtask.

## Deferred (next slice)

Actually *answering* out-of-domain questions (a cricketer, a politician) via a **web-search
fallback** — for now those correctly return "no relevant results" instead of misleading papers.

## Steps (each: code → make verify → commit)

1. `render.py`: list-aware clean output (count + top titles).
2. New `grounding.py`: `check_relevance(client, subtask, output, *, model) -> (relevant, reason)`.
3. `executor.py`: run the relevance check after a successful call; on "not relevant" mark the
   subtask `no_match` with the reason (suppress the raw output).
4. Tests for each (hermetic: FakeLLM + fixtures); `make verify` green.

## How you'll test it

```bash
# relevant topic -> a real list of papers:
PYTHONPATH=src python3 -m orchestrator --execute "find recent papers on mixture-of-experts"
# junk topic -> "no relevant results found", NOT garbage:
PYTHONPATH=src python3 -m orchestrator --execute "find papers on Virat Kohli"
```
