---
name: build
description: "Use to build a new work product from a requirement, end to end: create an isolated worktree, write and review a spec, write a task list, implement, and review-loop with mandatory verification to a single review-ready branch (never merges). Pass the requirement text, or a path to an existing spec file."
argument-hint: "<requirements|spec-file-path>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, SendMessage, Workflow, Skill, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite, ScheduleWakeup
---

# Autopilot: build

Autonomous build run. Drive the pipeline end to end: dispatch and judge.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent:

- **Requirements mode (default):** free-text requirements → full pipeline.
- **Spec-file mode:** if `$ARGUMENTS` is the path of an **existing spec file**, **skip S2
  and S3**. The spec must be **self-contained** — enough to plan, implement, and verify
  without further clarification.

Empty input → STOP.

## Preflight

- **Load config:** `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. It prints the effective config, including the per-phase Ralph caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase`.

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

**On start, resume first.** Look for an existing **plan doc**, reconcile
worktree/branch/base_ref existence on disk, then continue from `phase`. An interrupted review
round re-runs with the whole frozen panel, on the transport its freeze line records; only
`review_round` need be persisted to locate the loop. No plan doc → start at S1.

**Persist two things** so the run survives compaction: the **spec** (S2's output, or the
user-provided spec file) and the **plan doc** (task list + progress section +
RESUME block):

```
RESUME: phase=<S1|S2|S3|S4|S5|S6|S7|S8> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> spec_file=<path>
```

**Keep RESUME current:** rewrite `phase=` at every phase transition and `review_round=`
each loop iteration. **Location follows the user's / project's convention** — honor
CLAUDE.md and existing repo patterns.
For legacy S1–S9 plans, restart old S6/S7 at new S6; map old S8→S7 and S9→S8.

In the plan doc progress section, keep the full verify command and latest reviewed
SHA, command results (exit codes, failure counts, diagnostics). Evidence expires when
HEAD changes; resume an interrupted S6 round with its whole frozen panel.

## Deciding at decision points (expert council)

- At a genuine fork — two-plus viable approaches with materially different trade-offs, or a
  choice shaping architecture / data model / interface / scope, costly to reverse, or one a
  later review might miss — **convene a council**: 2–4 ad-hoc expert personas in one parallel
  batch, each returning a concise position
  (recommendation, rationale, trade-offs, dissent). You **synthesize, decide, and record** a
  brief decision (see **Progress log format**) — the decider, breaking ties.
- Otherwise decide solo and record (a wrong guess is caught by review). Never fabricate
  personas to hit a count — fewer than two real lenses → solo.

## Review rounds (S3 & S6)

- **Select & compose.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py"
  --phase spec --spec-file <spec doc>` (S3) / `... --phase work --worktree <worktree>
  --base <base_ref>` (S6) → a `selected` list of `{agent, subagent_type, tier, matched}`.
  The panel = ALL `core` agents (mandatory) + the `optional` agents you judge relevant (may
  drop marginal ones). S6 includes core `autopilot:verification-reviewer`; S3 does not.
- **Freeze & log** the panel to the **plan doc** progress section (see **Progress log
  format**); reuse it every round of that phase.
- **Dispatch the whole round together** — never one at a time, re-reviews included. Before
  each S6 round, require a clean committed source worktree (`git -C <worktree> status --porcelain`
  empty), set `reviewed_sha=<HEAD>` from `git -C <worktree> rev-parse HEAD`, and keep
  source unchanged until every verdict returns. Check HEAD still equals `reviewed_sha`
  and status is still empty before judging.
  Every S6 member gets the same fixed revision: ordinary reviewers read source HEAD;
  the verification reviewer clones reviewed_sha into its isolated checkout. Each
  member is `autopilot:<name>` and gets ONLY a run-input prompt — "PHASE=<spec|work>.
  Inputs: worktree=…, base_ref=…, spec_doc=…, plan_doc=…, requirement=…, focus=…,
  reviewed_sha=<HEAD> (S6 only). Output ONLY the verdict, no extra prose." (absolute
  paths; ordinary reviewers read the source worktree, never main). The verification
  reviewer reads the plan doc's full verify command; ordinary reviewers leave full
  checks to it. A re-reviewed lens's prompt adds its prior items (`<lens>#<n> "<gist>"`, from the
  persisted gists); S6 also adds the fix diff `git -C <worktree> diff <pre-fix HEAD>..HEAD` (record HEAD
  before each fix).
  - **Workflow (default):** one call per round —
    `Workflow({name: "autopilot:autopilot-review-round", args: {phase: "<spec|work>", members: [{agent, subagent_type, prompt}, …]}})`
    → `{phase, verdicts: [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}, …]}` in member
    order (never pass `resumeFromRunId`). A `synthetic: true` member is re-dispatched once
    via `Task` with its prompt; still no verdict → FAIL.
  - **Task (fallback):** if the `Workflow` call fails, dispatch the same members fresh as
    one parallel `Task` batch with the same prompts, and stay on Task for the phase (freeze
    line `->Task`). PASS only with no BLOCKING; no or unparseable verdict → FAIL.
- **Wait for every verdict** — never poll or judge early. After every verdict is in,
  inspect the verification reviewer's raw BLOCKING items before adding item IDs;
  `VERIFICATION_UNAVAILABLE:` at the start of an item triggers Safety stop 3;
  do not dispatch a code fixer for an unavailable environment or tool. Otherwise make
  ONE fix over all open blockers, then ONE re-review round.
- **Item IDs:** before deduping for the fixer, label each item `<lens>#<n>` — numbered per
  lens across the phase, never reused; a repeated OPEN item keeps its ID (reviewers prefix it).

