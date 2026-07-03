# Scenarios

One JSON file = one scripted end-to-end run of your agent. Grow this directory
task by task: every acceptance criterion should map to at least one scenario.

`example.json.disabled` is a template — copy, edit, rename to `*.json` to arm it.

Fields:
  args            appended to agent_cmd (from e2e.config.json)
  stdin           piped to the process
  env             extra environment for this scenario
  timeout_s       default 300
  expect.exit_code / stdout_contains / stdout_regex / files_exist / json_stdout_keys

The runner executes your agent in an empty temp dir (AGENT_WORKDIR / cwd), so
`files_exist` checks the artifacts your agent claims to produce. Evidence, not
assertions — same contract as everything else here.
