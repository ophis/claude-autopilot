---
name: build
description: "Full-rigor autopilot build path: brainstormed spec + a spec-review roster loop + a written plan + a work-review roster loop, to a single review-ready branch (never merges). Use for full / rigorous / roster-reviewed builds. Pass the requirement text, or a path to an existing spec file."
argument-hint: "<requirements|spec-file-path>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, Skill, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite, ScheduleWakeup
---

# Autopilot: build

You are the orchestrator for an autonomous build run. Drive the pipeline end to end:
dispatch and judge.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent, in one of two modes:

- **Requirements mode (default):** free-text requirements → full pipeline (S1 → S2 → S3 → S4 → …).
- **Spec-file mode:** if `$ARGUMENTS` is a path to an **existing spec
  file**, adopt it and **skip S2 and S3** (run S1 → S4 → …). The spec
  must be **self-contained** — enough to plan, implement, and verify without further
  clarification. A non-existent path is
  treated as requirements text. (Full rules in **Entry modes** under Pipeline.)

Empty input → STOP with a handoff asking for requirements.

## Preflight (dependencies)

- **Read `${CLAUDE_PLUGIN_ROOT}/references/autopilot-common.md`** — the shared operating protocol (disciplines, dispatch transport, verdict grammar, progress-log shapes, safety stops, result handoff). This skill defines only its pipeline + the deltas below.
- **Load config:** `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. It prints the effective config, including the per-phase Ralph caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase`.
- Before S1, confirm **superpowers** plugin is available. If **not** available, STOP with a
  handoff: superpowers required, install via `/plugin install superpowers@claude-plugins-official`,
  then re-run `/autopilot:build`.

## Operating disciplines

The 5 shared disciplines (Autonomous · Thin orchestrator · Worktree-pinned dispatch ·
STOP-is-a-handoff · No merge) → see **references/autopilot-common.md §C1**. Build-specific
additions:

- **Worktree-pinned dispatch (build delta):** producers dispatched via
  subagent-driven-development inherit the worktree-pin through their task context.
- **Disk-backed.** Persist the spec and a **plan doc** (implementation plan + progress
  section + RESUME block) so the run survives compaction. Location follows the
  user's/project's convention — see **Resume & state**.

## Resume & state

**On start, resume first.** Look for an existing **plan doc** with a RESUME block in the
project's convention location. If found: reconcile worktree/branch/base_ref existence on
disk, then continue from `phase`. An interrupted review round is **re-run from scratch**
(re-dispatch the whole frozen panel — bounded), only `review_round` need be
persisted to locate the loop. No plan doc → start at S1.

**Persist two things** so the run survives compaction: the **spec** (S2's output, or the
user-provided spec file) and the **plan doc** (implementation plan + progress section +
RESUME block):

```
RESUME: phase=<S1..S9> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> spec_file=<path>
```

**Keep RESUME current:** rewrite it at every
phase transition — `phase=` as you advance (S1→S2→S3…→S9; spec-file mode advances S1→S4),
`review_round=` each loop iteration; stale `phase=` breaks resumption. **Location follows
the user's / project's convention** — honor CLAUDE.md and existing repo patterns.

## Deciding at decision points (expert council)

→ see **references/autopilot-common.md §C2 Deciding at decision points**.

## Review rounds (S3 & S7)

