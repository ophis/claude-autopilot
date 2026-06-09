# Claude Autopilot — contributor notes

## Review roster (`agents/`)

When you **create or update an agent** in `agents/`, run the roster lint and fix any
failures before committing:

```
python3 scripts/lint-roster.py
```

It enforces acceptance criterion A3 for every reviewer: valid frontmatter
(`lens`/`phase`/`tier`/`applies_to` + `maxTurns`), a read-only `tools` allowlist
(`Read, Grep, Glob, Bash`), the inlined reviewer contract, and the strict verdict
block. A malformed reviewer would otherwise be silently mis-routed by the §8.6
selector (`scripts/select-panel.py`) or mis-run at dispatch — the lint makes that
fail loudly at authoring time. It is an authoring/CI check, **not** a step in the
`/autopilot:build` or `/autopilot:fix` pipeline.
