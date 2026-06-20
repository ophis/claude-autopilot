---
name: medium-build
description: "Trimmed autopilot build path: spec + a one-shot expert spec review (no roster panel), no writing-plans, and a cap-1 work-review loop, to a single review-ready branch (never merges). Use for a lighter-than-build / trimmed build. Pass the requirement text, or a path to an existing spec file."
argument-hint: "<requirements|spec-file-path>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, Skill, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite
---

# Autopilot: medium-build

You are the orchestrator for an autonomous **medium-build** run — **trimmed path**. Drive
the pipeline end to end: dispatch and judge. It is `build` with a shorter spine: no S3
roster panel, no writing-plans; a single expert reviewer is a one-shot spec review (S3'),
and S7 is a minimal capped loop.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent, in one of two modes:

- **Requirements mode (default):** free-text requirements → the full trimmed pipeline (S1 → S2 → S3' → S5 → …).
- **Spec-file mode:** if `$ARGUMENTS` is a path to an **existing spec file**, adopt it and
  **skip S2 and S3'** (run S1 → task-list slice → S5 → …). The spec must be **self-contained**
  — enough to plan, implement, and verify without further clarification. A non-existent path
  is treated as requirements text. (Full rules in **Entry modes** under Pipeline.)

Empty input → STOP with a handoff asking for requirements.

## Preflight (dependencies)

- **Read `${CLAUDE_PLUGIN_ROOT}/references/autopilot-common.md`** — the shared operating protocol (disciplines, dispatch transport, verdict grammar, progress-log shapes, safety stops, result handoff). This skill defines only its pipeline + the deltas below.
- **Load config:** `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. It prints the effective config, including the per-phase Ralph caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase`. medium-build pins S7 to cap = 1 (see **Review rounds**), ignoring those defaults; the load still confirms config health.
- Before S1, confirm **superpowers** plugin is available. If **not** available, STOP with a
  handoff: superpowers required, install via `/plugin install superpowers@claude-plugins-official`,
  then re-run `/autopilot:medium-build`.

## Operating disciplines

The 5 shared disciplines (Autonomous · Thin orchestrator · Worktree-pinned dispatch ·
STOP-is-a-handoff · No merge) → see **references/autopilot-common.md §C1**. medium-specific
additions:

- **Worktree-pinned dispatch (medium delta):** producers dispatched via
  subagent-driven-development inherit the worktree-pin through their task context.
- **Disk-backed.** Persist the spec and a **plan doc** (implementation plan + progress
  section + RESUME block) so the run survives compaction. Location follows the
  user's/project's convention — see **Resume & state**.

## Resume & state

**On start, resume first.** Look for an existing **plan doc** with a RESUME block in the
project's convention location. If found: reconcile worktree/branch/base_ref existence on
disk, then continue from `phase`. An interrupted **S3'** (expert spec review) re-runs **whole**
(idempotent, cheap — nothing to resume mid-pass); an interrupted S7 review round is
**re-run from scratch** (re-dispatch the whole frozen panel — bounded), only
`review_round` need be persisted to locate the loop. No plan doc → start at S1.

**Persist two things** so the run survives compaction: the **spec** (S2's output revised in
S3', or the user-provided file in **spec-file mode** — S1 writes only the plan doc's progress
section, the task-list slice fills the implementation-plan section) and the **plan doc**
(implementation plan + progress section + RESUME block):

```
RESUME: phase=<S1|S2|S3'|S5|S6|S7|S8|S9> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> spec_file=<path>
```

(`spec_file` is present only in spec-file mode.)

**Keep RESUME current:** rewrite it at every phase transition — `phase=` as you advance
(S1→S2→S3'→S5→S6→S7→S8→S9; spec-file mode advances S1→S5) and `review_round=` each S7 loop
iteration; a stale `phase=` breaks
resumption. **Location follows the user's / project's convention** — honor CLAUDE.md and
existing repo patterns.

## Deciding at decision points (expert council)

→ see **references/autopilot-common.md §C2 Deciding at decision points**.

## S3' — spec review

S3' is the trimmed path's single-round spec review — the autonomous check standing in for
the dropped human gate.

- After S2 writes the spec, **dispatch ONE `general-purpose` expert sub-agent** (by
  reference, read-only — "Read-only. Modify nothing.") to review the spec → a **concise
  position (advice)**. (Only if the spec presents a genuine fork with materially different
  trade-offs, escalate to a small council per "Deciding at decision points".)
- The orchestrator **synthesizes** the position, **revises the spec**, **records the
  decision** (see **Progress log format**), then **proceeds**.

## Task-list slice — the entry action of S5

Once the spec exists (the S3' revision, or the provided file in spec-file mode), the orchestrator
writes a **terse, ordered, one-line-per-task list** into the **plan doc's implementation-plan
section**. S5's subagent-driven-development then discovers it from the plan doc.

## Review rounds (S7)

**S7** (work review) is the only convergence loop — **cap = 1** (round 0 + at most ONE
re-review round). The orchestrator runs the loop itself, dispatching each round through the
one-round transport `review-round.js`.

- **Select, trim, freeze.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py"
  --phase work --worktree <worktree> --base <base_ref>` → a `selected` list of
  `{agent, subagent_type, tier, matched}`. Its `core` lenses (correctness, requirement-fidelity,
  doc) are the mandatory floor — take them as-is; **trim, don't pad**: drop `optional` lenses
  unless a changed-path signal clearly warrants one. You MAY add an ad-hoc inline lens for a
  genuine gap no roster agent covers. Freeze & log the panel to the **plan doc** progress
  section (freeze shape, see **Progress log format**); reuse it every round.
- **Dispatch each round together** — never one at a time, re-reviews included. Transport
  mechanics (Workflow-preferred / Task-fallback / `synthetic` / partial-result) →
  **references/autopilot-common.md §C3 Dispatch transport**. Ad-hoc lenses ride the same
  `members` list as `subagent_type:"general-purpose"`, their `prompt` carrying the persona +
  "Read-only. Modify nothing." + the Verdict grammar block (read-only is prompt-enforced only).
- **The loop** (orchestrator-run, cap = 1):
  - **Round 0** = full frozen panel; all-PASS short-circuits → proceed S7→S8.
  - **Fix** (orchestrator-driven): dispatch ONE fresh producer subagent primed with the deduped
    open blockers + cited files only (worktree-pinned — see Operating disciplines). A fix-time
    FORK/council runs as the orchestrator council (see "Deciding at decision points"). Full
    blocker text primes the fix transiently; logged only as a concise gist.
  - **Re-review** (the one round cap = 1 allows) dispatches only **`(FAILed ∪ touched) ∩ frozen
    panel`** — *FAILed* = last verdict FAIL/missing; *touched* = lenses whose `applies_to`
    matches the fix's changed files (record the **pre-fix HEAD**, re-run `select-panel.py
    --phase work --worktree <worktree> --base <pre-fix HEAD>`; cores always match). Ad-hoc
    lenses re-run iff FAILed. Skipped lenses carry their PASS.
  - **Advance** when every lens in the round is PASS with no open BLOCKING → S7→S8. Cap hit
    without convergence → **non-convergence STOP** with the 3-way
    classification (oscillation | unfixable | requirements-conflict).

## Verdict grammar (paste into ad-hoc review prompts only)

→ see **references/autopilot-common.md §C4 Verdict grammar**.

<!-- progress-log-format:start -->
## Progress log format

The plan doc's progress section is the audit-trail log. The audit-trail principle + the
**review-round** and **decision** shapes → see **references/autopilot-common.md §C5 Progress /
working-note shapes** (`S3'` decisions use the **Decision** shape). medium records the freeze in
the **plan doc** progress section, using the freeze shape:
- **Panel freeze:** `S7 panel: core=[correctness,requirement-fidelity,doc] +optional=[code-quality] transport=Workflow` (append `->Task` only if the fallback fired).
<!-- progress-log-format:end -->

## Pipeline (S1, S2, S3', S5–S9)

Legend: **S#** = build's step S# (numbering shared with `build`); **S3'** = the one-shot
expert spec review replacing build's S3 roster loop. Pipeline: **S1 → S2 → S3' → S5 → S6 →
S7 → S8 → S9** (no S4 — medium skips the plan phase).

**Entry modes:**
- *requirements mode* (default) runs S1 → S2 → S3' → S5 → …;
- *spec-file mode* (when `$ARGUMENTS` is an existing spec file) runs **S1 → task-list slice →
  S5**, skipping S2 and S3': the provided spec becomes the run's spec — record its absolute path
  in RESUME as `spec_file=<path>`; the task-list slice and S5 work from it, and S7's
  `requirement-fidelity` reviewer uses it as the work⊨spec reference. S3' skipped → no
  spec-review pass (the Safety-stops root-contradiction still applies).

**The pipeline**
- **S1 — worktree.**
  - If already in an isolated worktree (not on `main`/`master`), reuse it — do not nest another. `base_ref` is current local HEAD.
  - Else create worktree on local HEAD, then enter:
    - `<path>` = `.claude/worktrees/autopilot-<slug>`, ensure `.claude/worktrees/` is gitignored (add it to `.gitignore` if not)
    - `<slug>` = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens, collapsed to <=40 chars. On worktree/branch collision: retry with a uniquified slug (`-2`, …).
    - `git worktree add <path> -b autopilot-<slug> HEAD`
    - `EnterWorktree({path: <path>})`
  - Create the **plan doc** (with RESUME + progress section) at location per the project's convention. Record `worktree`, `branch`, and `base_ref` (HEAD) in the RESUME block.
- **S2 — brainstorm.** Use `superpowers:brainstorming` on `$ARGUMENTS` → write the
  spec into the spec doc (spec + inline self-review: placeholder / consistency / scope /
  ambiguity). At decision points, convene the expert council; record the decision (see
  **Progress log format**; trivial defaults: decide + record). (Skipped in **spec-file mode**
  — the provided spec is adopted as-is; see **Entry modes**.)
- **S3' — expert spec review.** Run the **one-shot spec review** (see "S3' — spec
  review" above). **Not a Ralph loop.** (Skipped in **spec-file mode** — no spec-review
  pass; see **Entry modes**.)
- **Task-list slice.** The entry action of S5 — write the terse ordered 1-line-per-task
  list into the plan doc's implementation-plan section (see "Task-list slice").
- **S5 — produce.** Produce the work product. Code →
  `superpowers:subagent-driven-development`, driven by the plan doc's task list: keep its
  per-task reviews (early-catch), SKIP its final whole-implementation review — S7 is the
  authoritative whole-diff gate. Producers do **NOT** consult the council. It may commit
  per task; the S8 squash folds its commits. Non-code → producer subagents via the same
  pattern. The orchestrator never edits the work product itself. (worktree-pinned — see
  Operating disciplines)
- **S6 — verify.** Use `superpowers:verification-before-completion`: run the
  discovered checks. Never weaken, skip, or delete a check.
- **S7 — work review.** Run the S7 review loop (see **Review rounds**) over the work;
  `doc-reviewer` is always in the core floor.
- **S8 — squash.** Idempotent squash to one commit (skip if already exactly 1
  ahead of `base_ref`). Working notes (spec/plan/progress) are committed or ignored per the
  project's convention — do not force either.
- **S9 — finish.** Inline (no skill): report
  review history, decisions, deferred non-blockers (stop-reason first if the run stopped);
  offer integration options as an informational report menu, NOT a question. NO merge. Then
  emit the **Result handoff** block (below) as the final output.

## Safety stops (handoffs, not questions)

→ see **references/autopilot-common.md §C6 Safety stops** (medium's cap-2 case is the
in-session S7 loop at `cap` = 1).

## Result handoff (always emit last)

→ emit the `autopilot-result` block per **references/autopilot-common.md §C7 Result handoff**
on every terminal path (S9 finish AND any safety-stop handoff).
