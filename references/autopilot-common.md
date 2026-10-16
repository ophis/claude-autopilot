# Autopilot common rules

Rules `build` and `light-build` share; the calling SKILL.md owns its pipeline and settings.
Paths here are relative to this file's directory.

## Terms

- **Input**: `input` is Claude Code's substituted `$ARGUMENTS`, or Codex's invoking user
  request or explicit caller input. An unresolved placeholder counts as absent. It is the
  single source of intent; the skill lists its forms.
- **Publish**: `publish=pr|ci|none`, set at S1 (Publish).
- **Genuine fork**: two or more viable approaches with materially different trade-offs,
  or a choice that shapes architecture, data model, interface or scope, is costly to
  reverse, or that a later review might miss. A question a quick run can answer is not
  one: run it and log it, per the council's first step (Council).

## Disciplines

- **Decide everything yourself** (Council). Never ask the user anything. Every stop is a
  handoff, not a question.
- **Author the work; let reviewers judge it.** You implement the S5 tasks and the S6 fixes
  yourself. Independent reviewer subagents judge the result.
- **Guard your context.** Read only what the current step needs. Send long command output
  to a file and read bounded slices of it. Hand bulk searches and reads to a subagent and
  keep its summary.
- **Targeted checks.** Your own checks (tasks, fixes, merges) cover only the files you
  changed; the full suite is the verifier's.
- **Real exit codes.** A command whose exit code decides anything (check, commit, push)
  runs unpiped, output to a file, or after `set -o pipefail`: `tests | tail -2 && git
  commit` commits a failing test.
- **Brief workers fully.** Give every worker the absolute worktree path and branch,
  bundled paths resolved to absolute, and the target repo's applicable AGENTS.md /
  CLAUDE.md paths and constraints.
- **Pin every write to the worktree.** You and every worker use absolute paths and
  `git -C <worktree>`, never the inherited cwd. Before any write, assert `git -C <worktree> branch --show-current` is the run branch, never
  a default branch (Worktree (S1)).
- **Batch steps.** Every tool call re-sends your whole context. Combine independent shell
  steps into one command, and make independent calls together in one parallel batch.
- **Never merge.**

## Hosts

- Tool names in parentheses are Claude Code forms. On another host, use the session's
  exposed equivalent.
- Request fresh context for each worker when the host supports it.

## State and resume

- **Plan doc.** Each run keeps all its state in one plan doc,
  `<worktree>/.autopilot/<slug>-plan.md`, created at S1 where the resolver names it
  (Worktree (S1)). The `.autopilot/` directory holds a `.gitignore` of `*`, so writing
  the plan doc never dirties the worktree. In order, the plan
  doc holds the line `Rules: <abs SKILL.md path> <abs path of this file> <abs path of review-round.md>`, RESUME as the
  second line, `input` verbatim, the full verify command once known (with its `CI checks:`
  line when publishing), the progress log, the review items, Notes, and the task list last
  (from S4).
- **RESUME** is one line, rewritten at every phase change and loop iteration:
  `RESUME: phase=<step|done> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> input_sha=<sha>`,
  plus `spec_file=<path>` when the skill records one. Publish state lives with `pr.py`
  (Publish).
- **Resume first.** On start, run the resolver (Worktree (S1)) before anything else.
  `mode: resume` points at this input's unfinished plan doc, matched by RESUME
  `input_sha`; a plan doc for another input, or at `phase=done`, is an earlier run's and
  stays untouched. Check that its worktree, branch and base_ref exist on disk, then
  continue from its `phase`. Any other mode starts S1.
- **Review items.** Every round's items, per review-round.md (Log).
- **Notes.** Write each durable fact you learn to Notes as one line: key files and entry
  points, repo patterns and commands, gotchas, and anything a later task depends on. A
  context summary drops these; the plan doc keeps them.

### Re-hydrate after compaction

