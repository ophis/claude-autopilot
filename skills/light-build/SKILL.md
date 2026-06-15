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
- **Lazy state — persist by exception, not by default.** There is **no spec doc and no
  mandatory plan/state file**. A straight-through run (produce → verify → S5 round-0 all-PASS
  → squash → finish) writes **nothing to disk** — hold the requirement,
  worktree/branch/base_ref, phase, and any decisions in context. **Materialize a minimal
  state file the first time the run crosses a compaction-risk boundary** — whichever happens
  first: a council/`FORK` is resolved, S5 returns a FAIL and a fix round begins, or the
  producer reports multi-step work spanning several dispatches. The file holds **only** the
  **verbatim requirement** + a **one-line RESUME block** (+ a terse 1-line-per-task list for
  multi-step S3) — **never an audit trail**. Once it exists, keep RESUME current. See
  **State & resumption**.
- **A STOP is a handoff, never a question:** emit current state + the exact next step a
  human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

## Resume first (the resume contract)

Before anything else, look for an existing **state file** with a RESUME block in the
project's convention location. If found: reconcile worktree/branch/base_ref existence on
disk, then continue from `phase`. An interrupted S5 review round is **re-run from scratch**
(re-dispatch the whole frozen panel — bounded, idempotent), so only `review_round` need be
persisted to locate the loop. **No state file → start at E1** — a simple straight-through run
may never have materialized one, so an interrupted simple run re-runs from scratch (bounded,
idempotent; E1 reuses the existing worktree).

## Deciding at decision points (expert council)

When a choice is genuinely in doubt, **convene an expert council** — 2–4 ad-hoc expert
sub-agents (personas from the decision's domain), in **one parallel `Task` batch** (all calls
in a single message), each returning a concise position (recommendation + rationale +
trade-offs + any dissent). The orchestrator **synthesizes, decides, and records** a one-line
decision (see **Working-note shapes**); it is the decider and breaks ties.

