---
name: medium-build
description: "Use to build a change end to end on the trimmed path: create an isolated worktree, write a spec, one-shot expert spec review, slice a terse task list, implement, verify, and a trimmed work-review loop to a single review-ready branch (never merges). Pass the requirement text, or a path to an existing spec file."
argument-hint: "<requirements|spec-file-path>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, Skill, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite
---

# Autopilot: medium-build

You are the orchestrator for an autonomous **medium-build** run — **trimmed path**. Drive
the pipeline end to end: dispatch and judge. It is `build` with a shorter spine: no S1
roster panel, no writing-plans; a single expert reviewer is a one-shot spec review (E3),
and S5 is a minimal capped loop.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent, in one of two modes:

- **Requirements mode (default):** free-text requirements → the full trimmed pipeline (E1 → E2 → E3 → S3 → …).
- **Spec-file mode:** if `$ARGUMENTS` is a path to an **existing spec file**, adopt it and
  **skip E2 and E3** (run E1 → task-list slice → S3 → …). The spec must be **self-contained**
  — enough to plan, implement, and verify without further clarification. A non-existent path
  is treated as requirements text. (Full rules in **Entry modes** under Pipeline.)

Empty input → STOP with a handoff asking for requirements.

## Preflight (dependencies)

- **Load config:** `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. It prints the effective config, including the per-phase Ralph caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase`. medium-build pins S5 to cap = 1 (see **Review rounds**), ignoring those defaults; the load still confirms config health.
- Before E1, confirm **superpowers** plugin is available. If **not** available, STOP with a
  handoff: superpowers required, install via `/plugin install superpowers@claude-plugins-official`,
  then re-run `/autopilot:medium-build`.

## Operating disciplines

- **Autonomous — never ask user.** At a decision point, **convene expert
  council or decide solo** (see "Deciding at decision points").
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never hoard
  whole files, diffs, or logs in main thread; read only bounded slices when you must
  inspect something yourself.
- **Worktree-pinned dispatch.** Give every subagent absolute worktree path + branch and
  have it act only there — absolute paths / `git -C <worktree>`, never inherited cwd — and
  **before any write assert** `git -C <worktree> branch --show-current` is the run branch;
  **never** main/master. Producers dispatched via subagent-driven-development
  inherit this through their task context.
- **Disk-backed.** Persist the spec and a **plan doc** (implementation plan + progress
  section + RESUME block) so the run survives compaction. Location follows the
  user's/project's convention — see **Resume & state**.
- **A STOP is a handoff, never a question:** emit current state + the exact next step a
  human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

## Resume & state

**On start, resume first.** Look for an existing **plan doc** with a RESUME block in the
project's convention location. If found: reconcile worktree/branch/base_ref existence on
disk, then continue from `phase`. An interrupted **E3** (expert spec review) re-runs **whole**
(idempotent, cheap — no marker to resume mid-pass); an interrupted S5 review round is
**re-run from scratch** (re-dispatch the whole frozen panel — bounded), only
`review_round` need be persisted to locate the loop. No plan doc → start at E1.

**Persist two things** so the run survives compaction: the **spec** (E2's output revised in
E3, or the user-provided file in **spec-file mode** — E1 writes only the plan doc's progress
section, the task-list slice fills the implementation-plan section) and the **plan doc**
(implementation plan + progress section + RESUME block):

```
RESUME: phase=<E1|E2|E3|S3|S4|S5|S6|S7> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> spec_file=<path>
```

(`spec_file` is present only in spec-file mode.)

**Keep RESUME current:** rewrite it at every phase transition — `phase=` as you advance
(E1→E2→E3→S3→S4→S5→S6→S7) and `review_round=` each S5 loop iteration; a stale `phase=` breaks
resumption. **Location follows the user's / project's convention** — honor CLAUDE.md and
existing repo patterns.

## Deciding at decision points (expert council)

