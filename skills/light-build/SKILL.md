---
name: light-build
description: "Self-contained, autonomous, low-ceremony build harness: create an isolated worktree, produce the work, verify, and run a capped correctness + requirement-fidelity + doc review to a single review-ready branch (never merges). Has no plugin dependency — runs with nothing else installed. For simple tasks, or as a lighter-than-build option when you want autonomy + expert-council-at-forks without the spec/review rigor — for that rigor use medium-build or build. Pass the requirement text."
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

## Operating disciplines

- **Autonomous — never ask user.** At a decision point, **convene expert
  council or decide solo** (see "Deciding at decision points").
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never hoard
  whole files, diffs, or logs in main thread; read only bounded slices when you must
  inspect something yourself.
- **Worktree-pinned dispatch.** Give every subagent absolute worktree path + branch and
  have it act only there — absolute paths / `git -C <worktree>`, never inherited cwd — and
  **before any write assert** `git -C <worktree> branch --show-current` is the run branch;
  **never** main/master.
- **Lazy state.** Persist by exception, not by default — a straight-through run writes no
  file; materialize a minimal requirement + RESUME state file only at the first
  compaction-risk boundary (see **Resume & state**).
- **A STOP is a handoff, never a question:** emit current state + the exact next step a
  human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

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

- At a genuine fork — two-plus viable approaches with materially different trade-offs, or a
  choice shaping architecture / data model / interface / scope, costly to reverse, or one a
  later review might miss — **convene a council**: 2–4 ad-hoc expert personas in one parallel
  `Task` batch, each returning a concise position (recommendation, rationale, trade-offs,
  dissent). You **synthesize, decide, and record** a brief decision (see **Working-note
  shapes**) — the decider, breaking ties.
- Otherwise decide solo and record (a wrong guess is caught by review). Never fabricate
  personas to hit a count — fewer than two real lenses → solo.

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

Output ONLY the verdict — no prose/preamble. When a `StructuredOutput` tool is offered
(Workflow transport), the verdict IS that call: `{VERDICT: PASS|FAIL, BLOCKING: [...],
NON_BLOCKING: [...]}`, nothing else. Else (Task fallback) emit exactly:

```
VERDICT: PASS            # or exactly: VERDICT: FAIL
BLOCKING: none           # or one "- " item per line
NON-BLOCKING: none       # or one "- " item per line
```

PASS ⟺ no blocking items. Cite evidence (file:line / requirement clause); flag blockers,
not preferences. A missing, unparseable, or empty-on-FAIL verdict counts as **FAIL**.
Convergence is decided from these on-disk verdicts, never from vibes.

## S7 — correctness + requirement-fidelity + doc review (cap 1)

S7 is the **sole correctness gate** on this path — no spec review, no S3, no S5 per-task
reviews, so S7 carries it alone (deliberate, not an oversight). The orchestrator runs the
loop itself, dispatching each round through the one-round transport `review-round.js`.

- **Pin the panel directly** — `autopilot:correctness-reviewer`,
  `autopilot:requirement-fidelity-reviewer`, AND `autopilot:doc-reviewer`. These three cores
  are the whole panel; there are no optionals.
- **Freeze** the pinned panel in context as the freeze shape (see **Working-note
  shapes**); reuse it every round.
- **Dispatch each round together** — never one at a time, the re-review included. Build each
  member's run-input prompt once — "PHASE=work. Inputs: worktree=…, base_ref=…, requirement=…,
  focus=…. Output ONLY the verdict, no extra prose." (absolute paths; reviewers read the worktree,
  never main) — the identical prompt rides whichever transport carries it:
  - **Workflow transport (preferred):** one call per round —
    `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/scripts/review-round.js", args: {phase: "work", members: [{agent, subagent_type, prompt}, …]}})`,
    `args` is a real JSON object. The call returns a task ID; the round's verdicts arrive in its
    completion notification as `{phase, verdicts: [{agent, VERDICT, BLOCKING, NON_BLOCKING,
    synthetic}, …]}` — wait for it (never poll/judge early). Never pass `resumeFromRunId` — every round is a fresh run. `synthetic: true` = that member's
    infra failure, not a FAIL: re-dispatch just those lenses once via `Task`; still nothing →
    FAIL. No `verdicts` array, or one shorter than sent → Task fallback for the missing members.
  - **Task fallback:** if `Workflow` is unavailable or a call failed, dispatch the members as
    parallel `Task(subagent_type="autopilot:<name>")` calls in one batch — send ONLY the
    run-input prompt. Note the fallback on the freeze line's `transport=` field if it fired.
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
holds only the verbatim requirement + RESUME line, **never an audit trail**. Track the shapes
below for the S9 report; `review_round` (in RESUME) is the only resume-load-bearing field.

- **Panel freeze** (transport record): `S7 panel: pinned=[correctness,requirement-fidelity,doc] transport=Workflow` (note a fallback only if it fired: `transport=Workflow->Task`).
- **Each review round** (VERDICT roll-up + a concise gist per blocker): `S7 r0: correctness=FAIL requirement-fidelity=PASS -> 1 blocker (off-by-one in slice bound), fix dispatched`.
- **Each decision** (council or solo, incl. a resolved S5 FORK): `decision(<topic>): chose X over Y - <short reason>; dissent: <one phrase | none>`.

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

Stop and hand off (state + exact next step) only on the cases below. Every STOP handoff
ends by emitting the **Result handoff** block (`status`=`stopped`, or `capped-without-pass`
at the cap).
1. **Destructive op — only when Auto Mode is OFF.** Before any force-push, write outside
   the worktree, history rewrite beyond this branch, or rm/reset of uncommitted work.
   **In Auto Mode** (auto-accept / bypass-permissions), skip this stop — destructive-op
   judgment is deferred to Auto Mode. The other three stops apply regardless of Auto Mode.
2. **Non-convergence at cap** — the S7 review hits `cap` (= 1) without convergence (with the
   classification).
3. **Non-review phase failure** — one retry, then STOP.
4. **Root-contradiction** — the core requirement is self-contradictory; cite the two
   clauses.

## Result handoff (always emit last)

On **every** terminal path — S9 finish AND any safety-stop handoff — emit as the final
output exactly one fenced `autopilot-result` block (one JSON object) so a caller consumes
the outcome without parsing prose:

```autopilot-result
{ "status": "converged", "branch": "autopilot-<slug>", "base_ref": "<sha>", "head": "<sha>", "blockers": [], "reason": "" }
```

- `status` — `converged` (reached S9) | `capped-without-pass` (the S7 loop hit its cap) | `stopped` (any other safety stop).
- `branch` / `base_ref` / `head` — branch name, its base SHA, its final commit SHA (`head` = `base_ref` if nothing was produced).
- `blockers` — residual open BLOCKING items (strings) when `status != converged`, else `[]`.
- `reason` — empty when converged; else classification + detail (cap → oscillation | unfixable | requirements-conflict; stop → root-contradiction | phase-failure | destructive-op).
