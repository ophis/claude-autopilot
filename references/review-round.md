# Review round

How review rounds run and loop, for `build`, `light-build` and `review`. The calling skill
sets the panel, the cap (total rounds, `r1` included), the re-review set, the doc fields
of the run-input prompt, the freeze line and the log. Paths here are relative to this
file's directory. A section name in parentheses, such as (Publish), is `autopilot-common.md`'s.

- **Lens**: one reviewer agent. The **panel** is the set of lenses for a phase.
- **Round**: one parallel review of the panel, numbered `r1`, `r2`, ….
- **Phase**: `spec` reviews a document, `work` reviews commits. A step marked (work)
  runs only in the work phase.

## Dispatch

- On Claude Code, dispatch a lens from this plugin's `agents/` as `autopilot:<name>` via
  the Agent tool. It keeps the `model:`, `effort:` and tools from `../agents/<name>.md`.
- Give a lens from another folder (selector `subagent_type: "general-purpose"`), and every
  lens on a host without named dispatch, to a fresh generic agent: the full body of its
  file (`../agents/<name>.md`, or selector `file`) ahead of its run-input prompt, keeping
  the body's verdict grammar and tool and test limits. Codex always works this way: the
  agent inherits the session model, so pass no `model` to `spawn_agent`.

## Log

The caller says where these go:

- Panel freeze: the caller's freeze line, ending `transport=Workflow`. Append `->Task` or
  `-><actual native tool>` if the fallback fires.
- Round, with the verdict roll-up and one gist per blocker: `S6 r1 @<reviewed_sha>: correctness=FAIL verification=PASS (command=<cmd>, exit code=0, tests=12, failures=0) -> correctness#1 off-by-one in slice bound; fixing`.
  A spec-phase round has no `@<reviewed_sha>`. A round step 3 stopped logs
  `verification=FAIL (CI check; panel not dispatched)`.
- Items: after each round, its items in full with their IDs, BLOCKING and NON-BLOCKING.

The blocker gists prime re-reviews; the full items are in the items.

## Round

**Verifier (work).** Every work panel includes `autopilot:verification-reviewer`. Freeze
its backend in `r1`: `verification=ci` when `pr.py` reports `publish` other than `none`
and the plan doc's `CI checks:` names a check, else `verification=local`. It runs every
round.

Run each round in these steps:

1. **Freeze.** In `r1`, log the panel. Reuse it for every round of the phase.
2. **Pin the revision (work).** Require a clean committed source worktree:
   `git -C <worktree> status --porcelain` is empty. Set `reviewed_sha=<HEAD>` from
   `git -C <worktree> rev-parse HEAD`. Run `pr.py push` (Publish). Leave HEAD
   alone until every verdict is back.
3. **Peek at the PR (work, `publish` other than `none`).** Before dispatching anyone, run once
   `python3 <abs path of ../scripts/ci-verdict.py> --worktree <worktree> --sha <reviewed_sha> --plan-doc <plan_doc> --wait 20 --appear 20 --interval 5`.
   It never waits for CI to finish. Exit 5 (`CONFLICT:`): resolve it (Publish) before
   anything else. Exit 1, CI already failed: dispatch no one; the round is
   `verification=FAIL` with the printed items as its blockers, so go to step 9; every
   other lens keeps its state from earlier rounds, and one that has not reviewed yet is
   pending, not FAIL. Exit 6: safety stop 3. Any other exit, CI still running included:
   go on; with `verification=ci` the verifier waits for CI alongside the other lenses.
4. **Write prompts.** Each member gets only its run-input prompt:
   `PHASE=<spec|work>. Inputs: worktree=…, base_ref=…, <doc fields>, requirement=…, focus=…, reviewed_sha=<HEAD> (work only). Output ONLY the verdict, no extra prose.`
   With no repo, leave out `worktree=` and `base_ref=`.
   The verifier's prompt adds `verification=<local|ci>` and, with `ci`,
   `ci_script=<abs path of ../scripts/ci-verdict.py>`.
   `focus=` names only what the requirement, spec or a logged decision asks the lens to
   weigh. It never claims the work is correct and never narrows the lens's checklist.
   A re-reviewed lens also gets its prior items as `<lens>#<n> "<gist>"`. In the work
   phase it also gets the fix diff `git -C <worktree> diff <pre-fix HEAD>..HEAD`.
5. **Dispatch all members together**, never one at a time, re-reviews included. Queue
   the rest when the host's concurrency limit is reached.
   - **Workflow (default):** one call per round,
     `Workflow({name: "autopilot:autopilot-review-round", args: {phase: "<spec|work>", members: [{agent, subagent_type, prompt}, …]}})`.
     It returns `{phase, verdicts: [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}, …]}`
     in member order. Never pass `resumeFromRunId`. Re-dispatch a `synthetic: true` member
     once as a fresh subagent (`Task`) with its prompt; if it still gives no verdict, it
     is FAIL. A generic member goes in as `general-purpose`, its file's body ahead of its
     prompt.
   - **Native fallback:** if `Workflow` is unavailable or the call fails, dispatch the same
     members fresh as one parallel subagent batch (`Task`) with the same prompts. Stay on
     the fallback for the rest of the phase and note it in the freeze line.
6. **Wait for every verdict.** Never poll or judge early. A status message is not a verdict.
7. **Recheck the revision (work).** HEAD still equals `reviewed_sha` and status is still
   empty. If the only dirty paths are ones the verifier reports as leaked, judge normally;
   the fix removes them. If HEAD moved, take safety stop 3 and list the new commits.
8. **Check the verifier (work).** Read its raw BLOCKING items before adding item IDs.
   `VERIFICATION_UNAVAILABLE:` (after its one retry) triggers safety stop 3. `CONFLICT:`
   means merge the base and re-run the round (Publish).
9. **Label items.** Before deduping for the fix, give every BLOCKING and NON-BLOCKING
   item an ID `<lens>#<n>`, numbered per lens across the phase and never reused. A
   repeated open item keeps its ID (the reviewer prefixes it). Number only new items.
10. **Judge and log.** A lens passes with VERDICT PASS and no open BLOCKING; a dispatched
   lens with a missing or unparseable verdict is FAIL. Only the
   reviewers' own verdicts decide: never override one, downgrade a blocker, or mark an
   item INVALID yourself. Log the round.

Re-run an interrupted round whole: the frozen panel, on its recorded transport and round
number.

## The loop

`r1` runs the full frozen panel. While any lens fails and the cap allows another round,
make ONE fix over all blockers, then run ONE re-review round with the caller's re-review
set, plus every lens that has not yet reviewed in the phase; lenses outside the set
carry their PASS. When every lens passes, the phase passes.
At the cap without a pass, the caller says what happens.

### The fix

Fix all deduped open blockers yourself in one pass, from their full text,
their item IDs and the locations they cite. If an item stays OPEN after a fix, write down
what that fix assumed and check the assumption before the next fix depends on it.
