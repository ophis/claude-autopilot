# Autopilot common rules

The rules `build` and `light-build` share. The calling SKILL.md owns the pipeline and its
settings; this file owns everything both surfaces do the same way. Paths here are relative
to this file's directory.

## Terms

- **Input**: `input` is Claude Code's substituted `$ARGUMENTS`, or Codex's invoking user
  request or explicit caller input. An unresolved placeholder counts as absent. It is the
  single source of intent; the skill lists its forms.
- **Plan doc**: the run's one state file (see State and resume).
- **Producer**: a fresh subagent you hand one self-contained task to (see Produce (S5)).
- **Lens**: one reviewer agent. The **panel** is the set of lenses for a phase.
- **Round**: one parallel review of the panel, numbered `r1`, `r2`, ….
- **PR mode**: the requirement asks you to open a pull request (see PR mode).
- **Genuine fork**: two or more viable approaches with materially different trade-offs,
  or a choice that shapes architecture, data model, interface or scope, is costly to
  reverse, or that a later review might miss.

## Disciplines

- **Decide everything yourself.** Never ask the user anything. Settle a genuine fork with
  the council, anything else solo. Every stop is a handoff, not a question.
- **Author the work; let reviewers judge it.** You implement the S5 tasks and the S6 fixes
  yourself. Independent reviewer subagents judge the result.
- **Guard your context.** Read only what the current step needs. Send long command output
  to a file and read bounded slices of it. Hand bulk searches and reads to a subagent and
  keep its summary.
- **Brief workers fully.** Give every worker the absolute worktree path and branch,
  bundled paths resolved to absolute, and the target repo's applicable AGENTS.md /
  CLAUDE.md paths and constraints.
- **Pin every write to the worktree.** You and every worker use absolute paths and
  `git -C <worktree>`, never the inherited cwd. Before any write, assert `git -C <worktree> branch --show-current` is the run branch, never
  a default branch (Worktree (S1)).
- **Batch steps.** Every tool call re-sends your whole context. Combine independent shell
  steps into one command, and make independent calls together in one parallel batch.
- **End at a review-ready branch.** Never merge.

## Hosts

- Tool names in parentheses are Claude Code forms. On another host, use the session's
  exposed equivalent.
- Request fresh context for each worker when the host supports it.
- On Claude Code, dispatch reviewer `<name>` as `autopilot:<name>` via the Agent tool. It
  keeps the `model:`, `effort:` and tools from `../agents/<name>.md`.
- Without named dispatch, give a fresh generic agent the full `../agents/<name>.md` body
  plus its run-input prompt, and keep the body's verdict grammar and tool and test limits.
  Codex always works this way: the agent inherits the session model, so pass no `model` to
  `spawn_agent`.

## State and resume

- **Plan doc.** Each run keeps all its state in one plan doc,
  `<worktree>/.autopilot/<slug>-plan.md`, created at S1 where the resolver names it
  (Worktree (S1)). The `.autopilot/` directory holds a `.gitignore` of `*`, so writing
  the plan doc never dirties the worktree. In order, the plan
  doc holds the line `Rules: <abs SKILL.md path> <abs path of this file>`, RESUME as the
  second line, `input` verbatim, the full verify command once known, the progress log, the
  review items, Notes, and the task list last (from S4).
- **RESUME** is one line, rewritten at every phase change and loop iteration:
  `RESUME: phase=<step|done> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> input_sha=<sha>`,
  plus `spec_file=<path>` when the skill records one and `pr=<url>` in PR mode.
- **Resume first.** On start, run the resolver (Worktree (S1)) before anything else.
  `mode: resume` points at this input's unfinished plan doc, matched by RESUME
  `input_sha`; a plan doc for another input, or at `phase=done`, is an earlier run's and
  stays untouched. Check that its worktree, branch and base_ref exist on disk, then
  continue from its `phase`. Any other mode starts S1.
- Re-run an interrupted review round whole: the frozen panel, on its recorded transport
  and round number.
- **Review items.** After each round, append its items in full with their IDs, BLOCKING
  and NON-BLOCKING, and the verifier's exact commands and results (exit codes, failure
  counts, diagnostics).
