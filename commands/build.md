---
description: "Autonomous pipeline: worktree → spec+review loop → plan → subagent implementation → verify → review loop → docs → squash. Produces a review-ready branch; never merges. Explicit-only."
argument-hint: "<requirements>"
disable-model-invocation: true
---

# Autopilot: build

You are the orchestrator for an autonomous build run. Drive the pipeline below end
to end. Dispatch and judge; do not do the work yourself.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the **requirements** — the thing to build. Treat it as the single
source of intent. If it is empty, STOP with a handoff asking for requirements.

## Preflight (dependencies)

Before E1, confirm the **superpowers** plugin is available — its skills must appear
in your skill list (brainstorming, writing-plans, subagent-driven-development,
using-git-worktrees, verification-before-completion, finishing-a-development-branch,
dispatching-parallel-agents). This whole pipeline is built on them, and Claude Code
has no plugin auto-dependency mechanism, so this preflight is the safety net.

If superpowers is **not** available, STOP with a handoff (not a question): tell the
user it is required and how to install it —
`/plugin marketplace add obra/superpowers` then
`/plugin install superpowers@superpowers` — and to re-run `/autopilot:build` after.
(`planning-with-files` is optional.)

## Operating disciplines

- **Autonomous — never ask the user.** On resolvable doubt: decide, record the
  decision in the spec doc, proceed. On a *consequential fork*: decide AND dispatch
  exactly ONE challenger team to stress the decision; reconcile, record, proceed.
  Only the four safety stops interrupt the run.
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never
  hoard whole files, diffs, or logs in the main thread. Read only bounded slices
  when you must inspect something yourself.
- **Disk-backed.** Persist the spec, the plan, and a progress note (with a RESUME
  block) so the run survives compaction. Location follows the user's/project's
  convention — see **State & resumption**.
- **A STOP is a handoff, never a question:** emit current state + the exact next
  step a human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

## Resume first

Before anything else, look for an existing progress note with a RESUME block in the
project's convention location. If found: reconcile worktree/branch/base_ref
existence on disk, then continue from `phase`. An interrupted review round is
**re-run from scratch** (re-dispatch the whole frozen panel — bounded and
idempotent), so trust only `ralph_round` for loop position. If no progress note
exists, start at E1.

## Summoning a team (ad-hoc, fresh, inline — no agent files)

Use `superpowers:dispatching-parallel-agents` to summon reviewers/producers inline.
Personas are derived per phase from deterministic signals — never persisted as agent
files.

- **Derive the panel** from signals: spec keywords for S1; `git diff --name-only
  base_ref...HEAD` for S5. Always include a **floor lens** (S1: spec-fitness +
  structure; S5: correctness + quality). Add domain lenses by signal: code →
  quality + tests; auth/IO/deps/net/crypto → security; docs-only → prose/structure.
- **Cap ~4 lenses.** Pick the smallest panel that covers the signals.
- **Freeze the panel** for the phase. Log the chosen panel AND the skips to the
  progress doc, e.g. "skipped security: no IO/auth signal".
- **Dispatch template (short, by-reference):** role + one-line lens; inputs =
  worktree path, base_ref, the requirement string, a focus line; read-only
  ("modify nothing"); the reviewer fetches its own material (S1 reads the spec doc;
  S5 runs a path-scoped `git diff`). Each reviewer MUST return the verdict block
  below. Reviewers load no superpowers skills. Tier model/effort per lens (soft —
  let the dispatch tool decide).

## Verdict grammar (paste inline into every summon prompt)

```
VERDICT: PASS            # or exactly: VERDICT: FAIL
BLOCKING: none           # or one "- " item per line
NON-BLOCKING: none       # or one "- " item per line
```

PASS ⟺ `BLOCKING: none`; FAIL ⟹ ≥1 blocker. Cite evidence (file:line / spec
clause); flag blockers, not preferences. A missing, unparseable, or empty-on-FAIL
verdict counts as **FAIL**. Convergence is decided from these on-disk verdicts,
never from vibes.

## Ralph loop (S1 and S5)

`round = 0`, `cap = 3` (2 is steady state).
- **Round-0 short-circuit:** all-PASS on round 0 → advance immediately (no
  re-review is owed before any fix exists).
- After a fix, **re-dispatch only the FAILed + fix-touched lenses**; untouched
  lenses carry their prior PASS.