After a context compaction, or whenever you are unsure of the run's state, rebuild it
from disk before you act. Re-read the plan doc whole (Resume first), the files on its `Rules:`
line (gone: find them in the installed plugin), and any spec doc.
Run `pr.py status --plan-doc <plan_doc>`, `git -C <worktree> log --oneline <base_ref>..HEAD` and `git -C <worktree> status`; a
commit carrying a task's brief message means that task is done (log it if unmarked).
Finish unfinished work, then continue from RESUME `phase`:

- **S5**: uncommitted changes belong to the first task not `done`. Finish or redo it.
- **S3**: if the latest round failed, the spec doc on disk holds any partial fix. Finish
  it against that round's full BLOCKING items, then run the re-review.
- **S6**: uncommitted changes are the fix in progress: finish it against the latest
  round's review items, with that round's `reviewed_sha` as the pre-fix HEAD, commit, then
  run the re-review. A clean tree with HEAD past that `reviewed_sha` means the fix is
  committed: run the re-review. A clean tree with HEAD at that `reviewed_sha` and every
  lens passing means the phase converged: advance.

## Progress log

A short audit log in the plan doc, one line per event, not a transcript.

- Panel freeze and review rounds: per review-round.md (Log).
- Task done: `S5 task 3 done: <commit sha> red=<tests failing before the code, or none>`.
- Fork and decision: the council's lines (Council); a solo decision has no `tally`.
- Deferred pattern match outside the change: `deferred(<pattern>): <file:line>`.
- At the end: the residual NON-BLOCKING items.

## Council

At a genuine fork, run the council per [`../skills/council/SKILL.md`](../skills/council/SKILL.md),
with `input` as the requirement, the worktree as the repo and the plan doc's progress log
as the log. Brief workers fully does not apply to members. You decide everything
yourself, including a question members flag as the user's call.

Outside a genuine fork, decide solo and log it. Review catches a wrong guess.

## Worktree (S1)

Write `input` verbatim to a temporary file with the file-write tool, never through the
shell, and run the resolver from the starting checkout:

```
python3 <abs path of ../scripts/resolve-branch.py> --host <claude|codex> --input-file <file>
```

When the work is for one ticket, add `--prefix '<ticket ID>'` and
`--slug '<short-feature-slug>'`. A repo
whose AGENTS.md / CLAUDE.md says where worktrees go or names a branch namespace passes
`--worktree-root '<dir>'` and `--branch-prefix '<ns/>'`. Single-quote every value taken
from the requirement or the repo's docs. A **default branch** is `main`, `master` or `origin`'s default; on any other
branch the run stays on it, which is how a later requirement continues an earlier run's
branch. Act on `mode`:

- `resume`: continue the plan doc at `plan_doc` (State and resume).
- `stay`: work in this checkout on its branch.
- `reuse`: enter the branch's worktree, after `git worktree prune` and
  `git worktree add <worktree> <branch>` if it has none.
- `create`: run `git worktree add <worktree> -b <branch> HEAD`, or a host worktree tool
  only if it honors the exact local HEAD and branch. Keep the worktree directory
  gitignored.
- `stop`: take safety stop 3 with its `reason`; uncommitted changes there are the user's.

For `reuse` and `create`, enter the worktree (`EnterWorktree({path: <worktree>})`). Run
every later command in the worktree. Unless resuming, write `.autopilot/.gitignore` (`*`)
in it, then create the plan doc at `plan_doc` (State and resume) with `resume_line` as its
RESUME. Then run `pr.py start` (Publish).

## Task list (S4)

Write the task list yourself and invoke no planning skill. It is code-free and is the
plan doc's last section. The skill says what else goes in its header; the full verify
command never does.

- **Header**: Global Constraints (exact values the tasks need), and when publishing the
  PR a continued branch updates (Publish).
