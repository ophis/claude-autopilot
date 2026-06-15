# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Claude Autopilot is a **Claude Code plugin** that packages an autonomous
build / fix / medium-build / light-build pipeline driven by a committed roster of named
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

There is no build step. `tests/test_scripts.py` exercises `scripts/select-panel.py`
and `scripts/autopilot-config.py` as CLIs via subprocess (they have hyphenated names,
so they're not importable — the CLI is the contract).

## Architecture (the big picture)

The four surfaces — `skills/build/SKILL.md`, `skills/fix/SKILL.md`,
`skills/medium-build/SKILL.md`, and `skills/light-build/SKILL.md` — are **orchestrator
prompts**, not code. They are **skills** (model-invocable, so composable as a step inside a
larger skill/workflow); users still type `/autopilot:build` / `/autopilot:fix` /
`/autopilot:medium-build` / `/autopilot:light-build`.
`medium-build` is a sibling orchestrator on a trimmed path — same S-spine concept but no S1
roster panel (a single expert reviewer does a one-shot spec review instead), no
`writing-plans`, and a trimmed S5. `light-build` is the **superpowers-free** surface: a
self-contained, low-ceremony harness (E1 → S3 → S4 → S5 → S6 → S7) with no spec doc, no
spec review, no `writing-plans`, a lazy by-exception state model (no mandatory plan doc), and a pinned cap-1 S5 (correctness + requirement-fidelity + doc);
every phase uses a native tool, the plugin's own script, or inline logic, so it invokes no
`superpowers:*` skill and has no superpowers preflight. Neither medium-build nor light-build
gates scope — surface choice is the user's responsibility. When invoked, the
*main-session Claude becomes a thin orchestrator*: it dispatches subagents and judges
their structured output, and never edits the work product itself. Understanding the
system means reading those four skill files plus `agents/` and `scripts/` together:

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
  Reviewers are dispatched **natively** — preferably one `Workflow` call per review
  round (`scripts/review-round.js`, a dumb-transport Dynamic Workflows script:
  `agentType` = the same `autopilot:<name>` handles, schema-validated verdicts,
  `synthetic: true` = per-member infra failure; it tolerates `args` arriving as a
  stringified JSON object), falling back stickily to a parallel
  `Task(subagent_type="autopilot:<name>")` batch — each reviewer at its own `model` +
  read-only `tools` allowlist either way. **Ad-hoc lenses** (a gap no roster agent
  covers) ride the **same `Workflow` transport** as `general-purpose` members —
  schema-validated like the roster, read-only by prompt (not by a tool allowlist) —
  and share the roster's fallbacks. `scriptPath` resolves from the *installed* plugin,
  like agent dispatch. `scripts/review-round.js` dispatches **one** round; **all four
  surfaces** run the convergence loop natively in the orchestrator (round 0 + fix → re-review
  until all-PASS or the per-phase cap), dispatching each round through it. The orchestrator
  owns the loop, the fix, and (S5) the `(FAILed ∪ touched)` re-review subset — preserving
  ground-truth `touched` (via `select-panel.py`) and a warm, same-session fixer.

- **Selection stage (`scripts/select-panel.py`).** Deterministic, stdlib-only router:
  `(phase, signals) → JSON panel` of `{agent, subagent_type, tier, matched}`. Every
  `core` agent is a mandatory floor; `optional` agents route in when their `applies_to`
  matches the signals (spec keywords for S1; changed paths for S5). `tier` is usually a
  scalar but may be a per-phase JSON map (`tier: {"spec":"core","work":"optional"}` —
  resolved to the effective scalar per phase, emitted as such); `applies_to` may carry
  the reserved `@structural` work-phase token, which matches iff the diff changed file
  topology (any A/D/R/C file in `git diff --name-status`). A file is a "reviewer" iff its
  frontmatter has `phase` (`lint-roster.py` mirrors this rule — keep the two in lockstep).

- **Config (`scripts/autopilot-config.py`).** Reads/initializes
  `${CLAUDE_PLUGIN_DATA}/config.json` (the plugin's own data dir, never Claude's
  `settings.json`). Holds the Ralph-loop per-phase caps (`ralphLoop.maxIterations.*`).
  The old `ralphLoop.enabled` driver toggle (native vs. `ralph-loop` plugin) is
  deprecated and ignored — the native loop is the only driver.

- **Disk-backed state.** A run persists a **spec doc** and a **plan doc** (implementation
  plan + a progress section + a `RESUME:` block). The RESUME block
  (`phase=… worktree=… branch=… base_ref=… review_round=…`) lets a run survive
  compaction and resume from the current phase; an interrupted review round re-runs whole.

- **Built on `superpowers`.** `build` / `fix` / `medium-build` orchestrate superpowers
  skills (brainstorming, writing-plans, subagent-driven-development, using-git-worktrees,
  verification-before-completion, finishing-a-development-branch,
  dispatching-parallel-agents). For those three surfaces it is a **hard dependency** —
  they preflight for it and hand off install instructions if missing. `light-build` is
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
  The same applies to the `skills/build` + `skills/fix` + `skills/medium-build` +
  `skills/light-build` skills: edits to a `SKILL.md` (and `/autopilot:build` /
  `/autopilot:fix` / `/autopilot:medium-build` / `/autopilot:light-build` by-name
  invocability) go live only after `/reload-plugins`.
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