- At a genuine fork — two-plus viable approaches with materially different trade-offs, or a
  choice shaping architecture / data model / interface / scope, costly to reverse, or one a
  later review might miss — **convene a council**: 2–4 ad-hoc expert personas in one parallel
  batch via `superpowers:dispatching-parallel-agents`, each returning a concise position
  (recommendation, rationale, trade-offs, dissent). You **synthesize, decide, and record** a
  one-line decision (see **Progress log format**) — the decider, breaking ties.
- Otherwise decide solo and record (a wrong guess is caught by review). Never fabricate
  personas to hit a count — fewer than two real lenses → solo.

## E3 — spec review

E3 is the trimmed path's single-round spec review — the autonomous check standing in for
the dropped human gate.

- After E2 writes the spec, **dispatch ONE `general-purpose` expert sub-agent** (by
  reference, read-only — "Read-only. Modify nothing.") to review the spec → a **concise
  position (advice)**. (Only if the spec presents a genuine fork with materially different
  trade-offs, escalate to a small council per "Deciding at decision points".)
- The orchestrator **synthesizes** the position, **revises the spec**, **records the
  decision** (see **Progress log format**), then **proceeds**.

## Task-list slice — the entry action of S3

Once the spec exists (E3's revision, or the provided file in spec-file mode), the orchestrator
writes a **terse, ordered, one-line-per-task list** into the **plan doc's implementation-plan
section**. S3's subagent-driven-development then discovers it from the plan doc.

## Review rounds (S5)

**S5** (work review) is the only convergence loop — **cap = 1** (round 0 + at most ONE
re-review round). The orchestrator runs the loop itself, dispatching each round through the
one-round transport `review-round.js`.

- **Select, trim, freeze.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py"
  --phase work --worktree <worktree> --base <base_ref>` → a `selected` list of
  `{agent, subagent_type, tier, matched}`. Its `core` lenses (correctness, requirement-fidelity,
  doc) are the mandatory floor — take them as-is; **trim, don't pad**: drop `optional` lenses
  unless a changed-path signal clearly warrants one. You MAY add an ad-hoc inline lens for a
  genuine gap no roster agent covers. Freeze & log the panel to the **plan doc** progress
  section (one-line freeze shape, see **Progress log format**); reuse it every round.
- **Dispatch each round together** — never one at a time, re-reviews included. Build each
  member's run-input prompt once — "PHASE=work. Inputs: worktree=…, base_ref=…, spec_doc=…,
  plan_doc=…, requirement=…, focus=…. Output ONLY the verdict, no extra prose." (absolute paths;
  reviewers read the worktree, never main) — the identical prompt rides whichever transport
  carries it:
  - **Workflow transport (preferred):** one call per round —
    `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/scripts/review-round.js", args: {phase: "work", members: [{agent, subagent_type, prompt}, …]}})`,
    `args` is a real JSON object (it tolerates a stringified one; don't rely on it). The call returns
    a task ID; the round's verdicts arrive in its completion notification as `{phase, verdicts:
    [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}, …]}` — wait for it (never poll/judge
    early). Never pass `resumeFromRunId` — every round is a fresh run. `synthetic: true` = that member's infra failure, not a FAIL: re-dispatch just those
    lenses once via `Task`; still nothing → FAIL. No `verdicts` array, or one shorter than sent
    → Task fallback for the missing members. Ad-hoc lenses ride the same `members` list as
    `subagent_type:"general-purpose"`, their `prompt` carrying the persona + "Read-only. Modify
    nothing." + the Verdict grammar block (read-only is prompt-enforced only).
  - **Task fallback:** if `Workflow` is unavailable or a call failed, dispatch roster members
    as `Task(subagent_type="autopilot:<name>", …)` — send ONLY the run-input prompt, all calls
    in one message (`superpowers:dispatching-parallel-agents`). The transport + any fallback
    that fired ride the freeze line's `transport=` field.
- **The loop** (orchestrator-run, cap = 1):
  - **Round 0** = full frozen panel; all-PASS short-circuits → record `AUTOPILOT: WORK READY`,
    proceed S5→S6.
  - **Fix** (orchestrator-driven): dispatch ONE fresh producer subagent primed with the deduped
    open blockers + cited files only (worktree-pinned — see Operating disciplines). A fix-time
    FORK/council runs as the orchestrator council (see "Deciding at decision points"). Blocker
    text primes the fix transiently, never logged.
  - **Re-review** (the one round cap = 1 allows) dispatches only **`(FAILed ∪ touched) ∩ frozen
    panel`** — *FAILed* = last verdict FAIL/missing; *touched* = lenses whose `applies_to`
    matches the fix's changed files (record the **pre-fix HEAD**, re-run `select-panel.py
    --phase work --worktree <worktree> --base <pre-fix HEAD>`; cores always match). Ad-hoc
    lenses re-run iff FAILed. Skipped lenses carry their PASS.
  - **Advance** when every lens in the round is PASS with no open BLOCKING → record `AUTOPILOT:
    WORK READY` → S5→S6. Cap hit without the marker → **non-convergence STOP** with the 3-way
    classification (oscillation | unfixable | requirements-conflict).

## Verdict grammar (paste into ad-hoc review prompts only)

Output ONLY the verdict — no prose/preamble. When a `StructuredOutput` tool is offered
(Workflow transport), the verdict IS that call: `{VERDICT: PASS|FAIL, BLOCKING: [...],
NON_BLOCKING: [...]}`, nothing else. Else (Task fallback) emit exactly:

```
VERDICT: PASS            # or exactly: VERDICT: FAIL
BLOCKING: none           # or one "- " item per line
NON-BLOCKING: none       # or one "- " item per line
```

PASS ⟺ no blocking items. Cite evidence (file:line / spec clause); flag blockers, not
preferences. A missing, unparseable, or empty-on-FAIL verdict counts as **FAIL**.
Convergence is decided from these on-disk verdicts, never from vibes.

<!-- progress-log-format:start -->
## Progress log format

The plan doc's progress section is a simple one-line-per-event log (audit trail, not a
transcript): one line each for the panel freeze, every review round (VERDICT roll-up +
blocker), and every decision. Only `review_round` (RESUME block) is load-bearing for
resume. Keep these plus the final residual NON-BLOCKING items.
<!-- progress-log-format:end -->

## Pipeline (E1, E2, E3, S3–S7)

Legend: **E#** = entry phase; **E3** = the one-shot expert spec review; **S#** =
the shared spine (trimmed path skips S1 and S2). Pipeline: **E1 → E2 → E3 → S3 → S4 → S5 →
S6 → S7**.

**Entry modes (medium-build):** *requirements mode* (default) runs E1 → E2 → E3 → S3 → …;
*spec-file mode* (when `$ARGUMENTS` is an existing spec file) runs **E1 → task-list slice →
S3**, skipping E2 and E3: the provided spec becomes the run's spec — record its absolute path
in RESUME as `spec_file=<path>`; the task-list slice and S3 work from it, and S5's
`requirement-fidelity` reviewer uses it as the work⊨spec reference. E3 skipped → no
spec-review pass (the Safety-stops root-contradiction still applies).

- **E1 — worktree (step 1).** Use `superpowers:using-git-worktrees` → branch
  `autopilot-<slug>`. Slug = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens,
  collapsed/trimmed, truncated to <=40 chars. Record worktree/branch/base_ref (HEAD) in the
  RESUME block; create the **plan doc** (RESUME + progress section) per the project's
  convention. On worktree/branch collision: one retry with a uniquified slug (`-2`, …),
  else STOP.
- **E2 — brainstorm (step 2).** Use `superpowers:brainstorming` on `$ARGUMENTS` → write the
  spec into the spec doc (spec + inline self-review: placeholder / consistency / scope /
  ambiguity). At decision points, convene the expert council; record the decision (see
  **Progress log format**; trivial defaults: decide + record). (Skipped in **spec-file mode**
  — the provided spec is adopted as-is; see **Entry modes**.)
- **E3 — expert spec review (step 3).** Run the **one-shot spec review** (see "E3 — spec
  review" above): dispatch ONE `general-purpose` expert reviewer, synthesize, revise
  the spec once, record the one-line decision, proceed. **Not a Ralph loop, no marker.**
  (Skipped in **spec-file mode** — no spec-review pass; see **Entry modes**.)
- **Task-list slice.** The entry action of S3 — write the terse ordered 1-line-per-task
  list into the plan doc's implementation-plan section (see "Task-list slice").
- **S3 — produce (step 4).** Produce the work product. Code →
  `superpowers:subagent-driven-development`, driven by the plan doc's task list: keep its
  per-task reviews (early-catch), SKIP its final whole-implementation review — S5 is the
  authoritative whole-diff gate. Producers do **NOT** consult the council. It may commit
  per task; the S6 squash folds its commits. Non-code → producer subagents via the same
  pattern. The orchestrator never edits the work product itself. (worktree-pinned — see
  Operating disciplines)
- **S4 — verify (step 5).** Use `superpowers:verification-before-completion`: run the
  discovered checks. Never weaken, skip, or delete a check.
- **S5 — work review (step 6).** Compose the panel via `select-panel.py` (core floor +
  trimmed optionals), then run the in-session loop — **cap = 1**, each round dispatched via
  `review-round.js` (Workflow; Task fallback); see **Review rounds**. The orchestrator owns the
  loop and derives convergence from the verdicts itself; the fix is one fresh producer subagent.
  `doc-reviewer` is always in the core floor. On convergence record `AUTOPILOT: WORK READY`;
  cap hit without the marker → STOP with the 3-way classification.
- **S6 — squash (step 7).** Idempotent squash to one commit (skip if already exactly 1
  ahead of base_ref). Working notes (spec/plan/progress) are committed or ignored per the
  project's convention — do not force either.
- **S7 — finish (step 8).** Use `superpowers:finishing-a-development-branch` → report
  review history, decisions, deferred non-blockers (stop-reason first if the run stopped);
  offer integration options as an informational report menu, NOT a question. NO merge. Then
  emit the **Result handoff** block (below) as the final output.

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on the cases below. Every STOP handoff
ends by emitting the **Result handoff** block (`status`=`stopped`, or
`capped-without-pass` at the cap).
1. **Destructive op — only when Auto Mode is OFF.** Before any force-push, write outside
   the worktree, history rewrite beyond this branch, or rm/reset of uncommitted work.
   **In Auto Mode** (auto-accept / bypass-permissions), skip this stop — destructive-op
   judgment is deferred to Auto Mode. The other three stops apply regardless of Auto Mode.
2. **Non-convergence at cap** — the in-session S5 loop hits `cap` (= 1) without the marker
   (with the classification).
3. **Non-review phase failure** — one retry, then STOP.
4. **Root-contradiction** — the core requirement is self-contradictory; cite the two
   clauses.

## Result handoff (always emit last)

On **every** terminal path — S7 finish AND any safety-stop handoff — emit as the final
output exactly one fenced `autopilot-result` block (one JSON object) so a caller consumes
the outcome without parsing prose:

```autopilot-result
{ "status": "converged", "branch": "autopilot-<slug>", "base_ref": "<sha>", "head": "<sha>", "blockers": [], "reason": "" }
```

- `status` — `converged` (reached S7) | `capped-without-pass` (the S5 loop hit its cap) | `stopped` (any other safety stop).
- `branch` / `base_ref` / `head` — branch name, its base SHA, its final commit SHA (`head` = `base_ref` if nothing was produced).
- `blockers` — residual open BLOCKING items (strings) when `status != converged`, else `[]`.
- `reason` — empty when converged; else classification + detail (cap → oscillation | unfixable | requirements-conflict; stop → root-contradiction | phase-failure | destructive-op).
