---
name: build
description: "Use to build a new work product from a requirement, end to end: create an isolated worktree, write and review a spec, write a task list, implement, and review-loop with verification to a single review-ready branch (never merges). Pass the requirement text, or a path to an existing spec file."
argument-hint: "<requirements|spec-file-path>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, Task, SendMessage, Workflow, Skill, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite, ScheduleWakeup
---

# Autopilot: build

Paths are relative to this skill's directory.

Autonomous build run. Drive the pipeline end to end: dispatch and judge.

## Your input

`input` is Claude Code's substituted `$ARGUMENTS` or Codex's invoking user request /
explicit caller input; an unresolved placeholder is absent. It is the single source of intent:

- **Requirements mode (default):** free-text requirements → full pipeline.
- **Spec-file mode:** if `input` is the path of an **existing spec file**, **skip S2
  and S3**. The spec must be **self-contained** — enough to plan, implement, and verify
  without further clarification.

Empty input → STOP.

## Operating disciplines

- **Autonomous — never ask user.** At a decision point, **convene expert
  council or decide solo** (see "Deciding at decision points").
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never hoard
  whole files, diffs, or logs in main thread; read only bounded slices when you must
  inspect something yourself.
- **Resources.** Resolve bundled paths to absolute paths for tools and worker briefs without
  changing the target worktree cwd. Read applicable AGENTS.md / CLAUDE.md in the target
  repo/worktree and pass their paths and constraints to workers.
- **Native agents.** Use exposed spawn, continue and wait tools with documented arguments.
  Request fresh context when supported, supplying the brief and applicable constraints.
  Dispatch rounds in parallel, queuing remaining members at available concurrency
  capacity; collect every verdict before judging or fixing; status alone is no verdict.
- **Host tools.** Claude tool forms appear in parentheses; use the session's exposed
  equivalents elsewhere. Workflow is Claude-only; without it use the Task fallback.
  Worktree defaults: Claude `.claude/worktrees/<prefix>-<slug>`
  / `<prefix>-<slug>`; Codex `.codex/worktrees/<prefix>-<slug>` / `codex/<prefix>-<slug>`.
  Claude named reviewers keep `model:` / `effort:` and tools from `../../agents/*.md`.
  When named dispatch is unavailable, give a fresh generic reviewer the canonical
  `../../agents/<name>.md` body plus its run-input prompt; preserve the body's
  verdict grammar and tool/test boundaries. Codex uses these generic reviewers,
  inheriting the session model with no `model` override to `spawn_agent`.
- **Worktree-pinned dispatch.** Give every subagent absolute worktree path + branch and
  have it act only there — absolute paths / `git -C <worktree>`, never inherited cwd — and
  **before any write assert** `git -C <worktree> branch --show-current` is the run branch;
  **never** main/master.
- **No merge.** The run ends at a review-ready branch.

## Resume & state

**On start, resume first.** Look for an existing **plan doc**, reconcile
worktree/branch/base_ref existence on disk, then continue from `phase`. An interrupted review
round re-runs with the whole frozen panel, on its recorded transport and round number. No plan doc → start at S1.

**Persist** for compaction: the **spec** (S2's output, or the
user-provided spec file) and the **plan doc** (task list + progress section +
RESUME block):

```
RESUME: phase=<S[1-8]> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> spec_file=<path>
```

**Keep RESUME current:** rewrite `phase=` at every phase transition and `review_round=`
each loop iteration. **Location follows the user's / project's convention** — honor
AGENTS.md / CLAUDE.md and existing repo patterns. From S6, persist RESUME, the frozen panel and
verdicts, reviewed SHA/tree, and exact commands and results (exit codes, failure counts, diagnostics)
in an ignored run note; reuse an ignored plan, or link the note from a tracked plan before
committing it for review. Resume S7/S8 only with all-PASS evidence for the current tree;
otherwise restart S6. For legacy S1–S9 plans, restart old S6–S9 at S6, keeping task progress.

