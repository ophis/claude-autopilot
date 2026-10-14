# Autopilot common rules

The rules `build` and `light-build` share. The calling SKILL.md owns the pipeline and its
settings; this file owns everything both surfaces do the same way. Paths here are relative
to this file's directory.

## Terms

- **Input**: `input` is Claude Code's substituted `$ARGUMENTS`, or Codex's invoking user
  request or explicit caller input. An unresolved placeholder counts as absent. It is the
  single source of intent; the skill lists its forms.
- **Plan doc**: the run's state file. It holds the RESUME block and the task list; the
  skill says what else.
- **Run note**: an ignored file holding S6 state (see State and resume).
- **Producer**: a fresh subagent you hand one self-contained task to (see Produce (S5)).
- **Lens**: one reviewer agent. The **panel** is the set of lenses for a phase.
- **Round**: one parallel review of the panel, numbered `r1`, `r2`, ….
- **Genuine fork**: two or more viable approaches with materially different trade-offs,
  or a choice that shapes architecture, data model, interface or scope, is costly to
  reverse, or that a later review might miss.

## Disciplines

- **Decide everything yourself.** Never ask the user anything. Settle a genuine fork with
  the council, anything else solo. Every stop is a handoff, not a question.
- **Author the work; let reviewers judge it.** You implement the S5 tasks and the S6 fixes
  yourself. Independent reviewer subagents judge the result, and only their verdicts
  decide.
- **Guard your context.** Read only what the current step needs. Send long command output
  to a file and read bounded slices of it. Hand bulk searches and reads to a subagent and
  keep its summary.
- **Brief workers fully.** Resolve bundled paths to absolute paths for tools and briefs,
  and keep the target worktree as cwd. Read the target repo's applicable AGENTS.md /
  CLAUDE.md and pass their paths and constraints to every worker.
- **Pin every write to the worktree.** Give each subagent the absolute worktree path and
  branch. You and it use absolute paths and `git -C <worktree>`, never the inherited cwd.
  Before any write, assert `git -C <worktree> branch --show-current` is the run branch, never
  main/master.
- **Batch steps.** Every tool call re-sends your whole context. Combine independent shell
  steps into one command, and make independent calls together in one parallel batch.
- **End at a review-ready branch.** Never merge.

## Hosts

- Tool names in parentheses are Claude Code forms. On another host, use the session's
  exposed equivalent.
- Use the exposed spawn, continue and wait tools with their documented arguments. Request
  fresh context when supported, and give each worker its brief and constraints.
- `Workflow` exists only on Claude Code. Without it, use the native fallback (Review round).
- Default worktree path and branch: Claude `.claude/worktrees/<prefix>-<slug>` and
  `<prefix>-<slug>`; Codex `.codex/worktrees/<prefix>-<slug>` and `codex/<prefix>-<slug>`.
- On Claude Code, dispatch reviewer `<name>` as `autopilot:<name>` via the Agent tool. It
  keeps the `model:`, `effort:` and tools from `../agents/<name>.md`.
- Without named dispatch, give a fresh generic agent the full `../agents/<name>.md` body
  plus its run-input prompt, and keep the body's verdict grammar and tool and test limits.
  Codex always works this way: the agent inherits the session model, so pass no `model` to
  `spawn_agent`.

## State and resume

- **Resume first.** On start, look for this run's plan doc (in a found worktree, check
  `.autopilot/` too). If found, check that its
  worktree, branch and base_ref exist on disk, then continue from its `phase`. If not,
  start at S1.
- Place the plan doc where the user's or project's convention says (AGENTS.md /
  CLAUDE.md, existing repo patterns). With no convention, use an `.autopilot/` directory
  in the worktree that holds a `.gitignore` of `*`.
- The plan doc's first line is `Rules: <abs SKILL.md path> <abs path of this file>`.
- Once the plan doc exists, rewrite RESUME `phase=` at every phase change and
  `review_round=` every loop iteration.
- Re-run an interrupted review round whole: the frozen panel, on its recorded transport
  and round number.
- From S6, keep RESUME, the frozen panel, the verdicts with each round's full BLOCKING
  items, the reviewed SHA and tree, and the verifier's exact commands and results (exit codes, failure counts, diagnostics) in an
  ignored run note. An ignored plan doc can serve as the run note, with that content above the task
  list; a tracked plan doc links to the note before it is committed for review.
- Resume at S7 or S8 only with all-PASS evidence for the current tree. Otherwise restart S6.
- **Notes.** Once the plan doc exists, write each durable fact you learn to its Notes
  section as one line: key files and entry points, repo patterns and commands, gotchas,
  and anything a later task depends on. A context summary drops these; the plan doc
  keeps them. From S6, Notes go where S6 log lines go.

