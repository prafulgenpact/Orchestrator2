# Recorded model responses (record/replay)

LLM calls are the nondeterminism in your system. For repeatable E2E:

1. Wrap your model client behind one module (you should anyway).
2. RECORD mode (dev machine): real API calls; save each response to this dir
   keyed by a hash of the request (model + messages + tools).
3. REPLAY mode (CI, default for e2e): the wrapper loads responses from here —
   deterministic, fast, free. Missing key = test failure telling you to re-record.
4. Keep ONE live scenario out of CI (nightly / pre-release) to catch model drift.

Env convention the test runner already passes through:
  AGENT_LLM_MODE=replay|record|live   (implement in your client wrapper)

Commit recordings like any other fixture. Re-record deliberately when prompts
or models change — the diff shows you exactly how behavior moved.