## Deciding at decision points (expert council)

- At a genuine fork — two-plus viable approaches with materially different trade-offs, or a
  choice shaping architecture / data model / interface / scope, costly to reverse, or one a
  later review might miss — **convene a council**: 2–4 ad-hoc expert personas in one parallel
  subagent batch (`Task`), each returning a concise position
  (recommendation, rationale, trade-offs, dissent). You **synthesize, decide, and record** a
  brief decision (see **Progress log format**) — the decider, breaking ties.
- Otherwise decide solo and record (a wrong guess is caught by review). Never fabricate
  personas to hit a count — fewer than two real lenses → solo.

## Review rounds (S3 & S6)

- **Select & compose.** Run the [selector](scripts/select-panel.py) as
  `python3 scripts/select-panel.py
  --phase spec --spec-file <spec doc>` (S3) / `... --phase work --worktree <worktree>
  --base <base_ref>` (S6) → a `selected` list of `{agent, subagent_type, tier, matched}`.
  The panel = ALL `core` agents (mandatory) + the `optional` agents you judge relevant (may
  drop marginal ones). S6 includes core `autopilot:verification-reviewer`; S3 does not.
- **Freeze & log** the panel to the plan doc progress section (S6: run note if tracked;
  see **Progress log format**); reuse it every round of that phase.
- **Dispatch the whole round together**, never one at a time (the re-review too).
  Dispatch every member of the round in parallel as a subagent (`autopilot:<name>` via the Agent tool),
  each given ONLY that prompt — its run-input prompt below.
  For every S6 round, require a clean committed source worktree (`git -C <worktree>
  status --porcelain` empty); set `reviewed_sha=<HEAD>` with `git -C <worktree> rev-parse HEAD`.
  Keep it unchanged until all verdicts return; check HEAD still equals `reviewed_sha`
  and status remains empty before judging (dirty only with paths the verifier reports
  as leaked → judge normally; the fix removes them). Ordinary reviewers read source
  HEAD; the verification reviewer runs full checks in the frozen source worktree every
  round. Ordinary reviewers leave full checks to it. Each
  member gets a run-input prompt — "PHASE=<spec|work>.
  Inputs: worktree=…, base_ref=…, spec_doc=…, plan_doc=…, requirement=…, focus=…,
  reviewed_sha=<HEAD> (S6 only). Output ONLY the verdict, no extra prose."
  A re-reviewed lens's prompt adds its prior items (`<lens>#<n> "<gist>"`, from the
  persisted gists); S6 also adds the fix diff `git -C <worktree> diff <pre-fix HEAD>..HEAD` (record HEAD
  before each fix).
  - **Workflow (default):** one call per round —
    `Workflow({name: "autopilot:autopilot-review-round", args: {phase: "<spec|work>", members: [{agent, subagent_type, prompt}, …]}})`
    → `{phase, verdicts: [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}, …]}` in member
    order (never pass `resumeFromRunId`). A `synthetic: true` member is re-dispatched once
    as a fresh subagent (`Task`) with its prompt; still no verdict → FAIL.
  - **Task (fallback):** if `Workflow` is unavailable or the call fails, dispatch the same members fresh as
    one parallel subagent batch (`Task`) with the same prompts, and stay on that fallback for the phase (freeze
    line `->Task` or `-><actual native tool>`). PASS only with no BLOCKING; no or unparseable verdict → FAIL.
- **Wait for every verdict** — never poll or judge early. Inspect the verifier's raw
  BLOCKING items before adding item IDs: `VERIFICATION_UNAVAILABLE:` (after its one
  retry) triggers Safety stop 3. Otherwise ONE fix over all blockers, then ONE re-review.
- **Item IDs:** before deduping for the fixer, label each item `<lens>#<n>` — numbered per
  lens across the phase, never reused; a repeated OPEN item keeps its ID (reviewers prefix it).

