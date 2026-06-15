---
name: light-build
description: "Self-contained, autonomous, low-ceremony build harness: create an isolated worktree, produce the work, verify, and run a capped correctness + requirement-fidelity + doc review to a single review-ready branch (never merges). Has no plugin dependency — runs with nothing else installed. For simple tasks, or as a lighter-than-build option when you want autonomy + expert-council-at-forks without the spec/review rigor — for that rigor use medium-build or build. Pass the requirement text."
argument-hint: "<requirements>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite
---

# Autopilot: light-build

You are the orchestrator for an autonomous **light-build** run — the **self-contained,
low-ceremony** path. Drive the pipeline below end to end: dispatch and judge. It is
**dual-use**: for simple tasks, and as a **lighter alternative to `build`** when you want
autopilot's autonomy + expert-council-at-forks without the spec/review rigor. Its defining
trait is the **interaction model** (just do it autonomously; experts resolve forks, never
the user), NOT a file-count scope.

This is the **only fully self-contained surface** — it has **no plugin dependency**: every
phase uses a native tool, autopilot's own script, or inline logic. **It invokes no external
plugin skill (no `<plugin>:<skill>` call) and runs even with nothing else installed** —
there is no dependency preflight. (Keeping this property intact matters: naming any external
plugin skill anywhere would re-introduce a dependency through the back door — so do not name
or invoke one.)

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent: free-text requirements. **The requirement IS
the spec** — there is no spec doc, no brainstorm, no spec review. Empty input → STOP with a
handoff asking for requirements.

## Operating disciplines

- **Autonomous — never ask the user.** At a genuine decision point, **convene the expert
  council** (see "Deciding at decision points") to deliberate, then decide + record;
  trivial vagueness → decide + record solo. Only the safety stops interrupt the run.
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never hoard
  whole files, diffs, or logs in the main thread; read only bounded slices when you must
  inspect something yourself. **You never edit the work product** — a producer subagent does.
- **Worktree-pinned dispatch.** Give every subagent the absolute worktree path + branch and
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
disk, then continue from `phase`. An interrupted S5 review round is **re-run from scratch**
(re-dispatch the whole frozen panel — bounded, idempotent), so only `review_round` need be
persisted to locate the loop. **No state file → start at E1** — a simple straight-through run
may never have materialized one, so an interrupted simple run re-runs from scratch (bounded,
idempotent; E1 reuses the existing worktree).

**Persist lazily, by exception.** A straight-through run writes **no file at all** — hold the
requirement, worktree/branch/base_ref, phase, and decisions in context. **Materialize a
minimal state file the first time the run crosses a compaction-risk boundary** — whichever
happens first: a council / `FORK` is resolved, S5 returns a FAIL and a fix round begins, or
the producer reports multi-step work spanning several dispatches. The file holds **only** the
verbatim requirement + a one-line RESUME block (and, for multi-step S3, a terse
1-line-per-task list) — **never an audit trail**:

```
RESUME: phase=<E1|S3|S4|S5|S6|S7> worktree=<path> branch=<name> base_ref=<sha> review_round=<n>
```

**Where this lives follows the user's / project's convention** — honor CLAUDE.md and existing
repo patterns; no fixed path, no gitignore-vs-commit policy.

## Deciding at decision points (expert council)

- At a genuine fork — two-plus viable approaches with materially different trade-offs, or a
  choice shaping architecture / data model / interface / scope, costly to reverse, or one a
  later review might miss — **convene a council**: 2–4 ad-hoc expert personas in one parallel
  `Task` batch, each returning a concise position (recommendation, rationale, trade-offs,
  dissent). You **synthesize, decide, and record** a one-line decision (see **Working-note
  shapes**) — the decider, breaking ties.
- Otherwise decide solo and record (a wrong guess is caught by review). Never fabricate
  personas to hit a count — fewer than two real lenses → solo.

## The S3 FORK mechanism (producer → orchestrator → council → re-dispatch)

Producers do **NOT** consult the council directly. When a producer hits a **genuine fork**
(two-plus viable approaches with materially different trade-offs — the council triggers
above) it **does not guess**: it stops and returns a `FORK:` marker naming the options,
instead of picking one silently. Shape:

