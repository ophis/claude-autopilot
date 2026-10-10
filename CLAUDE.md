# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Claude Autopilot is a **Claude Code plugin** that packages an autonomous
build / light-build pipeline driven by a committed roster of named
review agents. The git repo **is both
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

Also run the manual smoke in README "Smoke test (the build eval)".

There is no build step. `tests/test_scripts.py` exercises `scripts/select-panel.py`
and `scripts/autopilot-config.py` as CLIs via subprocess (they have hyphenated names,
so they're not importable — the CLI is the contract).

## Architecture (the big picture)

The two surfaces — `skills/build/SKILL.md` and `skills/light-build/SKILL.md` — are
**orchestrator prompts**, not code. They are **skills** (model-invocable, so composable as a
step inside a larger skill/workflow); users still type `/autopilot:build` /
`/autopilot:light-build`. `light-build` is the **superpowers-free** surface: a
self-contained, low-ceremony harness (S1 → S5 → S6 → S7 → S8 → S9) with no spec doc, no
spec review, a lazy by-exception state model (no mandatory plan doc), and a pinned cap-1 S7 (correctness + requirement-fidelity + doc);
every phase uses a native tool, the plugin's own script, or inline logic, so it invokes no
`superpowers:*` skill and has no superpowers preflight. `light-build` does not
gate scope — surface choice is the user's responsibility. When invoked, the
*main-session Claude becomes a thin orchestrator*: it dispatches subagents and judges
their structured output, and never edits the work product itself. Understanding the
system means reading those two skill files plus `agents/` and `scripts/` together:

- **Shared spine.** `build` runs a single **S1–S9** pipeline: S1 worktree → S2 brainstorm →
  S3 spec-review → S4 task list → S5 produce → S6 verify → S7 work-review → S8 squash → S9 finish.
  `light-build` skips S2–S4 (same number = same step).
  **It never merges** — the deliverable is a review-ready branch.

- **Ralph convergence loops (S3, S7).** review → fix → re-review until the frozen
  review panel all-PASSes or a per-phase cap (default 3) is hit. Convergence is decided
  **only from reviewers' own verdicts** in the strict `VERDICT / BLOCKING / NON-BLOCKING`
  grammar — never from the orchestrator's opinion. Rounds are batched (wait for every
  verdict, one fix, one re-review); the orchestrator never overrides a verdict. Round 0
  short-circuits if all-PASS.

- **Named review roster (`agents/`).** Each reviewer is a **read-only, single-lens**
  agent whose frontmatter is **self-describing** (`lens` / `phase` / `tier` /
  `applies_to`) so the selector can route it with no code change. `reviewer-contract.md`
  is an authoring-time template (selector-inert: no `phase`) inlined into each reviewer.
  Reviewers run as `autopilot:<name>`, each at its own `model` + read-only `tools`
  allowlist. **Each round** is one call to the plugin workflow (below) — a re-reviewed lens
  is a fresh member primed with its prior items (+ the fix diff in S7). If that call fails,
  the phase falls back to a parallel native `Task` batch of the same members and prompts.
  **Both surfaces** run the convergence loop natively in the orchestrator (round 0 + fix →
  re-review until all-PASS or the per-phase cap). The orchestrator owns the loop, the fix
  (a fixer continued across rounds), and the re-review set: S3 the full panel; S7 the
  lenses that failed plus every core lens (light-build: only the failed ones).

- **Selection stage (`scripts/select-panel.py`).** Deterministic, stdlib-only router:
  `(phase, signals) → JSON panel` of `{agent, subagent_type, tier, matched}`. Every
  `core` agent is a mandatory floor; `optional` agents route in when their `applies_to`
  matches the signals (spec keywords for S3; changed paths for S7). `tier` is usually a
  scalar but may be a per-phase JSON map (`tier: {"spec":"core","work":"optional"}` —
  resolved to the effective scalar per phase, emitted as such); `applies_to` may carry
  the reserved `@structural` work-phase token, which matches iff the diff changed file
  topology (any A/D/R/C file in `git diff --name-status`). A file is a "reviewer" iff its
  frontmatter has `phase` (`lint-roster.py` mirrors this rule — keep the two in lockstep).

- **Plugin workflow (`workflows/review-round.js`).** The v0.9.x per-round review transport,
  restored byte-identical and invoked by name as `autopilot:autopilot-review-round` (the
  runtime names plugin workflows `<plugin>:<meta.name>`). The default S3/S7 review-round
  transport of both skills; Task is the fallback. Contract in README "Plugin workflow".

- **Config (`scripts/autopilot-config.py`).** Reads/initializes
  `${CLAUDE_PLUGIN_DATA}/config.json` (the plugin's own data dir, never Claude's
  `settings.json`). Holds the Ralph-loop per-phase caps (`ralphLoop.maxIterations.*`).
  The old `ralphLoop.enabled` driver toggle (native vs. `ralph-loop` plugin) is
  deprecated and ignored — the native loop is the only driver.

- **Disk-backed state.** A run persists a **spec doc** and a **plan doc** (task list +
  a progress section + a `RESUME:` block). The RESUME block
  (`phase=… worktree=… branch=… base_ref=… review_round=…`) lets a run survive
  compaction and resume from the current phase; an interrupted review round re-runs whole.
  The progress section records each S5 task done (a resume continues from the next), the
  review transport, and per-lens blocker gists that prime re-reviewed lenses.

- **Built on `superpowers`.** `build` orchestrates superpowers
  skills (brainstorming, verification-before-completion). (Worktree creation is raw
  `git worktree` + the native `EnterWorktree`, not a superpowers skill.) For `build` it is a **hard dependency** —
  it preflights for it and hands off install instructions if missing. `light-build` is
  the exception: it is self-contained, invokes no `superpowers:*` skill, and has no
  superpowers preflight. There is no plugin auto-dependency mechanism, so dependencies
  are documented in `README.md`, not declared.

## Conventions & gotchas (non-obvious, learned the hard way)

- **`${CLAUDE_PLUGIN_DATA}` is NOT exported to bash subprocesses.** Claude Code
  inline-substitutes it into command *text*, but a `python3` call won't see it in
  `os.environ` unless you forward it explicitly:
  `CLAUDE_PLUGIN_DATA='…' python3 scripts/autopilot-config.py`.
- **Roster agents are only dispatchable as `autopilot:<name>` from the *installed*
  plugin.** After adding/renaming an agent, the new `subagent_type` resolves only once
  the plugin is reloaded/updated — a fresh agent can't be dispatched natively in the
  same run that creates it (dispatch it ad-hoc via `general-purpose` until shipped).
  The same applies to the `skills/build` + `skills/light-build` skills: edits to a
  `SKILL.md` (and `/autopilot:build` / `/autopilot:light-build` by-name invocability) go live only after `/reload-plugins`.
- **Give a subagent the worktree-absolute path for `CLAUDE.md` edits.** Told to edit
  `CLAUDE.md` in a worktree, one edited the repo-root copy loaded in its context;
  `git -C <worktree> add -A` doesn't see it, so the edit strands on `main`.
- **`dev-docs/` is gitignored** (per-build audit trail
  `dev-docs/<date>-<slug>-{spec,plan}.md`).
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
is an authoring/CI check, **not** a step in the `/autopilot:build` pipeline.
