---
name: light-build
description: "Self-contained, autonomous, low-ceremony build harness: create an isolated worktree, write an S4 task list, produce the work with a fresh producer per task, and run a capped correctness + requirement-fidelity + doc + verification review to a single review-ready branch (never merges). Has no plugin dependency — runs with nothing else installed. For simple tasks, or as a lighter-than-build option when you want autonomy + expert-council-at-forks without the spec/review rigor — for that rigor use build. Pass the requirement text."
argument-hint: "<requirements>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, SendMessage, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite
---

# Autopilot: light-build

Autonomous light-build run. Drive the pipeline end to end: dispatch and judge; no scope
gate. **Self-contained: name or invoke no external plugin skill; no dependency preflight.**

Before any phase, read [Host runtime](../host-runtime.md) and apply its mappings
for startup, paths, dispatch, review transport, and approvals throughout this skill.

## Your input

`input` is the single source of intent: free-text requirements. **The requirement IS
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
disk, then continue from `phase`. An interrupted S6 review round re-runs with the whole
frozen panel, on its recorded transport. **No state file → start at S1.**

**The state file** (materialized in S4) holds the requirement and full verify command
above RESUME, then the task list:

```
RESUME: phase=<S[14-8]> worktree=<path> branch=<name> base_ref=<sha> review_round=<n>
```

Advance RESUME's `phase=` with the run. From S6, persist RESUME, the frozen panel and
verdicts, reviewed SHA/tree, and exact commands and results (exit codes, failure counts, diagnostics)
in an ignored run note; reuse an ignored state file, or link the note from a tracked state
file before committing it for review. Resume S7/S8 only with all-PASS evidence for the current
tree; otherwise restart S6. For legacy S1–S9 states, restart old S6–S9 at S6, keeping task progress.

**Location follows the user's / project's convention** — honor AGENTS.md / CLAUDE.md and existing repo
patterns.

## Deciding at decision points (expert council)

