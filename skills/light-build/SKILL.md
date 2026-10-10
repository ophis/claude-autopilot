---
name: light-build
description: "Self-contained, autonomous, low-ceremony build harness: create an isolated worktree, produce the work, verify, and run a capped correctness + requirement-fidelity + doc review to a single review-ready branch (never merges). Has no plugin dependency — runs with nothing else installed. For simple tasks, or as a lighter-than-build option when you want autonomy + expert-council-at-forks without the spec/review rigor — for that rigor use build. Pass the requirement text."
argument-hint: "<requirements>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, SendMessage, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite
---

# Autopilot: light-build

Autonomous light-build run. Drive the pipeline end to end: dispatch and judge; no scope
gate. **Self-contained: name or invoke no external plugin skill; no dependency preflight.**

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent: free-text requirements. **The requirement IS
the spec.** Empty input → STOP with a handoff asking for requirements.

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
- **No merge.** The run ends at a review-ready branch.

## Resume & state

**On start, resume first.** Look for an existing **state file** with a RESUME block in the
project's convention location. If found: reconcile worktree/branch/base_ref existence on
disk, then continue from `phase`. An interrupted S7 review round re-runs with the whole
frozen panel, on the phase's transport; only `review_round` need be persisted to locate the
loop. **No state file → start at S1.**

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
trigger above) the producer stops and returns a `FORK:` marker naming the options. Shape:

```
FORK: <one-line question>
- option A: <terse description + trade-off>
- option B: <terse description + trade-off>
```

On a `FORK:` return the orchestrator **convenes the expert council** (above), **decides**,
**records** the brief decision, and **re-dispatches the producer** with the decision baked
into its prompt ("DECISION: <chosen option + one-line rationale>; proceed — do not re-fork on
this"). A trivial/low-stakes ambiguity is NOT a fork — the producer picks the obvious default
(a wrong guess is caught by S7).

## S7 — correctness + requirement-fidelity + doc review

S7 is the **sole correctness gate**.

- **Panel:** pin `autopilot:correctness-reviewer`, `autopilot:requirement-fidelity-reviewer`
  AND `autopilot:doc-reviewer` — the whole panel: three cores, no optionals. Freeze it in
  context (see **Working-note shapes**); reuse it every round.
- **Dispatch** each round's members together, never one at a time (the re-review too).
  Each member's run-input prompt, built once: "PHASE=work. Inputs: worktree=…, base_ref=…,
  requirement=…, focus=…. Output ONLY the verdict, no extra prose." (absolute paths;
  reviewers read the worktree, never main). Members: `autopilot:<name>` with ONLY that
  prompt. A re-reviewed lens's prompt adds its prior items (`<lens>#<n> "<gist>"`, from the
  in-context notes) + the fix diff `git -C <worktree> diff <pre-fix HEAD>..HEAD` (record the
  pre-fix HEAD before the fix).
  - **Workflow (default):** per round, one
    `Workflow({name: "autopilot:autopilot-review-round", args: {phase: "work", members: [{agent, subagent_type, prompt}, …]}})`
    → `{phase, verdicts: [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}, …]}` in member
    order; never pass `resumeFromRunId`. Re-dispatch a `synthetic: true` member once via
    `Task` with its prompt; still no verdict → FAIL.
  - **Task (fallback):** if the `Workflow` call fails, dispatch the same members fresh as
    one parallel `Task` batch with the same prompts, and stay on Task for the phase (freeze
    note `->Task`). PASS only with no BLOCKING; no or unparseable verdict → FAIL.
- **Wait for every verdict** — never poll or judge early — then ONE fix over all open
  blockers, then the re-review.
- **Item IDs:** before deduping for the fixer, label every BLOCKING / NON-BLOCKING item
  `<lens>#<n>` (per lens, continuing across the phase, never reused); a repeated OPEN
  item keeps its ID (reviewers prefix it) — number only new items.
- **Loop** (orchestrator-run, cap = 1):
  - **Round 0** = the pinned panel; all-PASS short-circuits → S7→S8.
  - **Fix:** the first fix is ONE fresh producer via plain `Task` primed with the deduped
    open blockers (with item IDs) + cited files only; keep its agent ID in context; later
    fixes continue it via `SendMessage` (unknown ID / error → fresh producer, whose ID
    replaces it). A fix-time genuine fork goes through the **S5 FORK → council**
    mechanism, not an in-loop council. Full blocker text primes the fix transiently; only
    a concise gist is logged.
  - **Re-review** (the one round the cap allows) = only the lenses that failed last round;
    the rest carry their PASS.
  - **Advance** when every pinned lens is PASS with no open BLOCKING → S7→S8. Cap hit
    without convergence → Safety stop 2. Only reviewers' own verdicts decide
    convergence: never override one, downgrade a blocker, or mark an item INVALID yourself.