- **CI checks** (when publishing): under the plan doc's verify command,
  `CI checks: [<names>]`, a JSON array of the CI checks that run its tests, from the
  repo's CI config. Names as GitHub shows them: job `name`, else id; a glob (`test*`)
  covers matrix jobs. `CI checks: []` if none runs them.
- **One task is one commit** that can be reverted on its own: one purpose (a behavior
  change with its tests, or one mechanical change such as a rename, move, reformat or
  generated update, never both), split by behavior rather than layer, ordered so removals
  and prep come first. Split a task that mixes purposes; fold one with no purpose of its
  own into the task it serves.
- **One `### Task N: <name>` heading per task.** A brief runs to the next task heading,
  so a producer can be handed one alone. Each brief lists:
  - Files.
  - Consumes / Produces: exact names and signatures that cross tasks.
  - Tests to write first, including edge cases.
  - The checks it runs (Targeted checks).
  - Commit message.

## Produce (S5)

For each task, starting from the first one not `done`:

1. Implement it yourself from its `### Task N` brief: tests first, run red (each new test
   fails because the behavior is missing, not because the test is broken), then the code.
2. Run the checks its brief names.
3. Commit with the brief's message. In `publish=pr` with checks named in `CI checks:`,
   first peek at the CI of the last pushed commit, which ran while you wrote this task
   (none before the first push): with `<sha>` from
   `git -C <worktree> rev-parse @{upstream}`, run
   `python3 <abs path of ../scripts/ci-verdict.py> --worktree <worktree> --sha <sha> --plan-doc <plan_doc> --wait 0 --appear 0 --interval 0`.
   Exit 1: fix the printed failures (S6 fixes) in one more commit,
   `fix(ci): <check names>`. Exit 5: merge the base as in Publish (Conflicts), with no
   round to re-run. Any other exit: go on. Then run `pr.py push --task` (Publish), add
   Notes for anything a later task needs, and log the task `done`.

**Delegation.** You may hand a self-contained task that would flood your context, such as
a bulk mechanical edit or a large isolated module, to one fresh producer. Give it the task
list header, its `### Task N` brief and what the skill adds (Brief workers fully). The producer follows steps 1 and 2, commits, and returns its red count and any
Notes lines for you to record. You confirm the commit, then finish step 3. If the
producer fails, implement the task yourself.

A producer never consults the council. At a genuine fork, it stops and returns:

```
FORK: <one-line question>
- option A: <terse description + trade-off>
- option B: <terse description + trade-off>
```

Then you run the council on it (Council) and re-dispatch the producer with the decision
in its prompt: `DECISION: <chosen option + one-line rationale>; proceed — do not re-fork on this`.

## Review round

Run review rounds per [review-round.md](review-round.md), with the skill's panel, cap,
re-review set, doc fields and freeze line. Freeze and round lines go to the progress log,
items to the review items. When every lens
passes, advance. At the cap without a pass, take safety stop 2.

## S6 fixes

Fix the code yourself, per review-round.md (The fix), and:

- Record HEAD before each fix; the re-review diff starts there.
- Fix causes, not symptoms. Reproduce each blocker first (run its case where one exists,
  else trace it) and fix it where it originates. Fix the same pattern within the change's
  scope; log matches outside it as `deferred` lines for the S7 report. A guard that
  silences a symptom is not a fix.
- Commit the round's fix as one commit, `fix(r<N>): <item IDs>`, before the re-review. The re-review then pins it.

## Publish

With CI, the repo's CI verifies the work, never a local full-suite run, so the run
publishes its branch as a draft PR. `python3 <abs path of ../scripts/pr.py>`
does every `gh` step and keeps the state beside the plan doc. Each call prints
`{publish, pr, …, reason}`; exit 3 is safety stop 3 with that reason.

