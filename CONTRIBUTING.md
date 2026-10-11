# Contributing

See [local development](README.md#local-development) for helper tests and roster lint.

## Smoke protocol

Run both build and light-build on Claude Code and Codex with the candidate's skill
files and bundled resources. In Claude, load the candidate with
`claude --plugin-dir <absolute-checkout>` and invoke `/autopilot:build` or
`/autopilot:light-build`; in Codex, explicitly invoke the candidate's absolute
SKILL.md path with the same requirement.

Exercise production and a fixture whose full checks expose a failure outside
S5's targeted checks: require an S6 FAIL, one committed fix, fresh re-review and
full verification of the fixed SHA. Interrupt a run after S5, resume from its
recorded state, and confirm the final head tree equals the tree with all-PASS
review evidence. Record host, exact invocation/check commands, exit codes,
test counts, reviewer verdicts and final `autopilot-result`; record an unavailable
scenario with its actual reason rather than a PASS.