```
FORK: <one-line question>
- option A: <terse description + trade-off>
- option B: <terse description + trade-off>
```

On a `FORK:` return, the orchestrator **convenes the expert council** (above), **decides**,
**records** the one-line decision (in context — this **materializes the state file**, since a
fork is a compaction-risk boundary), and **re-dispatches the producer** with
the decision baked into its prompt ("DECISION: <chosen option + one-line rationale>;
proceed — do not re-fork on this"). The council resolves the fork; the producer then
executes it. A trivial/low-stakes ambiguity is NOT a fork — the producer picks the obvious
default and proceeds (a wrong guess is caught by S5).

## Verdict grammar (paste into ad-hoc summon prompts only — roster agents already embed it)

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
Convergence is decided from these structured verdicts, never from vibes.

## S5 — correctness + requirement-fidelity + doc review (cap 1)

S5 is the **sole correctness gate** on this path — there is no spec review and no S1, and
S3 has no per-task reviews, so S5 carries it alone (a deliberate property of the light path,
not an oversight).

- **Pin the panel directly** — `autopilot:correctness-reviewer`,
  `autopilot:requirement-fidelity-reviewer`, AND `autopilot:doc-reviewer`.
- **Freeze** the pinned panel in context as the one-line freeze shape (see **Working-note
  shapes**); pass it to the loop.
- **Run the loop via `review-loop.js`**:
  `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/scripts/review-loop.js", args: {phase:"work",
  worktree, base_ref, requirement, spec_doc:null, plan_doc:<state file|null>, cap:1,
  panel:[{agent, subagent_type, focus}, …]}})` — `args` a real JSON object. The call
  returns a task ID; its completion notification carries `{converged, rounds, head,
  verdicts, blockers, reason, decisions}` — wait for it (never poll/judge early). Map it:
  `converged:true` → record `AUTOPILOT: WORK READY`, proceed S5→S6; `converged:false` →
  **non-convergence STOP** with `reason` (oscillation | unfixable | requirements-conflict).
  Log each `decisions[]` entry as a decision line. The S5 fix and any fix-time FORK/council
  run **inside** the loop; S3-produce FORKs still use the orchestrator council (unchanged).
- **No-Workflow fallback:** iff the `Workflow` tool is unavailable, `Read`
  `${CLAUDE_PLUGIN_ROOT}/skills/_shared/review-loop.md` and run the prose loop in-session.

## Working-note shapes (in context — not persisted)

light-build keeps its working notes **in context**, not on disk. The materialized state file
(when one exists) holds only the verbatim requirement + the RESUME line — **never an audit
trail**. Track the shapes below in context for the S7 report; `review_round` (in the RESUME
block) is the only field that is load-bearing for resume.

- **Panel freeze** (transport record): `S5 panel: pinned=[correctness,requirement-fidelity,doc] transport=Workflow` (note a fallback only if it fired: `transport=Workflow->Task`).
- **Each review round** (lens=VERDICT roll-up + blocker COUNT, never blocker text): `S5 r0: correctness=FAIL requirement-fidelity=PASS -> 1 blocker, fix dispatched`.
- **Each decision** (council or solo, incl. a resolved S3 FORK): `decision(<topic>): chose X over Y - <reason <=12 words>; dissent: <<=8 words | none>`.

Blocker text is transient — hold it to prime the fix, never write it down. The S7 report
surfaces these notes plus the residual NON-BLOCKING items.

## Pipeline (E1, S3–S7)

Legend: **E1** = entry phase; **S#** = the spine (light path skips S1, S2). Pipeline:
**E1 → S3 → S4 → S5 → S6 → S7**. No E2 brainstorm, no spec doc, no spec review, no
writing-plans.

- **E1 — worktree (step 1).** Create an isolated worktree + branch `autopilot/<slug>` via
  the native **`EnterWorktree`** tool. Inline rules (this path borrows no skill):
  - **Step-0 reuse:** if you are **already in an isolated worktree** for this run, reuse it
    — do not nest another.
  - **Slug** = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens, collapsed/trimmed,
    truncated to ~40 chars.
  - **Collision:** on worktree/branch collision, **one** retry with a uniquified slug
    (`-2`, …), else STOP.
  Hold worktree/branch/base_ref (HEAD) + the verbatim requirement in context. **Create no
  state file yet** — it is materialized lazily at the first compaction-risk boundary (see
  **Resume & state**).
- **S3 — produce (step 2).** Produce the work product by dispatching a **producer subagent
  via plain `Task`** (by reference, bounded prompt; worktree-pinned — see Operating
  disciplines) — there is no per-task review and no task-driven framework. On a genuine fork the producer returns a `FORK:` marker → the
  orchestrator runs the **S3 FORK mechanism** (council → decide → record → re-dispatch with
  the decision). Producers do **NOT** consult the council directly. If the producer reports
  genuinely multi-step work, **materialize the state file** with a terse 1-line-per-task list
  for resumability. A producer may commit its work; the S6 squash folds its commits. The
  orchestrator never edits the work product itself.
- **S4 — verify (step 3).** Run the discovered checks **inline via `Bash`** (no skill).
  Discover the project's checks (for THIS plugin = `claude plugin validate` + `python3
  tests/test_scripts.py` + the documented manual smoke). Cap fixes at **3**. **Never weaken,
  skip, or delete a check; a drop in the check count → STOP** (non-review phase failure).
  Idempotent — re-running it is safe.
- **S5 — work review (step 4).** Run the **S5 review** above (**cap = 1**) over the work: pin
  `correctness` + `requirement-fidelity` + `doc`, then run the whole loop via `review-loop.js`
  (Workflow; `_shared/review-loop.md` prose fallback when `Workflow` is unavailable). On
  `converged:true` record `AUTOPILOT: WORK READY`; on `converged:false` STOP with `reason`.
- **S6 — squash (step 5).** Idempotent squash to one commit **via `git` (`Bash`)** — **skip
  if already exactly 1 ahead of base_ref**. The state file (if one was materialized) is
  committed or ignored per the project's convention — do not force either.
- **S7 — finish (step 6).** Inline (no skill): report review history, decisions, deferred
  non-blockers (stop-reason first if the run stopped); offer integration options as an
  informational report menu, NOT a question. NO merge. Then emit the **Result handoff** block
  (below) as the final output.

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on the four cases below. Every STOP handoff
ends by emitting the **Result handoff** block (`status`=`stopped`, or `capped-without-pass`
at the cap).
1. **Destructive op — only when Auto Mode is OFF.** Before any force-push, write outside
   the worktree, history rewrite beyond this branch, or rm/reset of uncommitted work.
   **In Auto Mode** (auto-accept / bypass-permissions), skip this stop — destructive-op
   judgment is deferred to Auto Mode. The other three stops apply regardless of Auto Mode.
2. **Non-convergence at cap** — the S5 review hits `cap` (= 1) without the marker (with the
   classification).
3. **Non-review phase failure** — one retry, then STOP (incl. an S4 check-count drop).
4. **Root-contradiction** — the core requirement is self-contradictory; cite the two
   clauses (a handoff, never a question; mere vagueness is decided, not stopped).

## Result handoff (always emit last)

On **every** terminal path — S7 finish AND any safety-stop handoff — emit as the final
output exactly one fenced `autopilot-result` block (one JSON object) so a calling
skill/workflow consumes the outcome without parsing prose:

```autopilot-result
{ "status": "converged", "branch": "autopilot/<slug>", "base_ref": "<sha>", "head": "<sha>", "blockers": [], "reason": "" }
```

- `status` — `converged` (reached S7) | `capped-without-pass` (the S5 loop hit its cap) | `stopped` (any other safety stop).
- `branch` / `base_ref` / `head` — branch name, its base SHA, its final commit SHA (`head` = `base_ref` if nothing was produced).
- `blockers` — residual open BLOCKING items (strings) when `status != converged`, else `[]`.
- `reason` — empty when converged; else classification + detail (cap → oscillation | unfixable | requirements-conflict; stop → root-contradiction | phase-failure | destructive-op).

Additive only — it changes no phase's behavior.