**Ralph loop:** review → fix → re-review until the frozen panel all-PASSes.
S3 spec review and S6 work review each allow **3 total rounds** by default;
change a phase's cap for this run only when the invoking requirement says so.

- **Round 1** (`r1`) = full frozen panel. Fix/re-reviews are Round 2 (`r2`) and
  Round 3 (`r3`); the initial review counts toward the cap.
- **Re-review:** S3 = the full panel on the whole spec. S6 = the lenses that failed last
  round plus every core lens; the rest carry their PASS.
- **Advance** when every lens is PASS with no open BLOCKING (S3→S4, S6→S7). Cap hit →
  Safety stop 2. Never override a reviewer's verdict — never downgrade a blocker or mark an
  item INVALID yourself.

<!-- progress-log-format:start -->
## Progress log format

The plan doc's progress section (S6: ignored run note if tracked) is a short-entry audit log, not a transcript: one entry per
panel freeze, S5 task done, review round and decision, in the shapes below (`S3` rounds use
the `S6` shapes), plus the final residual NON-BLOCKING items. The per-lens blocker gists prime
re-reviewed lenses.

- **Panel freeze:** `S6 panel: core=[correctness,requirement-fidelity,doc,verification] +optional=[code-quality] transport=Workflow` (append `->Task` or `-><actual native tool>` if the fallback fires).
- **Task done:** `S5 task 3 done: <commit sha>`.
- **Review round** (VERDICT roll-up + a concise gist per blocker, with item IDs): `S6 r1 @<reviewed_sha>: correctness=FAIL verification=PASS (command=<cmd>, exit code=0, failures=0) -> correctness#1 off-by-one in slice bound; fix dispatched`.
- **Decision** (council or solo): `decision(<topic>): chose X over Y - <short reason>; dissent: <one phrase | none>`.
<!-- progress-log-format:end -->

## Pipeline (S1–S8)

**Spec-file mode:** record `spec_file=<abs path>` in RESUME.

**The pipeline**
- **S1 — worktree.**
  - If already in an isolated worktree (not on `main`/`master`), reuse it — do not nest another. `base_ref` is current local HEAD.
  - Else resolve the requirement's host-specific `<branch>` before lookup or creation; use this same resolved branch for worktree reuse and resume:
    - `<prefix>` = the ticket ID when the work is for one single ticket (e.g. Linear `TASK-123`), else `autopilot`.
    - `<slug>` = `input` lowercased, non-alphanumerics → hyphens, collapsed to <=40 chars; with a ticket prefix, a short feature description instead (not the ticket ID again).
    - Follow repo worktree/branch conventions, otherwise the session defaults above. Ensure the worktree directory is gitignored.
    - If this requirement's resolved `<branch>` exists from a prior run, reuse it with its commits — do not create a numbered one: enter its worktree (`git worktree list`; if none, `git worktree add <path> <branch>`), `base_ref` = `git merge-base HEAD <branch>`; a plan doc there → resume from it.
    - Else create worktree on local HEAD, then enter:
      - On collision with another requirement's worktree/branch: retry with a uniquified slug (`-2`, …) and resolve `<path>` and `<branch>` again.
      - Use an exposed host worktree tool only if it honors the exact local HEAD base and resolved branch; otherwise `git worktree add <path> -b <branch> HEAD`. Use the absolute worktree directory for commands and workers.
  - Switch into the worktree; run every later command there (`EnterWorktree({path: <path>})`).
  - Create the **plan doc** (with RESUME + progress section) at location per the project's convention. Record `worktree`, `branch`, and `base_ref` (HEAD) in the RESUME block.
- **S2 — spec. (Skipped in spec-file mode)** Write the spec into the spec doc per
  [spec.md](spec.md); read the affected code first. A genuine fork → the expert
  council (**Deciding at decision points**); never ask the user.
- **S3 — spec review. (Skipped in spec-file mode)** Run the S3 review loop (see **Review
  rounds**) over the spec. **Fixes:** the orchestrator edits the spec doc directly. Root
  contradiction → Safety stop 4.