- Resume at S7 only with all-PASS evidence for HEAD. Otherwise restart S6.
- **Notes.** Write each durable fact you learn to Notes as one line: key files and entry
  points, repo patterns and commands, gotchas, and anything a later task depends on. A
  context summary drops these; the plan doc keeps them.

### Re-hydrate after compaction

After a context compaction, or whenever you are unsure of the run's state, rebuild it
from disk before you act:

1. Find the plan doc (Resume first) and re-read it whole. With no plan doc yet, follow
   Resume first.
2. Re-read the SKILL.md and this file from the `Rules:` paths. If a path is gone, find
   the file by skill name in the installed plugin.
3. Re-read the spec doc if the run has one.
4. Run `git -C <worktree> log --oneline <base_ref>..HEAD` and `git -C <worktree> status`.
   A commit carrying a task's brief message means that task is done; log it if the mark
   is missing.
5. Finish unfinished work before moving on:
   - **S5**: uncommitted changes belong to the first task not `done`. Finish or redo it.
   - **S3**: if the latest round failed, the spec doc on disk holds any partial fix.
     Finish it against that round's full BLOCKING items, then run the re-review.
   - **S6**: uncommitted changes are the fix in progress. Finish it against the latest
     round's review items, with that round's `reviewed_sha` as the
     pre-fix HEAD, commit, then run the re-review. A clean tree with HEAD past that
     `reviewed_sha` means the fix is committed: run the re-review. A clean tree with HEAD
     at that `reviewed_sha` and every lens passing means the phase converged: advance.
6. Continue from RESUME `phase`.

## Progress log

A short audit log in the plan doc, one line per event, not a transcript. S3 uses the S6
shapes.

- Panel freeze: the skill's freeze line, ending `transport=Workflow`. Append `->Task` or
  `-><actual native tool>` if the fallback fires. In S6 it names the verifier's backend, `verification=local` or `verification=ci`.
- Task done: `S5 task 3 done: <commit sha>`.
- Review round, with the verdict roll-up and one gist per blocker: `S6 r1 @<reviewed_sha>: correctness=FAIL verification=PASS (command=<cmd>, exit code=0, failures=0) -> correctness#1 off-by-one in slice bound; fixing`.
- Decision, council or solo: `decision(<topic>): chose X over Y - <short reason>; dissent: <one phrase | none>`.
- Deferred pattern match outside the change: `deferred(<pattern>): <file:line>`.
- At the end: the residual NON-BLOCKING items.

The blocker gists prime re-reviews; the full items are in the review items.

## Council

1. At a genuine fork, convene 2–4 ad-hoc expert personas in one parallel subagent batch
   (`Task`). Each returns a concise position: recommendation, rationale, trade-offs,
   dissent.
2. Synthesize and decide; you break ties. Log the decision.
3. Use only personas with a genuinely distinct view. With fewer than two, decide solo.

Outside a genuine fork, decide solo and log it. Review catches a wrong guess.

## Worktree (S1)

Write `input` verbatim to a temporary file with the file-write tool, never through the
shell, and run the resolver from the starting checkout:

```
python3 <abs path of ../skills/build/scripts/resolve-branch.py> --host <claude|codex> --input-file <file>
```

When the work is for one ticket, add `--prefix '<ticket ID>'` (letters, digits, `.`, `_`,
`-`) and `--slug '<short-feature-slug>'` (lowercase letters, digits and hyphens). A repo
whose AGENTS.md / CLAUDE.md says where worktrees go or names a branch namespace passes
`--worktree-root '<dir>'` and `--branch-prefix '<ns/>'`. Single-quote every value taken
from the requirement or the repo's docs.
It prints `{mode, branch, worktree, base_ref, plan_doc, spec_doc, input_sha, resume_line,
reason}`. A **default branch** is `main`, `master` or `origin`'s default; on any other
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
RESUME. In PR mode, run its S1 check (PR mode).

## Task list (S4)

Write the task list yourself and invoke no planning skill. It is code-free and is the
plan doc's last section. The skill says what else goes in its header; the full verify
command never does.

- **Header**: Global Constraints (exact values the tasks need), and in PR mode the PR a
  continued branch updates (PR mode).
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
  - The checks it runs: only those its change affects, never a full suite. The verifier
    runs that.
  - Commit message.

## Produce (S5)

For each task, starting from the first one not `done`:

1. Implement it yourself from its `### Task N` brief: the tests first, then the code.
2. Run the checks its brief names.
3. Commit with the brief's message, push in PR mode (PR mode), add Notes for anything a
   later task needs, and log the task `done`.

**Delegation.** You may hand a self-contained task that would flood your context, such as
a bulk mechanical edit or a large isolated module, to one fresh producer. Give it the task
list header, its `### Task N` brief, the worktree pin, the constraints, and what the skill
adds. The producer follows steps 1 and 2, commits, and returns any Notes lines for you
to record. You confirm the commit, then finish step 3. If the producer fails,
implement the task yourself.

A producer never consults the council. At a genuine fork, it stops and returns:

```
FORK: <one-line question>
- option A: <terse description + trade-off>
- option B: <terse description + trade-off>
```

Then you convene the council, decide, log the decision, and re-dispatch the producer with
the decision in its prompt: `DECISION: <chosen option + one-line rationale>; proceed — do not re-fork on this`.

## Review round

The skill sets the panel, the cap (total rounds, `r1` included), the re-review set, and
the doc fields of the run-input prompt.

**Verifier.** Every S6 panel includes `autopilot:verification-reviewer`. Freeze its
backend in `r1`: `verification=ci` in PR mode, else `verification=local`. With `local` it
runs the complete checks in the frozen source worktree; with `ci` it reads the repo's CI
checks for `reviewed_sha`, and runs the local checks when CI gives no usable result. It
runs every round.

Run each round in these steps:

1. **Freeze.** In `r1`, log the panel. Reuse it for every round of the phase.
2. **Pin the revision (S6).** Require a clean committed source worktree:
   `git -C <worktree> status --porcelain` is empty. Set `reviewed_sha=<HEAD>` from
   `git -C <worktree> rev-parse HEAD`. In PR mode, push it (PR mode). Leave HEAD alone
   until every verdict is back.
3. **Write prompts.** Each member gets only its run-input prompt:
   `PHASE=<spec|work>. Inputs: worktree=…, base_ref=…, <doc fields>, requirement=…, focus=…, reviewed_sha=<HEAD> (S6 only). Output ONLY the verdict, no extra prose.`
   The verifier's prompt adds `verification=<local|ci>` and, with `ci`,
   `ci_script=<abs path of ../skills/build/scripts/ci-verdict.py>`.
   `focus=` names only what the requirement, spec or a logged decision asks the lens to
   weigh. It never claims the work is correct and never narrows the lens's checklist.
   A re-reviewed lens also gets its prior items as `<lens>#<n> "<gist>"`. In S6 it also
   gets the fix diff `git -C <worktree> diff <pre-fix HEAD>..HEAD`.
4. **Dispatch all members together**, never one at a time, re-reviews included. Queue
   the rest when the host's concurrency limit is reached.
   - **Workflow (default):** one call per round,
     `Workflow({name: "autopilot:autopilot-review-round", args: {phase: "<spec|work>", members: [{agent, subagent_type, prompt}, …]}})`.
     It returns `{phase, verdicts: [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}, …]}`
     in member order. Never pass `resumeFromRunId`. Re-dispatch a `synthetic: true` member
     once as a fresh subagent (`Task`) with its prompt; if it still gives no verdict, it
     is FAIL.
   - **Native fallback:** if `Workflow` is unavailable or the call fails, dispatch the same
     members fresh as one parallel subagent batch (`Task`) with the same prompts. Stay on
     the fallback for the rest of the phase and note it in the freeze line.
5. **Wait for every verdict.** Never poll or judge early. A status message is not a verdict.
6. **Recheck the revision (S6).** HEAD still equals `reviewed_sha` and status is still
   empty. If the only dirty paths are ones the verifier reports as leaked, judge normally;
   the fix removes them. If HEAD moved, take safety stop 3 and list the new commits.
7. **Check the verifier.** Read its raw BLOCKING items before adding item IDs.
   `VERIFICATION_UNAVAILABLE:` (after its one retry) triggers safety stop 3.
8. **Label items.** Before deduping for the fix, give every BLOCKING and NON-BLOCKING
   item an ID `<lens>#<n>`, numbered per lens across the phase and never reused. A
   repeated open item keeps its ID (the reviewer prefixes it). Number only new items.