- Advance on all-PASS with no open blocker.
- At `cap` → STOP with a compact classification: `oscillation | unfixable |
  requirements-conflict`, citing the relevant lines.

Round state lives in-context within a run; persisted `ralph_round` exists only so a
resumed run re-runs the interrupted round whole (see Resume contract).

## Pipeline (E1, E2, S1–S8)

- **E1 — worktree (step 1).** Use `superpowers:using-git-worktrees` → branch
  `autopilot/<slug>`. Slug = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens,
  collapsed/trimmed, truncated to ~40 chars. Record worktree/branch/base_ref (HEAD)
  in the RESUME block; create the spec + progress notes per the project's
  convention. On worktree/branch collision: one retry with a uniquified slug
  (`-2`, …), else STOP.
- **E2 — brainstorm (step 2).** Use `superpowers:brainstorming` on `$ARGUMENTS` →
  write the spec into the spec doc. Decide on doubt; record decisions.
- **S1 — spec review (steps 2–3).** Run the Ralph loop over the spec. Fixes =
  orchestrator edits the spec doc. If the core requirement is self-contradictory
  (cite two clauses) → STOP (root-contradiction).
- **S2 — plan (step 4).** Use `superpowers:writing-plans` → write the plan into the
  spec doc and record how the work will be verified. On a consequential plan fork →
  decide + dispatch ONE challenger.
- **S3 — produce (step 5).** Produce the work product. Code →
  `superpowers:subagent-driven-development` (it may commit per task and run its own
  task-level review — that is fine; S5 is the authoritative gate and the S7 squash
  folds its commits). Non-code → producer subagents via the same dispatch pattern.
  The orchestrator never edits the work product itself.
- **S4 — verify (step 6).** Use `superpowers:verification-before-completion`: run
  the discovered checks. For THIS plugin = `claude plugin validate` + the documented
  manual smoke. Cap fixes at 3. Never weaken, skip, or delete a check; a drop in the
  check count → STOP.
- **S5 — work review (step 7).** Run the Ralph loop over the work. Fixes = ONE fresh
  producer subagent primed with the deduped open blockers + the cited files only.
- **S6 — docs (step 8).** Update the README (document the command + the manual
  smoke) and add a one-line SPEC status note. Keep doc edits bounded.
- **S7 — squash (step 9).** Idempotent squash to one commit (skip if already exactly
  1 ahead of base_ref). Working notes (spec/plan/progress) are committed or ignored
  per the project's convention — do not force either.
- **S8 — finish (step 10).** Use `superpowers:finishing-a-development-branch` →
  report: review history, decisions, deferred non-blockers (stop-reason first if the
  run stopped); offer integration options as an informational report menu, NOT a
  question. NO merge.

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on:
1. **Destructive op — only when Auto Mode is OFF.** Before any force-push, write
   outside the worktree, history rewrite beyond this branch, or rm/reset of
   uncommitted work. **If the session is in Auto Mode** (auto-accept /
   bypass-permissions), skip this stop — destructive-op judgment is deferred to
   Auto Mode. The other three stops below apply regardless of Auto Mode.
2. **Non-convergence at cap** — a Ralph loop hits `cap` (with the classification).
3. **Non-review phase failure** — one retry, then STOP.
4. **Root-contradiction** — the core requirement is self-contradictory; cite the
   two clauses.

## Token discipline

Thin orchestrator · by-reference dispatch (never pipe diffs into N prompts) ·
smallest panel (2–4, conditional lenses only on signal) · round-0 short-circuit ·
cap 3, re-dispatch only FAILed/touched lenses · bounded subagent prompts, no
superpowers skills loaded into reviewers · producer primed by blockers + cited files
only.

## State & resumption

Persist three things so the run survives compaction: the brainstormed **spec**, the
**plan**, and a **progress note** carrying a small RESUME block:

```
RESUME: phase=<E1|E2|S1..S8> worktree=<path> branch=<name> base_ref=<sha> ralph_round=<n>
```

**Where these live follows the user's / project's existing convention** — honor
CLAUDE.md preferences and existing repo patterns. The command imposes no fixed path
(do not assume `dev-docs/`) and no gitignore-vs-commit policy.

**Resume contract:** on resume, reconcile worktree/branch existence first, then
continue from `phase`; an interrupted review round is re-run from scratch
(re-dispatch the whole frozen panel — bounded, idempotent), so only `ralph_round`
need be persisted to locate the loop.
