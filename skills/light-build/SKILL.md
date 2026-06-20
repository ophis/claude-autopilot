---
name: light-build
description: "Self-contained, no-plugin-dependency, low-ceremony autopilot path: no spec doc, no spec review, a pinned cap-1 correctness + requirement-fidelity + doc review, to a single review-ready branch (never merges). Use for simple tasks or a superpowers-free autonomous run (experts resolve forks, never the user); for spec/review rigor use medium-build or build. Pass the requirement text."
argument-hint: "<requirements>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite
---

# Autopilot: light-build

You are the orchestrator for an autonomous **light-build** run — the **self-contained,
low-ceremony** path. Drive the pipeline end to end: dispatch and judge. It is **dual-use**:
for simple tasks, and as a **lighter alternative to `build`** when you want autopilot's
autonomy + expert-council-at-forks without the spec/review rigor. Its defining trait is the
**interaction model** (do it autonomously; experts resolve forks, never the user), NOT a
file-count scope.

This is the **only fully self-contained surface** — **no plugin dependency**: every phase
uses a native tool, autopilot's own script, or inline logic. **It invokes no external plugin
skill (no `<plugin>:<skill>` call) and runs with nothing else installed** — no dependency
preflight. Naming any external plugin skill anywhere re-introduces a dependency — so do not
name or invoke one.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent: free-text requirements. **The requirement IS
the spec** — there is no spec doc, no brainstorm, no spec review. Empty input → STOP with a
handoff asking for requirements.

## Preflight

- **Read `${CLAUDE_PLUGIN_ROOT}/references/autopilot-common.md`** — the shared operating protocol (disciplines, dispatch transport, verdict grammar, progress-log shapes, safety stops, result handoff). This skill defines only its pipeline + the deltas below. This is a plugin-bundled reference file (like `review-round.js`), **not** a `superpowers:*` skill — reading it preserves self-containment.
- **No other preflight.** This path invokes no external plugin skill (no `<plugin>:<skill>` call) and runs with nothing else installed — no dependency preflight.

## Operating disciplines

The 5 shared disciplines (Autonomous · Thin orchestrator · Worktree-pinned dispatch ·
STOP-is-a-handoff · No merge) → see **references/autopilot-common.md §C1**. light-specific
addition:

- **Lazy state.** Persist by exception, not by default — a straight-through run writes no
  file; materialize a minimal requirement + RESUME state file only at the first
  compaction-risk boundary (see **Resume & state**).

## Resume & state

**On start, resume first.** Look for an existing **state file** with a RESUME block in the
project's convention location. If found: reconcile worktree/branch/base_ref existence on
disk, then continue from `phase`. An interrupted S7 review round is **re-run from scratch**
(re-dispatch the whole frozen panel — bounded), only `review_round` need be
persisted to locate the loop. **No state file → start at S1** — a straight-through run may
never have materialized one, so an interrupted simple run re-runs from scratch (bounded,
idempotent; S1 reuses the existing worktree).

**Persist lazily, by exception.** A straight-through run writes **no file at all** — hold the
requirement, worktree/branch/base_ref, phase, and decisions in context. **Materialize a
minimal state file the first time the run crosses a compaction-risk boundary** — whichever is
first: a council / `FORK` resolved, S7 returns a FAIL and a fix round begins, or the producer
reports multi-step work across several dispatches. The file holds **only** the verbatim
requirement + a one-line RESUME block (and, for multi-step S5, a terse 1-line-per-task list)
— **never an audit trail**:

```
RESUME: phase=<S1|S5|S6|S7|S8|S9> worktree=<path> branch=<name> base_ref=<sha> review_round=<n>
```

**Location follows the user's / project's convention** — honor CLAUDE.md and existing repo
patterns.

## Deciding at decision points (expert council)

→ see **references/autopilot-common.md §C2 Deciding at decision points** (light dispatches the
parallel batch via `Task`; record the decision per **Working-note shapes**).

## The S5 FORK mechanism (producer → orchestrator → council → re-dispatch)

Producers do **NOT** consult the council directly. On a **genuine fork** (the council
trigger above) the producer **does not guess** — it stops and returns a `FORK:` marker
naming the options instead of picking one silently. Shape:

```
FORK: <one-line question>
- option A: <terse description + trade-off>
- option B: <terse description + trade-off>
```

On a `FORK:` return the orchestrator **convenes the expert council** (above), **decides**,
**records** the brief decision (in context — this **materializes the state file**, a fork
being a compaction-risk boundary), and **re-dispatches the producer** with the decision baked
into its prompt ("DECISION: <chosen option + one-line rationale>; proceed — do not re-fork on
this"). A trivial/low-stakes ambiguity is NOT a fork — the producer picks the obvious default
(a wrong guess is caught by S7).

## Verdict grammar (paste into ad-hoc review prompts only)

→ see **references/autopilot-common.md §C4 Verdict grammar** (light cites the requirement
clause, there being no spec doc).

## S7 — correctness + requirement-fidelity + doc review (cap 1)

S7 is the **sole correctness gate** on this path — no spec review, no S3, no S5 per-task
reviews, so S7 carries it alone (deliberate, not an oversight). The orchestrator runs the
loop itself, dispatching each round through the one-round transport `review-round.js`.

- **Pin the panel directly** — `autopilot:correctness-reviewer`,
  `autopilot:requirement-fidelity-reviewer`, AND `autopilot:doc-reviewer`. These three cores
  are the whole panel; there are no optionals.
- **Freeze** the pinned panel in context as the freeze shape (see **Working-note
  shapes**); reuse it every round.
- **Dispatch each round together** — never one at a time, the re-review included. The
  run-input prompt carries only light's inputs — "PHASE=work. Inputs: worktree=…, base_ref=…,
  requirement=…, focus=…. Output ONLY the verdict, no extra prose." (no `spec_doc`/`plan_doc` —
  light has neither). Transport mechanics (Workflow-preferred / Task-fallback / `synthetic` /
  partial-result) → **references/autopilot-common.md §C3 Dispatch transport**.