- **S4 — task list.** Write the task list yourself (invoke no planning skill): a code-free
  task list into the plan doc's implementation-plan section:
  - Header: spec path; Global Constraints (exact values producers need). Put the full
    verify command outside the task-list header, in the plan doc progress section.
  - Per task, a `### Task N: <name>` heading (its S5 producer reads its brief by it) with:
    Files; Consumes/Produces (exact names/signatures crossing tasks); tests to write
    first, incl. edge cases; the checks it runs (only those its change affects, never a
    full suite: the S6 verification reviewer runs that); commit message.
  - The task list is the plan doc's last section; the progress section, RESUME block and
    any verification notes go above it (a brief runs to the next Task heading).
- **S5 — produce.** Code → per S4 task, in order from the first not `done`, dispatch one
  fresh producer subagent on the task list header and its `### Task N` brief: tests first,
  then the code; run only the checks its brief names that cover its changed files (never
  the full verify command or full suite); commit
  with the brief's message; log the task `done`. Non-code → producer subagents. The
  orchestrator never edits the work product itself.
- **S6 — work review.** Run the review loop above; genuine check failures block.
  **Fixes:** the first fix dispatches ONE fresh producer subagent primed with the deduped
  open blockers (with item IDs) + cited files only; later fixes continue the same
  subagent by its id (`SendMessage`); use a continuation that starts it when idle
  (unknown ID / error → fresh producer, whose ID replaces the recorded one). Docs are part
  of S6. Each fix producer runs only checks covering the files it changes; the fix producer
  must commit all product changes before re-review under the dispatch rules above.
- **S7 — squash.** Idempotent squash to one commit (skip if already exactly 1
  ahead of `base_ref`). Working notes (spec/plan/progress) are committed or ignored per the
  project's convention — do not force either. Require a clean worktree and matching
  `git rev-parse HEAD^{tree}` / `git rev-parse <reviewed_sha>^{tree}` before S8; if
  trees differ, return to S6.
- **S8 — finish.** Inline (no skill): report review history, final verification evidence
  from the run note, decisions, deferred non-blockers (stop-reason first if stopped);
  offer integration options as an informational report menu, NOT a question.

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on the cases below.
1. **Destructive op — unless the session runs with automatic approval (Claude: Auto Mode).**
   Before any force-push, write outside the worktree, history rewrite beyond this branch,
   or rm/reset of uncommitted work, stop and hand off the state and exact next step.
   Follow the session's permission rules; report a denied action and its reason.
2. **Non-convergence at cap** — a Ralph loop hits `cap` (with the classification).
3. **Non-review phase failure / missing required capability** — one retry, then STOP
   with the failure or missing capability and exact next step; never replace a required worker yourself.
4. **Root-contradiction** — the core requirement asks for two things that cannot both be
   true: quote the two clauses; record the handoff in the plan doc. Mere vagueness is
   decided, not stopped.

## Result handoff (always emit last)

On **every** terminal path — S8 finish AND any safety-stop handoff — emit as the final
output exactly one fenced `autopilot-result` block (one JSON object) so a caller consumes
the outcome without parsing prose:

```autopilot-result
{ "status": "converged", "branch": "<prefix>-<slug>", "base_ref": "<sha>", "head": "<sha>", "blockers": [], "reason": "" }
```

- `status` — `converged` (reached S8) | `capped-without-pass` (a Ralph loop hit its cap) | `stopped` (any other safety stop).
- `branch` / `base_ref` / `head` — branch name, its base SHA, its final commit SHA (`head` = `base_ref` if nothing was produced).
- `blockers` — residual open BLOCKING items (strings) when `status != converged`, else `[]`.
- `reason` — empty when converged; else classification + detail (cap → oscillation | unfixable | requirements-conflict; stop → root-contradiction | phase-failure | destructive-op).
