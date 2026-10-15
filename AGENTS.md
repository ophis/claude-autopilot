# AGENTS.md

This file provides repository guidance to Claude Code and Codex.

## What this is

Claude Autopilot is a **Claude Code and Codex plugin** that packages an autonomous
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

# Lint the review roster — run after editing agents/
python3 scripts/lint-roster.py

# Local dev loop: load the plugin from the working copy, then hot-reload after edits
claude --plugin-dir .
/reload-plugins
```

Also run the [contributor smoke protocol](CONTRIBUTING.md#smoke-protocol).

There is no build step. `tests/test_scripts.py` exercises `skills/build/scripts/select-panel.py`,
`skills/build/scripts/check-spec.py`, `skills/build/scripts/ci-verdict.py` and `skills/build/scripts/pr.py` (against a fake `gh` on `PATH`),
`skills/build/scripts/resolve-branch.py` (on temp git repos) and `scripts/lint-roster.py` as CLIs via subprocess (they have hyphenated names,
so they're not importable — the CLI is the contract).

## Architecture (the big picture)

The two surfaces — `skills/build/SKILL.md` and `skills/light-build/SKILL.md` — are
**orchestrator prompts**, not code. They are **skills** (model-invocable, so composable as a
step inside a larger skill/workflow); users still type `/autopilot:build` /
`/autopilot:light-build`. `light-build` is the low-ceremony surface: a harness
(S1 → S4 → S5 → S6 → S7) with no spec doc and no spec review; S6 is a pinned panel
capped at 3 rounds
(correctness + requirement-fidelity + doc + verification). It does not gate scope — surface choice is
the user's responsibility. When invoked, the *main-session agent implements the work itself* (S5 tasks and S6 fixes,
optionally handing a self-contained task to a fresh producer) while independent reviewer
subagents judge it; only their verdicts decide. Both read `references/autopilot-common.md` first: the rules they share (disciplines,
state, council, worktree, review round, fixes, safety stops, result block); each SKILL.md
keeps only its own input, state, steps and review settings. Understanding the system means
reading those three files plus `agents/` and the bundled `skills/build/scripts/` helpers together:

- **Shared spine.** `build` runs a single **S1–S7** pipeline: S1 worktree → S2 spec →
  S3 spec-review → S4 task list → S5 produce → S6 work-review → S7 finish.
  `light-build` skips S2, S3 (same number = same step).
  **It never merges** — the deliverable is a review-ready branch, plus a draft PR when
  publishing (S1 `publish`, all `gh` steps in `skills/build/scripts/pr.py`): `pr` when the
  requirement asks for a PR (each commit pushed as it lands, build posts the reviewed spec,
  ready on convergence), `ci` when the repo has a pull_request workflow (pushed at S6 pins,
  a draft during the run). Either way the repo's CI is the verifier's backend, read by
  `skills/build/scripts/ci-verdict.py`; a full suite never runs locally while CI can run it.

- **Ralph convergence loops (S3, S6).** review → fix → re-review until the frozen
  review panel all-PASSes or a per-phase cap (build: 3 total rounds) is hit. Convergence is decided
  **only from reviewers' own verdicts** in the strict `VERDICT / BLOCKING / NON-BLOCKING`
  grammar — never from the orchestrator's opinion. Rounds are batched (wait for every
  verdict, one fix, one re-review); the orchestrator never overrides a verdict. Round 1
  short-circuits if all-PASS. Build counts it toward its 3-round cap (override in
  the requirement); light-build has the same 3-round cap.

- **Named review roster (`agents/`).** Each reviewer has a single lens. Ordinary reviewers
  are read-only and never run the full test suite; the core work-phase verification
  reviewer runs the complete checks in the frozen source worktree at the reviewed SHA, or
  when publishing reads the CI checks the plan doc names as running the tests for that
  SHA and falls back to local checks. Each
  agent has **self-describing** frontmatter (`lens` / `phase` / `tier` /
  `applies_to`) so the selector can route it with no code change. `reviewer-contract.md`
  is an authoring-time template (selector-inert: no `phase`) copied verbatim into ordinary reviewers (a test enforces it);
  `verification-reviewer.md` follows its dedicated execution contract.
  Both skills use neutral actions with Claude tool forms in parentheses.
  Claude reviewers run as `autopilot:<name>` with configured models;
  Codex inherits the host model and gives generic agents the canonical reviewer files.
  **Each round** uses the plugin workflow when exposed, otherwise native dispatch; a re-reviewed lens
  is a fresh member primed with its prior items (+ the fix diff in S6). If that call fails,
  the phase falls back to a native host dispatch batch of the same members and prompts.
  **Both surfaces** run the convergence loop natively in the orchestrator (Round 1 + fix →
  re-review until all-PASS or the per-phase cap). The orchestrator owns the loop, the fix
  (made by the orchestrator itself), and the re-review set: S3 the full panel; S6 the
  lenses that failed plus every core lens, the verifier included (light-build: failed
  lenses plus the verifier every round, and correctness after a verifier FAIL).

- **Selection stage (`skills/build/scripts/select-panel.py`).** Deterministic, stdlib-only router:
  `(phase, signals) → JSON panel` of `{agent, subagent_type, tier, matched}`. Every
  `core` agent is a mandatory floor; `optional` agents route in when their `applies_to`
  matches the signals (spec keywords for S3; changed paths for S6). `tier` is usually a
  scalar but may be a per-phase JSON map (`tier: {"spec":"core","work":"optional"}` —
  resolved to the effective scalar per phase, emitted as such); `applies_to` may carry
  the reserved `@structural` work-phase token, which matches iff the diff changed file
  topology (any A/D/R/C file in `git diff --name-status`). A file is a "reviewer" iff its
  frontmatter has `phase` (`lint-roster.py` mirrors this rule — keep the two in lockstep).

- **Plugin workflow (`workflows/review-round.js`).** The per-round review transport,
  invoked by name as `autopilot:autopilot-review-round` (the
  runtime names plugin workflows `<plugin>:<meta.name>`). The default S3/S6 review-round
  transport when Workflow is exposed; native host dispatch is the fallback.
  Contract in README "Plugin workflow".

- **S1 resolver (`skills/build/scripts/resolve-branch.py`).** Decides where a run works:
  resume this input's unfinished plan doc (by `input_sha`), stay on a non-default branch,
  reuse or create a worktree, or stop on a dirty checkout. It changes nothing but may
  record origin's default branch, and prints JSON.

- **Disk-backed state.** Each run keeps all its state in one ignored plan doc,
  `.autopilot/<slug>-plan.md` in its worktree, created at S1 and identified by the
  `input` it records (build adds a spec doc beside it). It holds the verify command, a
  `RESUME:` line (schema in common: State and resume), the progress log, every round's
  review items, Notes and the task list. A run survives compaction by re-hydrating from it and `git log` (common:
  Re-hydrate after compaction); an interrupted review round re-runs whole. At finish the
  docs are copied to the project's plan location if its AGENTS.md / CLAUDE.md names one.

- **No plugin dependencies.** Both surfaces use only native tools, the plugin's own
  scripts, or inline logic; neither invokes another plugin's skill or preflights for one.
  build and light-build S4 both say "invoke no planning skill" so an installed one
  isn't pulled into S4.

## Conventions & gotchas (non-obvious, learned the hard way)

- **On Claude Code, roster agents are only dispatchable as `autopilot:<name>` from
  the *installed* plugin.** After adding/renaming an agent, the new `subagent_type` resolves only once
  the plugin is reloaded/updated — a fresh agent can't be dispatched natively in the
  same run that creates it (dispatch it ad-hoc via `general-purpose` until shipped).
  The same applies to the `skills/build` + `skills/light-build` skills: edits to a
  `SKILL.md` or `references/autopilot-common.md` (and `/autopilot:build` / `/autopilot:light-build` by-name invocability) go live only after `/reload-plugins`.
- **Give a subagent the worktree-absolute path for `AGENTS.md` edits.** Told to edit
  `AGENTS.md` in a worktree, one edited the repo-root copy loaded in its context;
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

It checks every reviewer: valid frontmatter (`lens`/`phase`/`tier`/
`applies_to` + `maxTurns`), a `tools` allowlist (`Read, Grep, Glob, Bash`),
the ordinary reviewers' inlined contract or the verification reviewer's dedicated
execution contract, and the strict verdict block — so a malformed reviewer
fails loudly at authoring time instead of being silently mis-routed by the selector. It
is an authoring/CI check, **not** a step in the `/autopilot:build` pipeline.