- **The loop** (orchestrator-run, cap = 1):
  - **Round 0** = the pinned panel; all-PASS short-circuits → proceed S7→S8.
  - **Fix:** dispatch ONE producer subagent via plain `Task` (worktree-pinned — like the S5
    producer) primed with the deduped open blockers + cited files only. A fix-time genuine fork
    uses the existing **S5 FORK → council** mechanism (orchestrator council), not an in-loop
    council. Full blocker text primes the fix transiently; logged only as a concise gist.
  - **Re-review** (the one round cap = 1 allows) dispatches only the **FAILed subset** — the
    lenses whose last verdict was FAIL/missing. All three are cores, so there is no `touched`
    recompute. Skipped lenses carry their PASS.
  - **Advance** when every pinned lens is PASS with no open BLOCKING → S7→S8. Cap hit
    without convergence → **non-convergence STOP** with the 3-way
    classification (oscillation | unfixable | requirements-conflict).

## Working-note shapes (in context — not persisted)

Keep working notes **in context**, not on disk; the materialized state file (when one exists)
holds only the verbatim requirement + RESUME line, **never an audit trail**. The audit-trail
principle + the **review-round** and **decision** shapes → see **references/autopilot-common.md
§C5 Progress / working-note shapes** (a resolved S5 FORK uses the **decision** shape).
`review_round` (in RESUME) is the only resume-load-bearing field. light records the freeze
in context, using the freeze shape:

- **Panel freeze** (transport record): `S7 panel: pinned=[correctness,requirement-fidelity,doc] transport=Workflow` (note a fallback only if it fired: `transport=Workflow->Task`).

Hold full blocker text only to prime the fix; the notes keep a concise gist. Keep every
line short. The S9 report surfaces these notes plus the residual NON-BLOCKING items.

## Pipeline (S1, S5–S9)

Legend: **S#** = build's step S# (numbering shared with `build`). Pipeline:
**S1 → S5 → S6 → S7 → S8 → S9** — light skips S2 (brainstorm), S3 (spec review), S4 (plan):
no spec doc, no spec review, no writing-plans.

- **S1 — worktree.** Create the worktree on local HEAD via raw git + the native **`EnterWorktree`** tool (this path borrows no skill).
  - If already in an isolated worktree (not on `main`/`master`), reuse it — do not nest another. `base_ref` is current local HEAD.
  - Else create worktree on local HEAD, then enter:
    - `<path>` = `.claude/worktrees/autopilot-<slug>`, ensure `.claude/worktrees/` is gitignored (add it to `.gitignore` if not)
    - `<slug>` = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens, collapsed to <=40 chars. On worktree/branch collision: retry with a uniquified slug (`-2`, …).
    - `git worktree add <path> -b autopilot-<slug> HEAD`
    - `EnterWorktree({path: <path>})`
  - Hold `worktree`, `branch`, `base_ref` (HEAD), and the verbatim requirement in context. **Create no state file yet** — it is materialized lazily at the first compaction-risk boundary (see **Resume & state**).
- **S5 — produce.** Produce the work product by dispatching a **producer subagent
  via plain `Task`** (by reference, bounded prompt; worktree-pinned — see Operating
  disciplines) — no per-task review, no task-driven framework. On a genuine fork the producer
  returns a `FORK:` marker → the orchestrator runs the **S5 FORK mechanism** (council →
  decide → record → re-dispatch with the decision). If the producer reports genuinely
  multi-step work, **materialize the state file** with a terse 1-line-per-task list. A
  producer may commit its work; the S8 squash folds its commits. The orchestrator never edits
  the work product itself.
- **S6 — verify.** Run the discovered checks **inline via `Bash`** (no skill; for THIS plugin = `claude plugin validate` + `python3 tests/test_scripts.py` + the documented manual smoke).
  **Never weaken, skip, or delete a check.** Idempotent — re-running is safe.
- **S7 — work review.** Run the **S7 review** above (**cap = 1**) over the work: pin
  `correctness` + `requirement-fidelity` + `doc`, then run the in-session loop — each round
  dispatched via `review-round.js` (Workflow; parallel-`Task` fallback). The orchestrator owns
  the loop and derives convergence from the verdicts itself; the fix is one `Task` producer.
  Cap hit without convergence → STOP with the 3-way classification.
- **S8 — squash.** Idempotent squash to one commit **via `git` (`Bash`)** — **skip
  if already exactly 1 ahead of `base_ref`**. The state file (if one was materialized) is
  committed or ignored per the project's convention — do not force either.
- **S9 — finish.** Inline (no skill): report review history, decisions, deferred
  non-blockers (stop-reason first if the run stopped); offer integration options as an
  informational report menu, NOT a question. NO merge. Then emit the **Result handoff** block
  (below) as the final output.

## Safety stops (handoffs, not questions)

→ see **references/autopilot-common.md §C6 Safety stops** (light's cap-2 case is the S7 review
at `cap` = 1).

## Result handoff (always emit last)

→ emit the `autopilot-result` block per **references/autopilot-common.md §C7 Result handoff**
on every terminal path (S9 finish AND any safety-stop handoff).