### Re-hydrate after compaction

After a context compaction, or whenever you are unsure of the run's state, rebuild it
from disk before you act:

1. Find the plan doc (Resume first) and re-read it: the `Rules:` line, RESUME, progress,
   Notes and task list. With no plan doc yet, follow Resume first.
2. Re-read the SKILL.md and this file from the `Rules:` paths. If a path is gone, find
   the file by skill name in the installed plugin.
3. Re-read the spec doc if the run has one, and from S6 the run note.
4. Run `git -C <worktree> log --oneline <base_ref>..HEAD` and `git -C <worktree> status`.
   A commit carrying a task's brief message means that task is done; log it if the mark
   is missing.
5. Finish unfinished work before moving on:
   - **S5**: uncommitted changes belong to the first task not `done`. Finish or redo it.
   - **S3**: if the latest round failed, the spec doc on disk holds any partial fix.
     Finish it against that round's full BLOCKING items, then run the re-review.
   - **S6**: uncommitted changes are the fix in progress. Finish it against the latest
     round's full BLOCKING items in the run note, with that round's `reviewed_sha` as the
     pre-fix HEAD, commit, then run the re-review. A clean tree with HEAD past that
     `reviewed_sha` means the fix is committed: run the re-review.
6. Continue from RESUME `phase`.

## Progress log

A short audit log, one line per event, not a transcript. The skill says where each line
goes. S3 uses the S6 shapes.

- Panel freeze: the skill's freeze line, ending `transport=Workflow`. Append `->Task` or
  `-><actual native tool>` if the fallback fires. In S6 without the verifier, write `verification=CI` or `verification=none`.
- Task done: `S5 task 3 done: <commit sha>`.
- Review round, with the verdict roll-up and one gist per blocker: `S6 r1 @<reviewed_sha>: correctness=FAIL verification=PASS (command=<cmd>, exit code=0, failures=0) -> correctness#1 off-by-one in slice bound; fixing`.
- Decision, council or solo: `decision(<topic>): chose X over Y - <short reason>; dissent: <one phrase | none>`.
- Deferred pattern match outside the change: `deferred(<pattern>): <file:line>`.
- At the end: the residual NON-BLOCKING items.

The blocker gists prime re-reviews. The log line holds only the gist; the full BLOCKING
items go to the fix and stay on disk until it lands (S6: the run note).

## Council

1. At a genuine fork, convene 2–4 ad-hoc expert personas in one parallel subagent batch
   (`Task`). Each returns a concise position: recommendation, rationale, trade-offs,
   dissent.
2. Synthesize and decide; you break ties. Log the decision.
3. Use only personas with a genuinely distinct view. With fewer than two, decide solo.

Outside a genuine fork, decide solo and log it. Review catches a wrong guess.

## Worktree (S1)

1. Already in an isolated worktree, not on `main`/`master`: reuse it, with `base_ref` =
   current local HEAD. Do not nest another.
2. Otherwise resolve the host-specific `<branch>` before lookup or creation, and use this
   same branch for reuse and resume:
   - `<prefix>`: the ticket ID when the work is for one ticket (e.g. Linear `TASK-123`),
     else `autopilot`.
   - `<slug>`: `input` lowercased, non-alphanumerics turned into hyphens, at most 40
     chars. With a ticket prefix, use a short feature description instead (not the
     ticket ID again).
   - Follow the repo's worktree and branch conventions, else the host defaults. Make sure
     the worktree directory is gitignored.
3. The branch exists from a prior run: reuse it with its commits, never a numbered copy.
   Enter its worktree (`git worktree list`; if none, `git worktree add <path> <branch>`)
   and set `base_ref` = `git merge-base HEAD <branch>`. A plan doc there means resume.
4. Otherwise create the worktree on local HEAD:
   - On a collision with another requirement's worktree or branch, add `-2`, `-3`, … to
     the slug and resolve path and branch again.
   - Use a host worktree tool only if it honors the exact local HEAD base and branch.
     Otherwise run `git worktree add <path> -b <branch> HEAD`.
5. Enter the worktree (`EnterWorktree({path: <path>})`). Run every later command there,
   and give workers its absolute path.

## Task list (S4)

Write the task list yourself and invoke no planning skill. It is code-free and is the
plan doc's last section. The skill says what else goes in the header and where the full
verify command goes; it never goes in the task-list header.

- **Header**: Global Constraints (exact values the tasks need).
- **One `### Task N: <name>` heading per task.** A brief runs to the next task heading,
  so a producer can be handed one alone. Each brief lists:
  - Files.
  - Consumes / Produces: exact names and signatures that cross tasks.
  - Tests to write first, including edge cases.
  - The checks it runs: only those its change affects, never a full suite. The verifier
    or CI runs that.
  - Commit message.

