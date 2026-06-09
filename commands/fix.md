---
description: "Autonomous feedback loop: find the existing autopilot branch, brainstorm your review feedback into a change-spec, then plan → implement → verify → review → re-squash. Updates a review-ready branch; never merges. Explicit-only."
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

**Load config (run first, every run):** run `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. The `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}'` prefix is **required**: Claude Code inline-substitutes the value into the command text but does *not* export it to the bash subprocess, so the script only receives it when forwarded explicitly (otherwise it uses its fallback dir). It creates `${CLAUDE_PLUGIN_DATA}/config.json` with defaults if absent and prints the effective config. Note `ralphLoop.enabled` and the per-phase caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase` for the S1/S5 Ralph loop. User edits to that file take effect on the next run.

Before E1′, confirm the **superpowers** plugin is available — its skills must appear
in your skill list (brainstorming, writing-plans, subagent-driven-development,
verification-before-completion, finishing-a-development-branch,
dispatching-parallel-agents). This whole pipeline is built on them, and Claude Code
has no plugin auto-dependency mechanism, so this preflight is the safety net.

If superpowers is **not** available, STOP with a handoff (not a question): tell the
user it is required and how to install it —
`/plugin install superpowers@claude-plugins-official` — and to re-run `/autopilot:fix` after.
(`planning-with-files` is optional.)

`ralph-loop` is required only when `ralphLoop.enabled` is `true` in
`${CLAUDE_PLUGIN_DATA}/config.json`; otherwise it is not needed.

## Operating disciplines

- **Autonomous — never ask the user.** At a decision point, **convene the expert
  council** (see "Deciding at decision points (expert council)") to deliberate, then
  decide + record; trivial vagueness → decide + record solo. Only the safety stops
  interrupt the run.
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never
  hoard whole files, diffs, or logs in the main thread. Read only bounded slices
  when you must inspect something yourself.
- **Disk-backed.** Persist the change-spec and a **plan doc** (implementation plan +
  progress section + a RESUME block) so the run survives compaction. Location follows the
  user's/project's convention — see **State & resumption**.
- **A STOP is a handoff, never a question:** emit current state + the exact next
  step a human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

## Resume first

Look for an existing **plan doc** with a RESUME block in the project's convention
location. If found: reconcile worktree/branch/base_ref existence on disk, then
continue from `phase` (an interrupted review round re-runs whole). **If none, that
is the normal first run → go to E1′ (locate); never create a branch.**

## Selecting & dispatching the review panel

The S1/S5 panels are **selected by script** from the installed roster, then composed
and dispatched natively. Requires the installed plugin **≥0.3.0** (ships `agents/`).

- **Select.** Run the selector for the phase:
  - S1 → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py" --phase spec --spec-file <change-spec doc>`
  - S5 → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py" --phase work --worktree <worktree> --base <base_ref>`
  It returns JSON with a `selected` list of `{agent, subagent_type, tier, matched}`.
- **Compose the panel:** ALL returned `core` agents (mandatory floor) + the
  `optional` agents the orchestrator judges relevant (it may drop a marginal
  optional) + any **ad-hoc** inline lens for a genuine gap no roster agent covers.
- **Freeze & log** the composed panel to the **plan doc** (progress section): which core (all), which
  optionals included/excluded + why, any ad-hoc added. Reuse the frozen panel every
  round of that phase.
- **Dispatch the whole round's panel in one parallel batch** — issue every `Task` call together in a single message (`superpowers:dispatching-parallel-agents`), never one at a time. This applies to **every** review round in both S1 and S5 (including re-review rounds — whatever subset of lenses a round dispatches, send them together). Parallel dispatch is the intended efficiency; reviewers are independent and read-only.
  - *Roster member:* `Task(subagent_type="autopilot:<name>", …)` — the agent's body
    is its system prompt (persona/contract/checklist/verdict already loaded); pass
    ONLY the run inputs: "PHASE=<spec|work>. Inputs: worktree=…, base_ref=…,
    requirement=…, focus=…. Return ONLY the verdict block." It runs at its own
    `model` and read-only `tools` allowlist (read-only genuinely enforced;
    cost-tiering automatic).
  - *Ad-hoc member:* `general-purpose` with an inline persona (the pre-existing
    pattern), same verdict contract — for a gap no roster agent covers.