9. **Judge and log.** A lens passes with VERDICT PASS and no open BLOCKING; a missing or
   unparseable verdict is FAIL. Only the
   reviewers' own verdicts decide: never override one, downgrade a blocker, or mark an
   item INVALID yourself. Log the round.

**The loop.** `r1` runs the full frozen panel. While any lens fails and the cap allows
another round, make ONE fix over all blockers, then run ONE re-review round with the
skill's re-review set; lenses outside the set carry their PASS. When every lens passes,
advance. At the cap without a pass, take safety stop 2.

## S6 fixes

- Genuine check failures are blockers like any other.
- Record HEAD before each fix; the re-review diff starts there.
- Fix all deduped open blockers yourself in one pass, from their full text, their item
  IDs and the files they cite.
- Fix causes, not symptoms. Reproduce each blocker first (run its case where one exists,
  else trace it) and fix it where it originates. Fix the same pattern within the change's
  scope; log matches outside it as `deferred` lines for the S7 report. A guard that
  silences a symptom is not a fix.
- If an item stays OPEN after a fix, write down what that fix assumed and check the
  assumption before the next fix depends on it.
- Run only the checks covering the files you changed, and commit the round's fix as one
  commit, `fix(r<N>): <item IDs>`, before the re-review. The re-review then pins it.
- Docs are fixed here. There is no separate doc phase.

## PR mode

The run publishes its branch as a draft pull request, and the repo's CI is the verifier.

- **Check at S1.** It needs an authenticated `gh` and a GitHub `origin`; without them,
  take safety stop 3. Look up the branch's open PR
  (`gh pr list --head <branch> --state open --json url,isDraft`) and adopt it: turn a
  ready one back into a draft (`gh pr ready --undo <url>`), since an earlier run on this
  branch may have marked it ready, and record `pr=<url>` in RESUME. A run that continues
  a branch updates that PR: log it as a decision and name it in the task-list header at
  S4, so reviewers know the requirement's PR is this one.
- **Push** after each S5 task commit and at each S6 pin, so the PR shows each task as it
  lands: `git -C <worktree> push -u origin <branch>`. Never force; a rejected push is
  safety stop 3.
- **One draft PR.** Until `pr=` is recorded, repeat the S1 lookup before each push and
  adopt what it finds. With none after the push, open a draft:
  `gh pr create --draft --base '<base>' --head '<branch>' --title '<title>' --body-file <file>`,
  with the body written from the requirement with the file-write tool and a plain-words,
  quote-free title. A base the requirement names must match `[A-Za-z0-9._/-]+`; otherwise
  take safety stop 3. `<base>` is the branch the requirement names, else the repo's default
  branch. Record `pr=<url>` in RESUME.
- **Spec (build).** Post the spec doc as one PR comment
  (`gh pr comment <url> --body-file <spec doc>`) at S4 if `pr=` is recorded, else right
  after it is recorded, and log `spec posted`. Never post it twice.
- **Finish.** Converged: unless the PR body already holds it, add the S7 report, headed
  with HEAD's SHA, after any earlier run's (`gh pr view <url> --json body`, then
  `gh pr edit <url> --body-file <file>`). Then mark the PR ready (`gh pr ready <url>`).
  On a stop, leave the draft. Report the URL.

## Finish (S7)

Require a clean worktree with HEAD equal to the last all-PASS `reviewed_sha`; otherwise
return to S6. The branch keeps its task and fix commits. In PR mode, finish the PR (PR
mode). If the user's or project's convention (AGENTS.md / CLAUDE.md) keeps plans or specs
somewhere, copy the plan doc and any spec doc there. Report inline, with no skill: the
review history, the final verification evidence from the plan doc, the decisions, and the deferred non-blockers and `deferred` lines. On a
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
   with the failure or missing capability. Review round step 7 also sends an unavailable
   verifier here. Never act as your own reviewer or verifier.
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
- `pr`: the pull request URL in PR mode, else empty.
- `blockers`: the residual open BLOCKING items as strings when not converged, else `[]`.
- `reason`: empty when converged. Otherwise the classification plus detail: for a cap,
  `oscillation`, `unfixable` or `requirements-conflict`; for a stop, `root-contradiction`,
  `phase-failure` or `destructive-op`.