**Convene** when the choice has two-plus viable approaches with materially different
trade-offs, shapes architecture / data model / interface / scope, is costly to reverse, or is
a fork a later review might miss. **Decide solo** (and record) when an obvious default or
convention dictates, or it is cosmetic / local / easily reversible (a wrong guess is caught
by S5). Pay-per-use: fires zero-plus times per run. Fewer than two distinct lenses →
smaller council or solo; never fabricate personas to hit a count.

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
  `autopilot:requirement-fidelity-reviewer`, AND `autopilot:doc-reviewer`. No other
  reviewers; **no `select-panel.py`** (pinned, not selected). **Why these three:**
  `correctness` judges internal correctness only; with no spec doc/review,
  `requirement-fidelity` is the *sole* lens checking the work realizes the **requirement** —
  without it a producer could build the wrong thing, bug-free, and pass; `doc` (roster-core,
  `applies_to: ["**"]`) catches docs the change falsified — **a change can leave docs
  elsewhere stale** — and self-scopes via bounded mono-repo discovery, PASSing cleanly when
  nothing is affected (pin it every round, don't gate on a file-type signal).
  **`requirement-fidelity`'s reference is the run's requirement text** (`$ARGUMENTS` — the
  verbatim requirement held in context, recorded in the state file once materialized), **not
  a spec doc**.
- **Freeze** the pinned panel in context as the one-line freeze shape (see **Working-note
  shapes**); reuse it every round of S5.
- **Dispatch the whole round together** — never one at a time. Build each member's run-input
  prompt once — "PHASE=work. Inputs: worktree=…, base_ref=…, requirement=<the verbatim
  requirement>, focus=…. Output ONLY the verdict, no prose." (absolute paths) — the identical
  prompt rides whichever transport carries it:
  - **Workflow transport (preferred):** one call per round —
    `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/scripts/review-round.js", args: {phase: "work", members: [{agent, subagent_type, prompt}, …]}})`,
    `args` a real JSON object (it tolerates a stringified one; don't rely on it). Members keep
    their own model + read-only allowlist (`agentType` resolves like `Task`). The call returns
    a task ID; the round's verdicts arrive in its completion notification as `{phase, verdicts:
    [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}, …]}` — wait for it (never poll/judge
    early). Never pass `resumeFromRunId` — every round is a fresh run. `synthetic: true` = that
    member's infra failure, not a FAIL: re-dispatch just those lenses once via `Task`; still
    nothing → FAIL. No `verdicts` array, or one shorter than sent (incl. `[]`) → failed/partial
    → Task fallback for the missing members.
  - **Task fallback (plain parallel batch):** if `Workflow` is unavailable or a call failed,
    dispatch the pinned members as `Task(subagent_type="autopilot:<name>", …)` — body is the
    system prompt; send ONLY the run-input prompt, **all calls in a single message** (a plain
    parallel `Task` batch), rest of the run. The transport + any fallback that fired ride the
    freeze line's `transport=` field (see **Working-note shapes**) — not a separate log line.
- Each reviewer returns the verdict block; collect verdicts → the loop below.

**Cap = 1** (round 0 + at most one fix round) — pinned, not from config. **Round 0** = the
full pinned panel; all-PASS short-circuits. A FAIL → **ONE** fresh producer subagent primed
with the deduped open blockers + cited files only (entering this fix round **materializes the
state file** if not already present), then **re-review only the FAILed
lens(es)** (also re-run `doc` if the fix touched docs — it can regress) — there is no `select-panel.py` / `touched`
computation here; the pinned set is fixed and a skipped lens keeps its PASS as its current
verdict. Advance when every pinned lens's current verdict (fresh or carried) is PASS with no
open BLOCKING; on convergence record `AUTOPILOT: WORK READY` and proceed (S5→S6). Still
failing at the cap (= 1) → **non-convergence STOP** with the 3-way classification
(oscillation | unfixable | requirements-conflict) and a handoff — do not proceed. Every
dispatched reviewer is a fresh instance; convergence is decided from the structured verdicts
(the marker is printed ONLY when convergence is genuinely true — never to escape the loop).

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
  **Lazy state** / **State & resumption**).
- **S3 — produce (step 2).** Produce the work product by dispatching a **producer subagent
  via plain `Task`** (by reference, bounded prompt) — there is no per-task review and no
  task-driven framework. On a genuine fork the producer returns a `FORK:` marker → the
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
- **S5 — work review (step 4).** Run the **S5 review** above (**cap = 1**) over the work:
  pin `correctness` + `requirement-fidelity` + `doc`, dispatch via
  `review-round.js` (Workflow transport; plain parallel `Task` batch fallback), one fix on
  FAIL, re-review only the FAILed lens(es). On convergence record `AUTOPILOT: WORK READY`.
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

## Token discipline

Thin orchestrator · by-reference dispatch (never pipe diffs into N prompts) · self-contained
(no external plugin skills loaded anywhere) · light path = fewest phases (no E2/S1/S2) + a
**pinned 3-lens S5 panel** (`correctness` + `requirement-fidelity` + `doc`) + **cap = 1** · round-0
short-circuit · re-dispatch only the FAILed lens(es) on the one fix round · bounded subagent
prompts · producer primed by blockers + cited files only · expert councils bounded (2–4), at
genuine forks only, one parallel batch · workflow transport returns a round's verdicts as one
JSON payload (reviewer output stays off the main thread) · **lazy state** — no file for a
straight-through run, a minimal requirement+RESUME stub only at compaction-risk boundaries
(see **State & resumption**).

## State & resumption

light-build persists state **lazily, by exception**. A straight-through run writes **no file
at all**; the orchestrator holds the requirement, worktree/branch/base_ref, phase, and
decisions in context. **Materialize a minimal state file the first time the run crosses a
compaction-risk boundary** — whichever happens first:

- a council / `FORK` decision is made,
- S5 returns a FAIL and a fix round begins,
- the producer reports multi-step work spanning several dispatches.

The file holds **only** the verbatim requirement + a one-line RESUME block (and, for
multi-step S3, a terse 1-line-per-task list) — **never an audit trail**:

```
RESUME: phase=<E1|S3|S4|S5|S6|S7> worktree=<path> branch=<name> base_ref=<sha> review_round=<n>
```

**Why lazy:** a simple single-shot run finishes inside one context and never reads state
back, so a file is pure overhead; the boundaries above are exactly where a run grows long
enough to risk compaction, and only then is durable state worth its cost. **Keep RESUME
current** once the file exists — rewrite `phase=` at every transition and `review_round=`
each S5 loop iteration; the resume contract (**Resume first**) depends on `phase=` being
true. Trade-off: an interrupted simple run that never materialized a file re-runs from
scratch (bounded, idempotent) rather than resuming.

**Where this lives follows the user's / project's existing convention** — honor CLAUDE.md
preferences and existing repo patterns. The command imposes no fixed path (do not assume
`dev-docs/`) and no gitignore-vs-commit policy.