- **Collect verdicts → the existing Ralph loop** (unchanged: round-0 short-circuit,
  re-dispatch only FAILed/touched, cap, convergence from on-disk verdicts).

## Deciding at decision points (expert council)

At a **decision point**, the orchestrator **convenes an expert council**: a small team
(2–4) of **ad-hoc expert sub-agents** (personas derived from the decision's domain),
dispatched in **one parallel batch** via `superpowers:dispatching-parallel-agents`. Each
returns a **concise position** (recommendation + rationale + key trade-offs + any
dissent). The **orchestrator then synthesizes, decides, and records** the decision + the
council's key points (incl. dissent) in the spec/findings/progress. The orchestrator is
the decider; the council informs it. Never ask the user.

**Council members are advisors, not reviewers** — they give recommendations, NOT the
`VERDICT/BLOCKING/NON-BLOCKING` grammar (that's the review panel). Bounded: 2–4,
parallel, by-reference, no superpowers skills, concise positions.

**Convene when ANY of:**
- two or more **viable approaches with materially different trade-offs** exist;
- the choice **shapes architecture / data model / public interface / scope**;
- the choice is **costly to reverse** once baked in;
- it is a genuine fork a later review loop **might not catch**.

**Decide solo + record when:**
- there is a **single obvious default**, or project convention dictates the answer;
- the choice is **cosmetic / local / easily reversible**;
- a wrong guess would simply be **caught by S1/S5**.

**Examples.** Council: "which storage model / API shape / module boundaries?",
"reconcile two conflicting requirements", "pick between two non-trivial strategies".
Solo: "name a variable", "pick a file path under convention", "fill an obvious default
for a low-stakes detail".

**Single-persona fallback:** if a decision admits fewer than two distinct lenses, use a
smaller council or decide solo with recorded rationale — don't fabricate personas to hit
a count.

**Dissent / split handling:** the orchestrator rules and records *why*; a minority
position is logged as "considered, not adopted"; the orchestrator breaks ties (it is the
decider).

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
  itself: each round, dispatch the frozen panel fresh **in parallel (all that round's members in one batch)** and collect verdicts to disk;
  round-0 all-PASS short-circuits; advance on all-PASS with no open BLOCKING, else
  apply fixes and re-dispatch; cap = `maxIterations.spec-phase` (S1) /
  `maxIterations.implementation-phase` (S5), default 3.
- **`enabled: true` — ralph-loop plugin.** Drive the phase with one
  `/ralph-loop:ralph-loop` whose looped prompt is ONE round and whose
  completion-promise is the phase marker:
  - **S1** → `/ralph-loop:ralph-loop "Run ONE spec-review round: dispatch the frozen S1 panel fresh (read the spec doc); write each VERDICT to the plan doc. If every lens is PASS with no open BLOCKING, print exactly 'AUTOPILOT: SPEC READY'; otherwise edit the spec to resolve every BLOCKING item and do NOT print the marker." --max-iterations <maxIterations.spec-phase> --completion-promise "AUTOPILOT: SPEC READY"`
  - **S5** → `/ralph-loop:ralph-loop "Run ONE work-review round: dispatch the frozen S5 panel fresh against the diff (git diff base_ref...HEAD); write each VERDICT. If every lens is PASS with no open BLOCKING, print exactly 'AUTOPILOT: WORK READY'; otherwise dispatch ONE producer subagent to fix every BLOCKING item, then do NOT print the marker." --max-iterations <maxIterations.implementation-phase> --completion-promise "AUTOPILOT: WORK READY"`

Both drivers obey the same rules: a fresh panel each round; convergence is decided
from the on-disk verdicts (the marker is printed ONLY when convergence is genuinely
true — never to escape the loop); on the marker the phase is done and the command
proceeds (S1→S2, S5→S6); if the per-phase cap (`maxIterations.spec-phase` /
`.implementation-phase`, default 3) is hit WITHOUT the marker → non-convergence STOP
with the 3-way classification (oscillation | unfixable | requirements-conflict) and
a handoff — do not proceed.

## Pipeline (E1′, E2′, S1–S7)

Legend: **E#** = entry phase (command-specific; `′` = fix variant); **S#** = shared
spine (common to build & fix).

- **E1′ — locate the existing branch (no new worktree).** Find the target autopilot
  branch: read the project's **plan doc** (RESUME block) if present; else the most recent
  `autopilot/*` branch. **If none → STOP** ("no autopilot branch found — run
  `/autopilot:build <requirements>` first"). Never create a new branch. E1′ **reuses
  the existing plan doc if present, else creates one.**
  - **Worktree:** use the branch's existing worktree; if it was removed, check the
    branch out in place — never create a second worktree for it.
  - **base_ref:** reuse the value in that branch's **plan doc** RESUME block if present; else
    `git merge-base main autopilot/<slug>` (default branch = `main` unless the repo
    says otherwise). Record worktree/branch/base_ref.
  - **Dirty tree:** if the worktree has uncommitted changes, STOP with a handoff
    (commit or stash first) so they aren't folded into the re-squash — unless Auto
    Mode is on (then proceed, deferring to Auto Mode).
- **E2′ — brainstorm the feedback.** Use `superpowers:brainstorming` on `$ARGUMENTS`
  (the feedback) → write a **change-spec** appended to the existing spec doc (the
  original spec stays as context). At decision points, convene the expert council (see
  "Deciding at decision points (expert council)") to discuss and decide; record the
  decision + rationale. (Trivial defaults: decide + record.)
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
- **S2 — plan the delta.** Use `superpowers:writing-plans` → write the implementation
  plan for the change into the **plan doc** (separate from the change-spec), appended
  under a change-scoped heading; record how the work will be verified. On a consequential
  plan fork → convene the expert council (see "Deciding at decision points (expert
  council)") to decide.
- **S3 — produce.** Code → `superpowers:subagent-driven-development` (it may commit
  per task and run its own task-level review — that is fine; S5 is the authoritative
  gate and the S6 re-squash folds its commits). Non-code → producer subagents via
  the same dispatch pattern. The orchestrator never edits the work product itself.
- **S4 — verify.** Use `superpowers:verification-before-completion`: run the
  discovered checks. For THIS plugin = `claude plugin validate` + the documented
  manual smoke. Cap fixes at 3; never weaken, skip, or delete a check; a drop in the
  check count → STOP.
- **S5 — work review (Ralph loop).** Panel derived from the **delta diff**
  (`git diff --name-only base_ref...HEAD`); reviewers run a path-scoped diff. Run the
  **S5 Ralph loop** (above) over the work. The core `doc-reviewer` is always in the
  S5 panel and now gates docs: stale / missing / contradictory docs = BLOCKING (the
  S5 producer fix updates them); bloat = NON-BLOCKING. **Fixes:** ONE fresh producer
  subagent primed with the deduped open blockers + cited files only. On convergence
  it records `AUTOPILOT: WORK READY`.
- **S6 — re-squash.** Squash the branch back to **one** clean commit (fold the new
  feedback commits into the existing single commit). Local, unpushed history rewrite
  **within the branch's own commits** — permitted by the destructive-op stop (and
  skipped under Auto Mode). Idempotent: if already exactly 1 ahead of base_ref, skip.
  Record the pre-squash HEAD SHA in the RESUME block so an interrupted re-squash is
  detected on resume.
- **S7 — finish (no merge).** Use `superpowers:finishing-a-development-branch` →
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
only · expert councils bounded (2–4), convened only at genuine decision points, in one
parallel batch.

## State & resumption

Persist two things so the run survives compaction: the brainstormed
**change-spec** and the **plan doc** (implementation plan + progress section, carrying a small RESUME block):

```
RESUME: phase=<E1'|E2'|S1..S7> worktree=<path> branch=<name> base_ref=<sha> ralph_round=<n> pre_squash_head=<sha>
```

(`pre_squash_head` is recorded once **S6** runs, so an interrupted re-squash is detected
on resume.)

**Keep RESUME current:** rewrite the RESUME block at every phase transition — update `phase=` as you advance (E1′→E2′→S1…→S7), `ralph_round=` each loop iteration, and `pre_squash_head=` once the squash runs; the resume contract depends on RESUME reflecting the true current phase, and a stale `phase=` breaks resumption.

**Where these live follows the user's / project's existing convention** —
honor CLAUDE.md preferences and existing repo patterns. The command imposes no fixed
path (do not assume `dev-docs/`) and no gitignore-vs-commit policy.

**Resume contract:** on resume, reconcile worktree/branch/base_ref existence first,
then continue from `phase`; an interrupted review round is re-run from scratch
(re-dispatch the whole frozen panel — bounded, idempotent), so only `ralph_round`
need be persisted to locate the loop.