## Produce (S5)

For each task, starting from the first one not `done`:

1. Implement it yourself from its `### Task N` brief: the tests first, then the code.
2. Run only the checks its brief names that cover your changed files, never the full
   verify command or full suite.
3. Commit with the brief's message, add Notes for anything a later task needs, and log
   the task `done`.

**Delegation.** You may hand a self-contained task that would flood your context, such as
a bulk mechanical edit or a large isolated module, to one fresh producer. Give it the task
list header, its `### Task N` brief, the worktree pin, the constraints, and what the skill
adds. The producer follows steps 1 and 2, commits, and returns any Notes lines for you
to record. You confirm the commit, then log the task `done`. If the producer fails,
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

**Verifier rule.** Add `autopilot:verification-reviewer` to an S6 panel only when the repo
has no CI running its full checks or the requirement asks for local verification. The
verifier runs the complete checks in the frozen source worktree every round it is on the
panel. Ordinary reviewers read the source at HEAD and leave full checks to the verifier
or CI.

Run each round in these steps:

1. **Freeze.** In `r1`, log the panel. Reuse it for every round of the phase.
2. **Pin the revision (S6).** Require a clean committed source worktree:
   `git -C <worktree> status --porcelain` is empty. Set `reviewed_sha=<HEAD>` from
   `git -C <worktree> rev-parse HEAD`. Leave HEAD alone until every verdict is back.
3. **Write prompts.** Each member gets only its run-input prompt:
   `PHASE=<spec|work>. Inputs: worktree=…, base_ref=…, <doc fields>, requirement=…, focus=…, reviewed_sha=<HEAD> (S6 only). Output ONLY the verdict, no extra prose.`
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
     the fallback for the rest of the phase and note it in the freeze line. A verdict
     passes only with no BLOCKING items; a missing or unparseable verdict is FAIL.
5. **Wait for every verdict.** Never poll or judge early. A status message is not a verdict.
6. **Recheck the revision (S6).** HEAD still equals `reviewed_sha` and status is still
   empty. If the only dirty paths are ones the verifier reports as leaked, judge normally;
   the fix removes them.
7. **Check the verifier.** Read its raw BLOCKING items before adding item IDs.
   `VERIFICATION_UNAVAILABLE:` (after its one retry) triggers safety stop 3.
8. **Label items.** Before deduping for the fix, give every BLOCKING and NON-BLOCKING
   item an ID `<lens>#<n>`, numbered per lens across the phase and never reused. A
   repeated open item keeps its ID (the reviewer prefixes it). Number only new items.
9. **Judge and log.** A lens passes with VERDICT PASS and no open BLOCKING. Only the
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
  scope; log matches outside it as `deferred` lines for the S8 report. A guard that
  silences a symptom is not a fix.
- If an item stays OPEN after a fix, write down what that fix assumed and check the
  assumption before the next fix depends on it.
- Run only the checks covering the files you changed, and commit all product changes
  before the re-review. The re-review then pins the new revision.
- Docs are fixed here. There is no separate doc phase.

## Squash and finish (S7, S8)

- **S7.** Squash to one commit with `git`, idempotently: skip when the branch is already
  exactly 1 commit ahead of `base_ref`. Commit or ignore the run's notes per the
  project's convention; force neither. Before S8, require a clean worktree and
  `git rev-parse HEAD^{tree}` equal to `git rev-parse <reviewed_sha>^{tree}`. If the
  trees differ, return to S6.
- **S8.** Report inline, with no skill: the review history, the final verification
  evidence (the verifier's from the run note, else the freeze's `CI` or `none`), the
  decisions, and the deferred non-blockers and `deferred` lines. On a stop, lead with the stop reason. List
  the integration options as an informational menu, not a question.

## Safety stops

Stop and hand off the state and exact next step only in these cases:

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

On every terminal path, S8 or any safety stop, end with exactly one fenced
`autopilot-result` block holding one JSON object, so a caller reads the outcome without
parsing prose:

```autopilot-result
{ "status": "converged", "branch": "<prefix>-<slug>", "base_ref": "<sha>", "head": "<sha>", "blockers": [], "reason": "" }
```

- `status`: `converged` (reached S8), `capped-without-pass` (a review loop hit its cap),
  or `stopped` (any other safety stop).
- `branch`, `base_ref`, `head`: the branch name, its base SHA, and its final commit SHA
  (`head` = `base_ref` if nothing was produced).
- `blockers`: the residual open BLOCKING items as strings when not converged, else `[]`.
- `reason`: empty when converged. Otherwise the classification plus detail: for a cap,
  `oscillation`, `unfixable` or `requirements-conflict`; for a stop, `root-contradiction`,
  `phase-failure` or `destructive-op`.
