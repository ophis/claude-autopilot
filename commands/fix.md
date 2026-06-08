---
description: "Autonomous feedback loop: find the existing autopilot branch, brainstorm your review feedback into a change-spec, then plan → implement → verify → review → docs → re-squash. Updates a review-ready branch; never merges. Explicit-only."
argument-hint: "<feedback>"
disable-model-invocation: true
---

# Autopilot: fix

You are the orchestrator for an autonomous feedback round on an existing autopilot
branch. Drive the pipeline below end to end. Dispatch and judge; do not do the work
yourself.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the human **review feedback** on an existing autopilot branch. Treat
it as the single source of intent for this round. If it is empty, STOP with a
handoff asking for feedback.

## Preflight (dependencies)

**Load config (run first, every run):** run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. It creates `${CLAUDE_PLUGIN_DATA}/config.json` with defaults if absent and prints the effective config. Note `ralphLoop.enabled` and the per-phase caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase` for the S1/S5 Ralph loop. User edits to that file take effect on the next run.

Before E1′, confirm the **superpowers** plugin is available — its skills must appear
in your skill list (brainstorming, writing-plans, subagent-driven-development,
verification-before-completion, finishing-a-development-branch,
dispatching-parallel-agents). This whole pipeline is built on them, and Claude Code
has no plugin auto-dependency mechanism, so this preflight is the safety net.

If superpowers is **not** available, STOP with a handoff (not a question): tell the
user it is required and how to install it —
`/plugin marketplace add obra/superpowers` then
`/plugin install superpowers@superpowers` — and to re-run `/autopilot:fix` after.
(`planning-with-files` is optional.)

`ralph-loop` is required only when `ralphLoop.enabled` is `true` in
`${CLAUDE_PLUGIN_DATA}/config.json`; otherwise it is not needed.

## Operating disciplines

- **Autonomous — never ask the user.** On resolvable doubt: decide, record the
  decision in the spec doc, proceed. On a *consequential fork*: decide AND dispatch
  exactly ONE challenger team to stress the decision; reconcile, record, proceed.
  Only the four safety stops interrupt the autonomous pipeline mid-run.
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never
  hoard whole files, diffs, or logs in the main thread. Read only bounded slices
  when you must inspect something yourself.
- **Disk-backed.** Persist the change-spec, the plan, and a progress note (with a
  RESUME block) so the run survives compaction. Location follows the
  user's/project's convention — see **State & resumption**.
- **A STOP is a handoff, never a question:** emit current state + the exact next
  step a human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

## Resume first

Look for an existing progress note with a RESUME block in the project's convention
location. If found: reconcile worktree/branch/base_ref existence on disk, then
continue from `phase` (an interrupted review round re-runs whole). **If none, that
is the normal first run → go to E1′ (locate); never create a branch.**

## Summoning a team (ad-hoc, fresh, inline — no agent files)

Use `superpowers:dispatching-parallel-agents` to summon reviewers/producers inline.
Personas are derived per phase from deterministic signals — never persisted as agent
files.

- **Derive the panel** from signals: change-spec keywords for S1; `git diff
  --name-only base_ref...HEAD` for S5. Always include a **floor lens** (S1:
  spec-fitness + structure; S5: correctness + quality). Add domain lenses by signal:
  code → quality + tests; auth/IO/deps/net/crypto → security; docs-only →
  prose/structure.
- **Cap ~4 lenses.** Pick the smallest panel that covers the signals.
- **Freeze the panel** for the phase. Log the chosen panel AND the skips to the
  progress doc, e.g. "skipped security: no IO/auth signal".
- **Dispatch template (short, by-reference):** role + one-line lens; inputs =
  worktree path, base_ref, the requirement/feedback string, a focus line; read-only
  ("modify nothing"); the reviewer fetches its own material (S1 reads the
  change-spec doc; S5 runs a path-scoped `git diff`). Each reviewer MUST return the
  verdict block below. Reviewers load no superpowers skills. Tier model/effort per
  lens (soft — let the dispatch tool decide).

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

The two review-convergence phases — **S1** (spec review) and **S5** (work review) —
run a Ralph loop: review → fix → re-review until the panel passes, capped at the
per-phase cap (default 3 rounds). The driver is chosen by config.

**Config (loaded in Preflight):** from `${CLAUDE_PLUGIN_DATA}/config.json` →
`{ "ralphLoop": { "enabled": false, "maxIterations": { "spec-phase": 3, "implementation-phase": 3 } } }`.
`ralphLoop.enabled` picks the driver; `ralphLoop.maxIterations.spec-phase` / `.implementation-phase` is the per-phase round cap (default 3). `ralph-loop` is required only when enabled.

- **Default (`enabled: false`) — native loop.** The orchestrator runs the rounds
  itself: each round, dispatch the frozen panel fresh and collect verdicts to disk;
  round-0 all-PASS short-circuits; advance on all-PASS with no open BLOCKING, else
  apply fixes and re-dispatch; cap = `maxIterations.spec-phase` (S1) /
  `maxIterations.implementation-phase` (S5), default 3.
- **`enabled: true` — ralph-loop plugin.** Drive the phase with one
  `/ralph-loop:ralph-loop` whose looped prompt is ONE round and whose
  completion-promise is the phase marker:
  - **S1** → `/ralph-loop:ralph-loop "Run ONE spec-review round: dispatch the frozen S1 panel fresh (read the spec doc); write each VERDICT to the progress doc. If every lens is PASS with no open BLOCKING, print exactly 'AUTOPILOT: SPEC READY'; otherwise edit the spec to resolve every BLOCKING item and do NOT print the marker." --max-iterations <maxIterations.spec-phase> --completion-promise "AUTOPILOT: SPEC READY"`
  - **S5** → `/ralph-loop:ralph-loop "Run ONE work-review round: dispatch the frozen S5 panel fresh against the diff (git diff base_ref...HEAD); write each VERDICT. If every lens is PASS with no open BLOCKING, print exactly 'AUTOPILOT: WORK READY'; otherwise dispatch ONE producer subagent to fix every BLOCKING item, then do NOT print the marker." --max-iterations <maxIterations.implementation-phase> --completion-promise "AUTOPILOT: WORK READY"`

Both drivers obey the same rules: a fresh panel each round; convergence is decided
from the on-disk verdicts (the marker is printed ONLY when convergence is genuinely
true — never to escape the loop); on the marker the phase is done and the command
proceeds (S1→S2, S5→S6); if the per-phase cap (`maxIterations.spec-phase` /
`.implementation-phase`, default 3) is hit WITHOUT the marker → non-convergence STOP
with the 3-way classification (oscillation | unfixable | requirements-conflict) and
a handoff — do not proceed.

## Pipeline (E1′, E2′, S1–S8)

Legend: **E#** = entry phase (command-specific; `′` = fix variant); **S#** = shared
spine (common to build & fix).

- **E1′ — locate the existing branch (no new worktree).** Find the target autopilot
  branch: read the project's RESUME note if present; else the most recent
  `autopilot/*` branch. **If none → STOP** ("no autopilot branch found — run
  `/autopilot:build <requirements>` first"). Never create a new branch.
  - **Worktree:** use the branch's existing worktree; if it was removed, check the
    branch out in place — never create a second worktree for it.
  - **base_ref:** reuse the value in that branch's RESUME note if present; else
    `git merge-base main autopilot/<slug>` (default branch = `main` unless the repo
    says otherwise). Record worktree/branch/base_ref.
  - **Dirty tree:** if the worktree has uncommitted changes, STOP with a handoff
    (commit or stash first) so they aren't folded into the re-squash — unless Auto
    Mode is on (then proceed, deferring to Auto Mode).
- **E2′ — brainstorm the feedback.** Use `superpowers:brainstorming` on `$ARGUMENTS`
  (the feedback) → write a **change-spec** appended to the existing spec doc (the
  original spec stays as context). Decide on doubt; record decisions.
- **S1 — change-spec review (Ralph loop).** Review the **change-spec** (with the
  original as context), not the original. Panel derived from the change-spec's
  keywords; reviewers read the change-spec doc (as in build's S1). Run the **S1
  Ralph loop** (above) over the (change-)spec. **Fixes:** the orchestrator edits the
  spec doc directly (the spec is a small artifact it holds; only S5 delegates fixes
  to a producer). On convergence it records `AUTOPILOT: SPEC READY`.
  **Root-contradiction STOP:** if the reviewers find the core requirement asks for
  two things that cannot both be true, STOP and hand off — quote the two conflicting
  clauses (this is a handoff, never a question; mere vagueness is decided, not
  stopped).
- **S2 — plan the delta.** Use `superpowers:writing-plans` → write the plan for the
  change into the spec doc; record how the work will be verified. On a consequential
  plan fork → decide + dispatch ONE challenger.
- **S3 — produce.** Code → `superpowers:subagent-driven-development` (it may commit
  per task and run its own task-level review — that is fine; S5 is the authoritative
  gate and the S7 re-squash folds its commits). Non-code → producer subagents via
  the same dispatch pattern. The orchestrator never edits the work product itself.
- **S4 — verify.** Use `superpowers:verification-before-completion`: run the
  discovered checks. For THIS plugin = `claude plugin validate` + the documented
  manual smoke. Cap fixes at 3; never weaken, skip, or delete a check; a drop in the
  check count → STOP.
- **S5 — work review (Ralph loop).** Panel derived from the **delta diff**
  (`git diff --name-only base_ref...HEAD`); reviewers run a path-scoped diff. Run the
  **S5 Ralph loop** (above) over the work. **Fixes:** ONE fresh producer subagent
  primed with the deduped open blockers + cited files only. On convergence it records
  `AUTOPILOT: WORK READY`.
- **S6 — docs.** Update the README/companion docs to match the change. Keep doc
  edits bounded.
- **S7 — re-squash.** Squash the branch back to **one** clean commit (fold the new
  feedback commits into the existing single commit). Local, unpushed history rewrite
  **within the branch's own commits** — permitted by the destructive-op stop (and
  skipped under Auto Mode). Idempotent: if already exactly 1 ahead of base_ref, skip.
  Record the pre-squash HEAD SHA in the RESUME block so an interrupted re-squash is
  detected on resume.
- **S8 — report (no merge).** Use `superpowers:finishing-a-development-branch` →
  report: review history, decisions, deferred non-blockers (stop-reason first if the
  run stopped); offer integration options as an informational report menu, NOT a
  question. **NO merge.**

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on:
1. **Destructive op — only when Auto Mode is OFF.** Before any force-push, write
   outside the worktree, history rewrite beyond this branch, or rm/reset of
   uncommitted work. **If the session is in Auto Mode** (auto-accept /
   bypass-permissions), skip this stop — destructive-op judgment is deferred to
   Auto Mode. The other three stops below apply regardless of Auto Mode.
2. **Non-convergence at cap** — a Ralph loop hits `cap` (with the classification).
3. **Non-review phase failure** — one retry, then STOP.
4. **Root-contradiction** — the feedback irreconcilably contradicts a locked
   requirement (or the core requirement is self-contradictory); cite the two clauses.

## Token discipline

Thin orchestrator · by-reference dispatch (never pipe diffs into N prompts) ·
smallest panel (2–4, conditional lenses only on signal) · round-0 short-circuit ·
per-phase cap (`maxIterations.spec-phase` / `.implementation-phase`, default 3),
re-dispatch only FAILed/touched lenses · bounded subagent prompts, no
superpowers skills loaded into reviewers · producer primed by blockers + cited files
only.

## State & resumption

Persist three things so the run survives compaction: the brainstormed
**change-spec**, the **plan**, and a **progress note** carrying a small RESUME block:

```
RESUME: phase=<E1'|E2'|S1..S8> worktree=<path> branch=<name> base_ref=<sha> ralph_round=<n> pre_squash_head=<sha>
```

(`pre_squash_head` is recorded once S7 runs, so an interrupted re-squash is detected
on resume.) **Where these live follows the user's / project's existing convention** —
honor CLAUDE.md preferences and existing repo patterns. The command imposes no fixed
path (do not assume `dev-docs/`) and no gitignore-vs-commit policy.

**Resume contract:** on resume, reconcile worktree/branch/base_ref existence first,
then continue from `phase`; an interrupted review round is re-run from scratch
(re-dispatch the whole frozen panel — bounded, idempotent), so only `ralph_round`
need be persisted to locate the loop.