- **Select & compose.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py"
  --phase spec --spec-file <spec doc>` (S3) / `... --phase work --worktree <worktree>
  --base <base_ref>` (S7) → a `selected` list of `{agent, subagent_type, tier, matched}`.
  The panel = ALL `core` agents (mandatory) + the `optional` agents you judge relevant (may
  drop marginal ones) + any ad-hoc inline lens for a genuine gap no roster agent covers.
- **Freeze & log** the composed panel to the **plan doc** progress section as the
  freeze shape (see **Progress log format**); reuse it every round of that phase.
- **Dispatch the whole round together** — never one at a time, re-reviews included. Transport
  mechanics (Workflow-preferred / Task-fallback / `synthetic` / partial-result) →
  **references/autopilot-common.md §C3 Dispatch transport**.
- **Ad-hoc members ride the SAME `members` list** as `subagent_type: "general-purpose"`,
  their `prompt` carrying the persona + "Read-only. Modify nothing." + the Verdict grammar
  block (call `StructuredOutput` when offered). Their read-only is **prompt-enforced
  only** (no tool allowlist), so the prompt MUST carry it. They follow the SAME dual fallback
  as roster: the whole-round Task fallback, and the per-member `synthetic` single Task
  re-dispatch — dispatch ad-hoc directly via `Task` only when the whole round already fell back.
- Each reviewer returns the verdict block; collect verdicts → the Ralph loop.

**S3** (spec review) and **S7** (work review) run the native **Ralph loop**
until the frozen panel PASSes, capped per phase by `ralphLoop.maxIterations.spec-phase` /
`.implementation-phase` (default 3, from config). Full blocker text primes the fix
transiently; logged only as a concise gist. Every reviewer is a fresh instance; convergence holds only when genuinely
all-PASS. The orchestrator runs the rounds itself, logging each briefly (see
**Progress log format**).

- **Round 0** = full frozen panel; all-PASS short-circuits.
- **Re-review (N>0):**
  - S3 stays full-panel.
  - S7 dispatches only **`(FAILed ∪ touched) ∩ frozen panel`** — *FAILed* = last verdict
    FAIL/missing; *touched* = lenses whose `applies_to` matches the fix's changed files
    (record the **pre-fix HEAD**, re-run `select-panel.py --phase work --worktree <worktree> --base <pre-fix HEAD>`; cores always match). Skipped lenses carry their PASS; `∪ touched`
    re-checks what a fix might regress.
  - Ad-hoc lenses re-run iff FAILed.
- **Advance** when every lens in the round is PASS with no open BLOCKING → proceed
  (S3→S4, S7→S8; spec-file mode starts at S4, no S3). Cap hit without convergence →
  non-convergence STOP (oscillation | unfixable | requirements-conflict) + handoff.

## Verdict grammar (paste into ad-hoc review prompts only)

→ see **references/autopilot-common.md §C4 Verdict grammar**.

<!-- progress-log-format:start -->
## Progress log format

The plan doc's progress section is the audit-trail log. The audit-trail principle + the
**review-round** and **decision** shapes → see **references/autopilot-common.md §C5 Progress /
working-note shapes** (`S3` rounds use the same shapes as `S7`). Build records the freeze in
the **plan doc** progress section, using the freeze shape:
- **Panel freeze:** `S7 panel: core=[correctness,requirement-fidelity,doc] +optional=[code-quality] transport=Workflow` (append `->Task` only if the fallback fired).
<!-- progress-log-format:end -->

## Pipeline (S1–S9)

**Entry modes:**
- *requirements mode* (default) runs S1 → S2 → S3 → S4 → …;
- *spec-file mode* runs **S1 → S4 → ...**, skipping
  S2 and S3: the provided spec becomes the run's spec — record its absolute path in RESUME
  as `spec_file=<path>`. S3 skipped.

**The pipeline**
- **S1 — worktree.**
  - If already in an isolated worktree (not on `main`/`master`), reuse it — do not nest another. `base_ref` is current local HEAD.
  - Else create worktree on local HEAD, then enter:
    - `<path>` = `.claude/worktrees/autopilot-<slug>`, ensure `.claude/worktrees/` is gitignored (add it to `.gitignore` if not)
    - `<slug>` = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens, collapsed to <=40 chars. On worktree/branch collision: retry with a uniquified slug (`-2`, …).
    - `git worktree add <path> -b autopilot-<slug> HEAD`
    - `EnterWorktree({path: <path>})`
  - Create the **plan doc** (with RESUME + progress section) at location per the project's convention. Record `worktree`, `branch`, and `base_ref` (HEAD) in the RESUME block.
- **S2 — brainstorm. (Skipped in spec-file mode)** Use `superpowers:brainstorming` on `$ARGUMENTS` → write the spec into the spec doc. At
  decision points, see **Deciding at decision points**; record the decision (see
  **Progress log format**).
- **S3 — spec review. (Skipped in spec-file mode)** Run the S3 review loop (see **Review rounds**) over the
  spec. **Fixes:** the orchestrator edits the spec doc directly.
  **Root-contradiction STOP:** if reviewers find the core requirement asks for two things
  that cannot both be true, STOP and hand off — quote the two conflicting clauses (a
  handoff, never a question; mere vagueness is decided, not stopped), record the handoff in plan file.
- **S4 — plan.** Use `superpowers:writing-plans` → write implementation plan
  into the **plan doc's implementation-plan section**; record how the
  work will be verified. On a consequential plan fork → convene the expert council.
- **S5 — produce.** Produce the work product. Code →
  `superpowers:subagent-driven-development`: keep its per-task reviews (early-catch), SKIP
  its final whole-implementation review — S7 is the authoritative whole-diff gate. Non-code → producer subagents via the
  same dispatch pattern. The orchestrator never edits the work product itself.
  (worktree-pinned — see Operating disciplines)
- **S6 — verify.** Use `superpowers:verification-before-completion`: run the
  discovered checks. Never weaken, skip,
  or delete a check.
- **S7 — work review.** Run the S7 review loop (see **Review rounds**) over the work.
  **Fixes:** ONE fresh producer subagent primed with the deduped open blockers + cited
  files only (worktree-pinned — see Operating disciplines). Docs are part of S7.
- **S8 — squash.** Idempotent squash to one commit (skip if already exactly 1
  ahead of `base_ref`). Working notes (spec/plan/progress) are committed or ignored per the
  project's convention — do not force either.
- **S9 — finish.** Inline (no skill): report
  review history, decisions, deferred non-blockers (stop-reason first if the run stopped);
  offer integration options as an informational report menu, NOT a question. NO merge. Then
  emit the **Result handoff** block (below) as the final output.

## Safety stops (handoffs, not questions)

→ see **references/autopilot-common.md §C6 Safety stops** (build's cap-2 case is per-phase:
`ralphLoop.maxIterations.spec-phase` / `.implementation-phase`).

## Result handoff (always emit last)

→ emit the `autopilot-result` block per **references/autopilot-common.md §C7 Result handoff**
on every terminal path (S9 finish AND any safety-stop handoff).
