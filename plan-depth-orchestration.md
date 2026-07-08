# Plan: Depth — multi-app, multi-step orchestration with one combined answer

## Goal

Prove the real orchestrator: a task that runs **more than one step**, **passes results between
steps**, and returns **ONE grounded answer in your voice** — not a list of per-app outputs.

## Why

So far we've only proven single-app, single-step (arXiv). "Depth" — chaining steps and combining
their results — is what makes this an orchestrator rather than a single-app caller.

## Target demo

`find a recent paper on mixture-of-experts and explain its key takeaways`
- **t1:** arXiv search → papers
- **t2 (needs t1):** arXiv analyze → takeaways for the paper found in t1
- **→ one combined, grounded answer** (not two separate blobs)

This uses only apps that already work today (arXiv), so it proves the *orchestration*, not new app
plumbing.

## Tasks — core (this IS "depth"; each: code → `make verify` → commit)

1. **Data flow between steps.** A downstream subtask can use an upstream result. The
   operation+argument selector is given the outputs of the subtasks it depends on, so step 2 can
   use (e.g.) the arXiv id that step 1 returned. *(selector + executor)*
2. **Synthesis + your voice (AC-4).** A final step combines all step results into ONE answer,
   grounded strictly in those results (with sources), written in your voice; if a single app fully
   answered, pass its answer through verbatim. Shown as an "Answer" section on top; per-step detail
   stays below (or under `--verbose`). *(new `synthesis.py` + prompt; render + cli)*
3. **Prove it.** A hermetic replay e2e for a 2-step dependent task, plus a live run of the demo
   above. *(tests + docs)*

## Tasks — enhancements (after the core works)

4. **Web-search fallback execution.** Steps with no suitable app get a real web answer (with
   citations) instead of "no relevant results / skipped".
5. **Run budget + partial results.** An overall wall-clock cap for multi-step runs: on breach,
   cancel the rest and synthesize a partial answer — never hang.
6. **Parallel steps run in parallel.** Independent steps in the same wave run concurrently
   (faster), still bounded by a concurrency cap.

## How you'll test it

```bash
PYTHONPATH=src python3 -m orchestrator --execute \
  "find a recent paper on mixture-of-experts and explain its key takeaways"
```
Expect: a 2-step plan, both steps call arXiv (step 2 uses step 1's paper), and ONE combined answer
grounded in that paper. Plus `make verify` (hermetic, no key).

## Deferred (later slices)

The tricky apps — coding-playground (WebSocket), blogs-playground / research-assistant (async
poll), stats-teacher (streaming) — and switching on the remaining simple apps for breadth.

## Note

Tasks 1 and 2 are the real "depth". 4–6 harden and broaden it. I'll build them one small task at a
time, sealing each, and check with you between tasks.
