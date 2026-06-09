# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Claude Autopilot is a **Claude Code plugin** that packages an autonomous build/fix
pipeline driven by a committed roster of named review agents. The git repo **is both
the marketplace and the plugin** (`.claude-plugin/marketplace.json` points its single
plugin entry at `source: "./"`). The "product" is the plugin's prompts/agents/scripts,
not an application — there is nothing to compile or run as a server.

## Commands

```bash
# Validate manifests + agent frontmatter (use --strict in CI to fail on warnings)
claude plugin validate .

# Run all helper-script tests (stdlib unittest, no deps)
python3 tests/test_scripts.py
# Run a single test (the file calls unittest.main, so pass Class.method)
python3 tests/test_scripts.py SelectPanelTests.test_work_phase_glob_match

# Lint the review roster (acceptance criterion A3) — run after editing agents/
python3 scripts/lint-roster.py

# Local dev loop: load the plugin from the working copy, then hot-reload after edits
claude --plugin-dir .
/reload-plugins
```

There is no build step. `tests/test_scripts.py` exercises `scripts/select-panel.py`
and `scripts/autopilot-config.py` as CLIs via subprocess (they have hyphenated names,
so they're not importable — the CLI is the contract).

## Architecture (the big picture)

The two surfaces — `commands/build.md` and `commands/fix.md` — are **orchestrator
prompts**, not code. When invoked, the *main-session Claude becomes a thin
orchestrator*: it dispatches subagents and judges their structured output, and never
edits the work product itself. Understanding the system means reading those two
command files plus `agents/` and `scripts/` together:

- **Shared spine.** Both commands run entry phases (`build`: E1 worktree, E2
  brainstorm; `fix`: E1′ locate branch, E2′ brainstorm feedback) then a common
  **S1–S7** spine: S1 spec-review → S2 plan → S3 produce → S4 verify → S5 work-review →
  S6 squash → S7 finish. **It never merges** — the deliverable is a review-ready branch.

- **Ralph convergence loops (S1, S5).** review → fix → re-review until the frozen
  review panel all-PASSes or a per-phase cap (default 3) is hit. Convergence is decided
  **only from on-disk verdicts** in the strict `VERDICT / BLOCKING / NON-BLOCKING`
  grammar — never from the orchestrator's opinion. Round 0 short-circuits if all-PASS.

- **Named review roster (`agents/`).** Each reviewer is a **read-only, single-lens**
  agent whose frontmatter is **self-describing** (`lens` / `phase` / `tier` /
  `applies_to`) so the selector can route it with no code change. `reviewer-contract.md`
  is an authoring-time template (selector-inert: no `phase`) inlined into each reviewer.
  Reviewers are dispatched **natively** as `Task(subagent_type="autopilot:<name>")`,
  each running at its own `model` + read-only `tools` allowlist.

- **Selection stage (`scripts/select-panel.py`).** Deterministic, stdlib-only router:
  `(phase, signals) → JSON panel` of `{agent, subagent_type, tier, matched}`. Every
  `core` agent is a mandatory floor; `optional` agents route in when their `applies_to`
  matches the signals (spec keywords for S1; changed paths for S5). A file is a
  "reviewer" iff its frontmatter has `phase` (`lint-roster.py` mirrors this rule —
  keep the two in lockstep).

- **Config (`scripts/autopilot-config.py`).** Reads/initializes
  `${CLAUDE_PLUGIN_DATA}/config.json` (the plugin's own data dir, never Claude's
  `settings.json`). Toggles the Ralph driver (`ralphLoop.enabled`: native loop vs. the
  optional `ralph-loop` plugin) and per-phase caps.

- **Disk-backed state.** A run persists a **spec doc** and a **plan doc** (implementation
  plan + a progress section + a `RESUME:` block). The RESUME block
  (`phase=… worktree=… branch=… base_ref=… ralph_round=…`) lets a run survive
  compaction and resume from the current phase; an interrupted review round re-runs whole.

- **Built on `superpowers`.** The pipeline orchestrates superpowers skills
  (brainstorming, writing-plans, subagent-driven-development, using-git-worktrees,
  verification-before-completion, finishing-a-development-branch,
  dispatching-parallel-agents). It is a **hard dependency** — the commands preflight for
  it and hand off install instructions if missing. There is no plugin auto-dependency
  mechanism, so dependencies are documented in `README.md`, not declared.

## Conventions & gotchas (non-obvious, learned the hard way)

- **`${CLAUDE_PLUGIN_DATA}` is NOT exported to bash subprocesses.** Claude Code
  inline-substitutes it into command *text*, but a `python3` call won't see it in
  `os.environ` unless you forward it explicitly:
  `CLAUDE_PLUGIN_DATA='…' python3 scripts/autopilot-config.py`.
- **Roster agents are only dispatchable as `autopilot:<name>` from the *installed*
  plugin.** After adding/renaming an agent, the new `subagent_type` resolves only once
  the plugin is reloaded/updated — a fresh agent can't be dispatched natively in the
  same run that creates it (dispatch it ad-hoc via `general-purpose` until shipped).
- **`SPEC.md` and `dev-docs/` are gitignored** (local design doc + per-build audit
  trail `dev-docs/<date>-<slug>-{spec,plan}.md`). `SPEC.md` is the design source of
  truth but isn't shipped; keep it synced locally but don't reference it from
  shipped docs (its `§` numbers would be dead links). Note SPEC's §7.3 three-file state
  model (`task_plan.md`/`findings.md`/`progress.md`) is the aspirational "full-design
  target" — the actual commands use the simpler spec-doc + plan-doc model above.
- **Releases use explicit semver kept in sync across THREE places**: `version` in
  `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, plus the status
  line + "currently `x.y.z`" + repo-tree comment in `README.md`. Tag annotated as
  `v-X.Y.Z` (hyphenated).

## Review roster authoring rule

When you **create or update an agent** in `agents/`, run the roster lint and fix any
failures before committing:

```bash
python3 scripts/lint-roster.py
```

It enforces A3 for every reviewer: valid frontmatter (`lens`/`phase`/`tier`/
`applies_to` + `maxTurns`), a read-only `tools` allowlist (`Read, Grep, Glob, Bash`),
the inlined reviewer contract, and the strict verdict block — so a malformed reviewer
fails loudly at authoring time instead of being silently mis-routed by the selector. It
is an authoring/CI check, **not** a step in the `/autopilot:build` or `/autopilot:fix`
pipeline.