- At a genuine fork — two-plus viable approaches with materially different trade-offs, or a
  choice shaping architecture / data model / interface / scope, costly to reverse, or one a
  later review might miss — **convene a council**: 2–4 ad-hoc expert personas in one independent
  native-dispatch batch, each returning a concise position (recommendation, rationale, trade-offs,
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
(a wrong guess is caught by S6).

## S6 — correctness + requirement-fidelity + doc + verification review

- **Panel:** pin `autopilot:correctness-reviewer`, `autopilot:requirement-fidelity-reviewer`,
  `autopilot:doc-reviewer` AND `autopilot:verification-reviewer` — four cores, no optionals.
  Freeze it in the run note (see **Working-note shapes**); reuse it every round.
- **Dispatch** each round's members together through the host adapter (the re-review too).
  Require a clean committed source worktree (`git -C <worktree> status --porcelain` empty);
  set `reviewed_sha=<HEAD>` with `git -C <worktree> rev-parse HEAD`. Keep it unchanged
  until all verdicts return; check HEAD still equals `reviewed_sha` and status remains
  empty before judging. Ordinary reviewers read source HEAD; the verification reviewer
  clones reviewed_sha into its isolated checkout and runs full checks every round.
  Ordinary reviewers leave full checks to it. Each member's run-input prompt:
  "PHASE=work. Inputs: worktree=…, base_ref=…, state_file=…, requirement=…, focus=…,
  reviewed_sha=<HEAD>. Output ONLY the verdict, no extra prose."
  Members use canonical `autopilot:<name>` instructions plus that prompt. A re-reviewed lens adds prior items
  (`<lens>#<n> "<gist>"`, from the run note) + the fix diff `git -C <worktree> diff <pre-fix HEAD>..HEAD` (record the
  pre-fix HEAD before the fix).
  - **Transport:** use the host adapter’s Workflow/native dispatch and verdict rules;
    freeze the actual transport with the panel.
- **Wait for every verdict** — never poll or judge early. Inspect the verifier's raw
  BLOCKING items before adding item IDs: `VERIFICATION_UNAVAILABLE:` (after its one
  retry) triggers Safety stop 3. Otherwise ONE fix over all blockers, then the re-review.
- **Item IDs:** before deduping for the fixer, label every BLOCKING / NON-BLOCKING item
  `<lens>#<n>` (per lens, continuing across the phase, never reused); a repeated OPEN
  item keeps its ID (reviewers prefix it) — number only new items.
- **Loop** (orchestrator-run, cap = 1):
  - **Round 0** = the pinned panel.
  - **Fix:** the first fix is ONE fresh producer via native dispatch primed with the deduped
    open blockers (with item IDs) + cited files only; keep its agent ID in context; later
    fixes continue it via the host continuation operation (unknown ID / error → fresh producer, whose ID
    replaces it). A fix-time genuine fork goes through the **S5 FORK → council**
    mechanism, not an in-loop council. Full blocker text primes the fix transiently; only
    a concise gist is logged.
  - **Re-review** (the one round the cap allows) = failed lenses plus
    `autopilot:verification-reviewer` every round, including after a PASS; other passed
    lenses carry their PASS.
  - **Advance** when every pinned lens is PASS with no open BLOCKING → S6→S7. Cap hit
    without convergence → Safety stop 2. Only reviewers' own verdicts decide
    convergence: never override one, downgrade a blocker, or mark an item INVALID yourself.

## Working-note shapes

Track these for S8 (S6 verdicts/evidence in the run note, other notes in context),
plus residual NON-BLOCKING items:

- **Panel freeze:** `S6 panel: pinned=[correctness,requirement-fidelity,doc,verification] transport=Workflow` (append `->Task` if the fallback fires).
- **Each completed S5 task** (from the state file's done marks): `S5 task <N> done: <commit sha>` — feeds the S8 report.
- **Each review round** (VERDICT roll-up + a concise gist per blocker, with item IDs): `S6 r0 @<reviewed_sha>: correctness=FAIL verification=PASS (command=<cmd>, exit code=0, failures=0) -> correctness#1 off-by-one in slice bound; fix dispatched`.
- **Each decision** (council or solo, incl. a resolved S5 FORK): `decision(<topic>): chose X over Y - <short reason>; dissent: <one phrase | none>`.

## Pipeline (S1, S4–S8)

Legend: **S#** = build's step S# (numbering shared with `build`). Pipeline:
**S1 → S4 → S5 → S6 → S7 → S8** — light skips S2 (spec), S3 (spec review).

- **S1 — worktree.**
  - If already in an isolated worktree (not on `main`/`master`), reuse it — do not nest another. `base_ref` is current local HEAD.
  - Else resolve the requirement's host-specific `<branch>` before lookup or creation; use this same resolved branch for worktree reuse and resume:
    - `<prefix>` = the ticket ID when the work is for one single ticket (e.g. Linear `TASK-123`), else `autopilot`.
    - `<slug>` = `input` lowercased, non-alphanumerics → hyphens, collapsed to <=40 chars; with a ticket prefix, a short feature description instead (not the ticket ID again).
    - Resolve `<path>` and `<branch>` through the worktree/branch conventions in `skills/host-runtime.md`; ensure the worktree directory is gitignored.
    - If this requirement's resolved `<branch>` exists from a prior run, reuse it with its commits — do not create a numbered one: enter its worktree (`git worktree list`; if none, `git worktree add <path> <branch>`), `base_ref` = `git merge-base HEAD <branch>`; a state file there → resume from it.
    - Else create worktree on local HEAD, then enter:
      - On collision with another requirement's worktree/branch: retry with a uniquified slug (`-2`, …) and resolve `<path>` and `<branch>` again.
      - Create and enter through the host adapter (git fallback: `git worktree add <path> -b <branch> HEAD`); use the absolute worktree directory for commands.
  - Hold `worktree`, `branch`, `base_ref` (HEAD) in context.
- **S4 — task list.** Write the task list yourself (invoke no planning skill): a code-free
  task list into the state file — S4 always materializes the state file. The task list is
  the state file's last section; the RESUME block goes above it (a brief runs to the next
  `### Task N` heading):
  - Header: Global Constraints (exact values producers need). Put the full verify
    command outside the task-list header, above RESUME in the state file.
  - Per task, a `### Task N: <name>` heading (its S5 producer reads its brief by it) with:
    Files; Consumes/Produces (exact names/signatures crossing tasks); tests to write
    first, incl. edge cases; the checks it runs (only those its change affects, never a
    full suite: the S6 verification reviewer runs that); commit message.
  - A small change is one task.
- **S5 — produce.** Per S4 task, in order from the first not `done`, dispatch one
  fresh producer subagent via native dispatch on the requirement, the task list header and
  its `### Task N` brief: tests first, then the code; run only the checks its brief
  names that cover its changed files (never the full verify command or full suite);
  commit with the brief's message; log the task `done`
  in the state file.
  `FORK:` → the **S5 FORK mechanism**. The orchestrator never edits the work product itself.
- **S6 — work review.** Run the review above; genuine check failures block. Each fix
  producer runs only checks covering the files it changes; the fix producer must commit
  all product changes before re-review under the dispatch rules above.
- **S7 — squash.** Idempotent squash to one commit **via `git` (host command tool)** — **skip
  if already exactly 1 ahead of `base_ref`**. The state file is committed or
  ignored per the project's convention — do not force either. Require a clean worktree
  and matching `git rev-parse HEAD^{tree}` / `git rev-parse <reviewed_sha>^{tree}`
  before S8; if trees differ, return to S6.
- **S8 — finish.** Inline: report review history, final verification evidence from the
  run note, decisions, deferred non-blockers (stop-reason first if stopped);
  offer integration options as an informational report menu, NOT a question.

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on the cases below.
1. **Destructive op requiring host approval without existing authorization.**
   Before force-push, history rewrite beyond this branch, or rm/reset of uncommitted
   work, apply the host adapter’s approval rules.
2. **Non-convergence at cap** — the S6 review hits its cap without convergence (with the
   classification).
3. **Non-review phase failure** — one retry, then STOP.
4. **Root-contradiction** — the core requirement is self-contradictory; cite the two
   clauses.

## Result handoff (always emit last)

On **every** terminal path — S8 finish AND any safety-stop handoff — emit as the final
output exactly one fenced `autopilot-result` block (one JSON object) so a caller consumes
the outcome without parsing prose:

```autopilot-result
{ "status": "converged", "branch": "<prefix>-<slug>", "base_ref": "<sha>", "head": "<sha>", "blockers": [], "reason": "" }
```

- `status` — `converged` (reached S8) | `capped-without-pass` (the S6 loop hit its cap) | `stopped` (any other safety stop).
- `branch` / `base_ref` / `head` — branch name, its base SHA, its final commit SHA (`head` = `base_ref` if nothing was produced).
- `blockers` — residual open BLOCKING items (strings) when `status != converged`, else `[]`.
- `reason` — empty when converged; else classification + detail (cap → oscillation | unfixable | requirements-conflict; stop → root-contradiction | phase-failure | destructive-op).