## Working-note shapes (in context — not persisted)

Track these for the S9 report, which surfaces them plus the residual NON-BLOCKING items:

- **Panel freeze:** `S7 panel: pinned=[correctness,requirement-fidelity,doc] transport=Workflow` (append `->Task` if the fallback fires).
- **Each review round** (VERDICT roll-up + a concise gist per blocker, with item IDs): `S7 r0: correctness=FAIL requirement-fidelity=PASS -> correctness#1 off-by-one in slice bound; fix dispatched`.
- **Each decision** (council or solo, incl. a resolved S5 FORK): `decision(<topic>): chose X over Y - <short reason>; dissent: <one phrase | none>`.

## Pipeline (S1, S5–S9)

Legend: **S#** = build's step S# (numbering shared with `build`). Pipeline:
**S1 → S5 → S6 → S7 → S8 → S9** — light skips S2 (brainstorm), S3 (spec review), S4
(plan).

- **S1 — worktree.**
  - If already in an isolated worktree (not on `main`/`master`), reuse it — do not nest another. `base_ref` is current local HEAD.
  - Else, if this requirement's `<prefix>-<slug>` branch (below) exists from a prior run, reuse it with its commits — do not create a numbered one: enter its worktree (`git worktree list`; if none, `git worktree add <path> <branch>`), `base_ref` = `git merge-base HEAD <branch>`; a state file there → resume from it.
  - Else create worktree on local HEAD, then enter:
    - `<prefix>` = the ticket ID when the work is for one single ticket (e.g. Linear `TASK-123`), else `autopilot`.
    - `<path>` = `.claude/worktrees/<prefix>-<slug>`, ensure `.claude/worktrees/` is gitignored (add it to `.gitignore` if not)
    - `<slug>` = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens, collapsed to <=40 chars; with a ticket prefix, a short feature description instead (not the ticket ID again). On collision with another requirement's worktree/branch: retry with a uniquified slug (`-2`, …).
    - `git worktree add <path> -b <prefix>-<slug> HEAD`
    - `EnterWorktree({path: <path>})`
  - Hold `worktree`, `branch`, `base_ref` (HEAD) in context.
- **S5 — produce.** Produce the work product by dispatching a **producer subagent
  via plain `Task`** (by reference, bounded prompt) — no per-task review. `FORK:` → the
  **S5 FORK mechanism**. A producer may commit its work; the S8 squash folds its commits.
  The orchestrator never edits the work product itself.
- **S6 — verify.** Run the target repo's own checks (those its CLAUDE.md, README or CI
  name) **inline via `Bash`**; none named → the checks its build/test manifests define
  (`package.json` `test`, Makefile, pre-commit, …); none at all → say so in the S9 report.
  **Never weaken, skip, or delete a check.** Idempotent — re-running is safe. Claim a
  result only from this run's output (exit code, failure count).
- **S7 — work review.** Run the **S7 review** above over the work.
- **S8 — squash.** Idempotent squash to one commit **via `git` (`Bash`)** — **skip
  if already exactly 1 ahead of `base_ref`**. The state file, if any, is committed or
  ignored per the project's convention — do not force either.
- **S9 — finish.** Inline: report review history, decisions, deferred non-blockers
  (stop-reason first if the run stopped); offer integration options as an informational
  report menu, NOT a question. NO merge.

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on the cases below.
1. **Destructive op — only when Auto Mode (auto-accept / bypass-permissions) is OFF.**
   Before any force-push, write outside the worktree, history rewrite beyond this branch,
   or rm/reset of uncommitted work.
2. **Non-convergence at cap** — the S7 review hits its cap without convergence (with the
   classification).
3. **Non-review phase failure** — one retry, then STOP.
4. **Root-contradiction** — the core requirement is self-contradictory; cite the two
   clauses.

## Result handoff (always emit last)

On **every** terminal path — S9 finish AND any safety-stop handoff — emit as the final
output exactly one fenced `autopilot-result` block (one JSON object) so a caller consumes
the outcome without parsing prose:

```autopilot-result
{ "status": "converged", "branch": "<prefix>-<slug>", "base_ref": "<sha>", "head": "<sha>", "blockers": [], "reason": "" }
```

- `status` — `converged` (reached S9) | `capped-without-pass` (the S7 loop hit its cap) | `stopped` (any other safety stop).
- `branch` / `base_ref` / `head` — branch name, its base SHA, its final commit SHA (`head` = `base_ref` if nothing was produced).
- `blockers` — residual open BLOCKING items (strings) when `status != converged`, else `[]`.
- `reason` — empty when converged; else classification + detail (cap → oscillation | unfixable | requirements-conflict; stop → root-contradiction | phase-failure | destructive-op).