**Ralph loop:** review → fix → re-review until the frozen panel all-PASSes, capped by
`ralphLoop.maxIterations.spec-phase` / `.implementation-phase` (default 3, from config).

- **Round 0** = full frozen panel; all-PASS short-circuits.
- **Re-review:** S3 = the full panel on the whole spec. S6 = the lenses that failed last
  round plus every core lens; the rest carry their PASS.
- **Advance** when every lens is PASS with no open BLOCKING (S3→S4, S6→S7). Cap hit →
  Safety stop 2. Never override a reviewer's verdict — never downgrade a blocker or mark an
  item INVALID yourself.

<!-- progress-log-format:start -->
## Progress log format

The plan doc's progress section is a short-entry audit log, not a transcript: one entry per
panel freeze, S5 task done, review round and decision, in the shapes below (`S3` rounds use
the `S6` shapes), plus the final residual NON-BLOCKING items. The per-lens blocker gists prime
re-reviewed lenses.

- **Panel freeze:** `S6 panel: core=[correctness,requirement-fidelity,doc,verification] +optional=[code-quality] transport=Workflow` (append `->Task` if the fallback fires).
- **Task done:** `S5 task 3 done: <commit sha>`.
- **Review round** (VERDICT roll-up + a concise gist per blocker, with item IDs): `S6 r0 @<reviewed_sha>: correctness=FAIL verification=PASS (command=<cmd>, exit code=0, failures=0) -> correctness#1 off-by-one in slice bound; fix dispatched`. Record useful verification diagnostics when a command fails.
- **Decision** (council or solo): `decision(<topic>): chose X over Y - <short reason>; dissent: <one phrase | none>`.
<!-- progress-log-format:end -->

## Pipeline (S1–S8)

**Spec-file mode:** record `spec_file=<abs path>` in RESUME.

**The pipeline**
- **S1 — worktree.**
  - If already in an isolated worktree (not on `main`/`master`), reuse it — do not nest another. `base_ref` is current local HEAD.
  - Else, if this requirement's `<prefix>-<slug>` branch (below) exists from a prior run, reuse it with its commits — do not create a numbered one: enter its worktree (`git worktree list`; if none, `git worktree add <path> <branch>`), `base_ref` = `git merge-base HEAD <branch>`; a plan doc there → resume from it.
  - Else create worktree on local HEAD, then enter:
    - `<prefix>` = the ticket ID when the work is for one single ticket (e.g. Linear `TASK-123`), else `autopilot`.
    - `<path>` = `.claude/worktrees/<prefix>-<slug>`, ensure `.claude/worktrees/` is gitignored (add it to `.gitignore` if not)
    - `<slug>` = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens, collapsed to <=40 chars; with a ticket prefix, a short feature description instead (not the ticket ID again). On collision with another requirement's worktree/branch: retry with a uniquified slug (`-2`, …).
    - `git worktree add <path> -b <prefix>-<slug> HEAD`
    - `EnterWorktree({path: <path>})`
  - Create the **plan doc** (with RESUME + progress section) at location per the project's convention. Record `worktree`, `branch`, and `base_ref` (HEAD) in the RESUME block.
- **S2 — spec. (Skipped in spec-file mode)** Write the spec into the spec doc per
  `${CLAUDE_SKILL_DIR}/spec.md`; read the affected code first. A genuine fork → the expert
  council (**Deciding at decision points**); never ask the user.
- **S3 — spec review. (Skipped in spec-file mode)** Run the S3 review loop (see **Review
  rounds**) over the spec. **Fixes:** the orchestrator edits the spec doc directly. Root
  contradiction → Safety stop 4.
- **S4 — task list.** Write the task list yourself (invoke no planning skill): a code-free
  task list into the plan doc's implementation-plan section:
  - Header: spec path; Global Constraints (exact values producers need). Put the full
    verify command outside the task-list header, in the plan doc progress section,
    so the verification reviewer can read it by `plan_doc` reference.
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
- **S6 — work review.** Run the review loop above; complete checks run in parallel
  through the mandatory verification reviewer, and genuine failures block.
  **Fixes:** the first fix dispatches ONE fresh producer subagent primed with the deduped
  open blockers (with item IDs) + cited files only; later fixes continue it via `SendMessage`
  (unknown ID / error → fresh producer, whose ID replaces the recorded one). Docs are part
  of S6. Each fix producer runs only checks covering the files it changes; the fix
  producer must commit all product changes.
  After the fix, require empty `git -C <worktree> status --porcelain` and confirm
  `git -C <worktree> rev-parse HEAD` is the new committed SHA before re-review.
  The verifier repeats full checks each round; `VERIFICATION_UNAVAILABLE:` after its
  one retry is a safety stop.
- **S7 — squash.** Idempotent squash to one commit (skip if already exactly 1
  ahead of `base_ref`). Working notes (spec/plan/progress) are committed or ignored per the
  project's convention — do not force either.
- **S8 — finish.** Inline (no skill): report
  review history and final verification evidence (reviewed SHA, commands, exit codes,
  failure counts and useful diagnostics), decisions, deferred non-blockers
  (stop-reason first if the run stopped);
  offer integration options as an informational report menu, NOT a question. NO merge.

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on the cases below.
1. **Destructive op — only when Auto Mode (auto-accept / bypass-permissions) is OFF.**
   Before any force-push, write outside the worktree, history rewrite beyond this branch,
   or rm/reset of uncommitted work.
2. **Non-convergence at cap** — a Ralph loop hits `cap` (with the classification).
3. **Non-review phase failure** — one retry, then STOP.
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