- **Start (S1).** Write the PR title (first line) and body from the requirement to a file
  with the file-write tool. Run `pr.py start --plan-doc <plan_doc> --worktree <worktree>
  --body-file <file>`, adding `--requested` when the requirement asks for a pull request
  and `--base '<branch>'` when it names one. `publish` is `pr` (asked), `ci` (a
  pull_request workflow and an authenticated `gh`) or `none`. A `pr` in its output is the
  branch's open PR: log it as a decision and name it in the task-list header at S4.
- **Push.** `pr.py push --plan-doc <plan_doc>`, with `--task` after an S5 task commit. A
  refused push in `ci` returns `publish=none` with the reason: log `decision(publish)` and
  verify locally from then on.
- **Spec** (build). `pr.py spec --plan-doc <plan_doc> --spec-doc <spec doc>` at S4.
- **Conflicts.** A `CONFLICT:` from the PR peek before a round, or from the verifier,
  means the PR conflicts with its base, so CI will not run. With `<base>` from that line: `git -C <worktree> fetch origin <base>`,
  `git -C <worktree> merge origin/<base>` (never rebase), resolve, run targeted checks,
  commit. Set RESUME `base_ref` to `git -C <worktree> merge-base HEAD origin/<base>`, so
  reviewers see only this run's changes. `pr.py push`, re-pin, and re-run the round like an
  interrupted one (review-round.md). Unresolvable: `git -C <worktree> merge --abort`, then safety stop 3
  naming the conflicting files.
- **Finish.** On convergence, write the S7 report to a file and run
  `pr.py finish --plan-doc <plan_doc> --report-file <file>`. Report the URL.

## Finish (S7)

Require a clean worktree with HEAD equal to the last all-PASS `reviewed_sha`; otherwise
return to S6. The branch keeps its task and fix commits. On convergence, finish the PR
(Publish). If the user's or project's convention (AGENTS.md / CLAUDE.md) keeps plans or specs
somewhere, copy the plan doc and any spec doc there. Report inline, with no skill: the
review history, the final verification evidence from the plan doc, the decisions and `omitted` lines, and the deferred non-blockers and `deferred` lines. On a
stop, lead with the stop reason. List the integration options, a squash merge
(`git merge --squash`) among them, as an informational menu, not a question. On
convergence, set RESUME `phase=done` before the result block.

## Safety stops

Stop and hand off the state and exact next step, recorded in the progress log, only in
these cases:

1. **Destructive op**, unless the session runs with automatic approval (Claude: Auto
   Mode): any force-push, write outside the worktree, history rewrite beyond this branch,
   or rm/reset of uncommitted work. Follow the session's permission rules, and report a
   denied action with its reason.
2. **Non-convergence at the cap**, with its classification.
3. **Non-review phase failure or missing required capability**: retry once, then stop
   with the failure or missing capability. Never act as your own reviewer or verifier.
4. **Root contradiction**: the core requirement asks for two things that cannot both be
   true. Quote the two clauses. Vagueness is not a contradiction; decide it.

## Result handoff

On every terminal path, S7 or any safety stop, end with exactly one fenced
`autopilot-result` block holding one JSON object, so a caller reads the outcome without
parsing prose:

```autopilot-result
{ "status": "converged", "branch": "<prefix>-<slug>", "base_ref": "<sha>", "head": "<sha>", "pr": "", "blockers": [], "reason": "" }
```

- `status`: `converged` (reached S7), `capped-without-pass` (a review loop hit its cap),
  or `stopped` (any other safety stop).
- `branch`, `base_ref`, `head`: the branch name, its base SHA, and its final commit SHA
  (`head` = `base_ref` if nothing was produced).
- `pr`: the run's pull request URL (`pr.py status`), else empty. With `publish=ci` it is a
  draft; a caller that opens the final PR adopts and updates it.
- `blockers`: the residual open BLOCKING items as strings when not converged, else `[]`.
- `reason`: empty when converged. Otherwise the classification plus detail: for a cap,
  `oscillation`, `unfixable` or `requirements-conflict`; for a stop, `root-contradiction`,
  `phase-failure` or `destructive-op`.
