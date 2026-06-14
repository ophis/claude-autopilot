---
name: fix
description: "Use to apply review feedback to the existing autopilot branch: turn the feedback into a change-spec, then plan, implement, verify, review-loop, and re-squash to one review-ready branch (never merges). Pass the feedback text; requires an existing autopilot branch."
argument-hint: "<feedback>"
---

# Autopilot: fix

You are the orchestrator for an autonomous feedback round on an existing autopilot
branch. Drive the pipeline below end to end. Dispatch and judge.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the human **review feedback** on an existing autopilot branch. Treat
it as the single source of intent for this round. If it is empty, STOP with a
handoff asking for feedback.

## Preflight (dependencies)

**Load config (run first, every run):** run `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. It creates `${CLAUDE_PLUGIN_DATA}/config.json` with defaults if absent and prints the effective config. Note the per-phase caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase` for the S1/S5 Ralph loop. User edits to that file take effect on the next run.

Before E1′, confirm the **superpowers** plugin is available — its skills must appear
in your skill list. This whole pipeline is built on them, so this preflight is the safety net.

If it is **not** available, STOP with a handoff: tell the
user it is required and how to install it —
`/plugin install superpowers@claude-plugins-official` — and to re-run `/autopilot:fix` after.

## Operating disciplines

- **Autonomous — never ask the user.** At a decision point, **convene the expert
  council** (see "Deciding at decision points (expert council)") to deliberate, then
  decide + record; trivial vagueness → decide + record solo. Only the safety stops
  interrupt the run.
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never
  hoard whole files, diffs, or logs in the main thread. Read only bounded slices
  when you must inspect something yourself.
- **Disk-backed.** Persist the change-spec and a **plan doc** (implementation plan +
  progress section + a RESUME block) so the run survives compaction. Location follows the
  user's/project's convention — see **State & resumption**.
- **A STOP is a handoff, never a question:** emit current state + the exact next
  step a human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

## Resume first

Look for an existing **plan doc** with a RESUME block in the project's convention
location. If found: reconcile worktree/branch/base_ref existence on disk, then
continue from `phase` (an interrupted review round re-runs whole). **If none, that
is the normal first run → go to E1′ (locate); never create a branch.**

## Deciding at decision points (expert council)

At a **decision point**, the orchestrator **convenes an expert council**: a small team
(2–4) of **ad-hoc expert sub-agents** (personas derived from the decision's domain),
dispatched in **one parallel batch** via `superpowers:dispatching-parallel-agents`. Each
returns a **concise position** (recommendation + rationale + key trade-offs + any
dissent). The **orchestrator then synthesizes, decides, and records** the decision + the
council's key points (incl. dissent) in the spec doc / plan doc (progress section). The orchestrator is
the decider; the council informs it. Never ask the user.

**Council members are advisors, not reviewers** — they give recommendations, NOT the
`VERDICT/BLOCKING/NON-BLOCKING` grammar (that's the review panel). Bounded: 2–4,
parallel, by-reference, no superpowers skills, concise positions.

**Convene when ANY of:**
- two or more **viable approaches with materially different trade-offs** exist;
- the choice **shapes architecture / data model / public interface / scope**;
- the choice is **costly to reverse** once baked in;
- it is a genuine fork a later review loop **might not catch**.

**Decide solo + record when:**
- there is a **single obvious default**, or project convention dictates the answer;
- the choice is **cosmetic / local / easily reversible**;
- a wrong guess would simply be **caught by S1/S5**.

**Examples.** Council: "which storage model / API shape / module boundaries?",
"reconcile two conflicting requirements", "pick between two non-trivial strategies".
Solo: "name a variable", "pick a file path under convention", "fill an obvious default
for a low-stakes detail".

**Single-persona fallback:** if a decision admits fewer than two distinct lenses, use a
smaller council or decide solo with recorded rationale — don't fabricate personas to hit
a count.

**Dissent / split handling:** the orchestrator rules and records *why*; a minority
position is logged as "considered, not adopted"; the orchestrator breaks ties (it is the
decider).

## Selecting & dispatching the review panel

The S1/S5 panels are **selected by script** from the installed roster, then composed
and dispatched natively.

- **Select.** Run the selector for the phase:
  - S1 → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py" --phase spec --spec-file <change-spec doc>`
  - S5 → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py" --phase work --worktree <worktree> --base <base_ref>`
  It returns JSON with a `selected` list of `{agent, subagent_type, tier, matched}`.
- **Compose the panel:** ALL returned `core` agents (mandatory) + the
  `optional` agents the orchestrator judges relevant (it may drop a marginal
  optional) + any **ad-hoc** inline lens for a genuine gap no roster agent covers.
- **Freeze & log** the composed panel to the **plan doc** (progress section): which core (all), which
  optionals included/excluded + why, any ad-hoc added. Reuse the frozen panel every
  round of that phase.
- **Dispatch the whole round's panel together** — never one at a time; every review
  round in S1 and S5, re-reviews included. Build each member's run-input prompt once —
  "PHASE=<spec|work>. Inputs: worktree=…, base_ref=…, spec_doc=…, plan_doc=…,
  requirement=…, focus=…. Return ONLY the verdict block." (absolute paths) — the
  identical prompt goes to whichever transport carries it:
  - **Workflow transport (preferred; roster and ad-hoc members):** one call per round —
    `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/scripts/review-round.js", args: {phase: "<spec|work>", members: [{agent, subagent_type, prompt}, …]}})`.
    Pass `args` as a real JSON object (the transport tolerates a stringified one, but don't rely on it).
    Members keep their own model + read-only allowlist (`agentType` resolves like
    `Task`). The call returns a task ID immediately; the round's verdicts arrive in
    its completion notification as `{phase, verdicts: [{agent, verdict, blocking,
    non_blocking, synthetic}, …]}` — wait for it (never poll, never judge early).
    Never pass `resumeFromRunId`: every round is a fresh run. `synthetic: true` =
    that member's infra failure, not a review FAIL: once all initial results are in
    (incl. ad-hoc), re-dispatch just those lenses once via `Task`; still nothing →
    FAIL. A return without a `verdicts` array — or a `verdicts` array shorter than the
    panel you sent (including `[]` for a non-empty panel) — is a failed/partial call →
    Task fallback for the missing members.
  - **Ad-hoc members ride the SAME Workflow `members` list** as `subagent_type:
    "general-purpose"`, with the persona + the verdict contract — including "Read-only.
    Modify nothing." and "return ONLY the verdict block." — in the `prompt`. Their
    read-only is **prompt-enforced only** (roster members carry a real read-only tool
    allowlist; ad-hoc do not), so the summon prompt MUST carry the read-only
    instruction. Ad-hoc follow the SAME fallback as roster — both (a) the whole-round
    Task fallback if the Workflow call is unavailable/fails, and (b) the per-member
    `synthetic: true` single Task re-dispatch. Dispatch ad-hoc directly via `Task` only
    when the whole round is already on the Task fallback.
  - **Task fallback:** if the `Workflow` tool is unavailable or any call failed,
    dispatch roster members as `Task(subagent_type="autopilot:<name>", …)` — the
    agent's body is its system prompt; send ONLY the run-input prompt — all calls in
    a single message (`superpowers:dispatching-parallel-agents`), for the rest of
    the run. Record the transport (and any fallback) in the plan doc.
- **Collect verdicts → the Ralph loop** (round-0 short-circuit, re-review rounds
  dispatch the `(FAILed ∪ touched)` subset, cap, convergence from on-disk verdicts).

## Verdict grammar (paste into ad-hoc summon prompts only — roster agents already embed it)

```
VERDICT: PASS            # or exactly: VERDICT: FAIL
BLOCKING: none           # or one "- " item per line
NON-BLOCKING: none       # or one "- " item per line
```

PASS ⟺ `BLOCKING: none`. Cite evidence (file:line / spec
clause); flag blockers, not preferences. A missing, unparseable, or empty-on-FAIL
verdict counts as **FAIL**. Convergence is decided from these on-disk verdicts,
never from vibes.

## Ralph loop (S1 and S5)

The two review-convergence phases — **S1** (spec review) and **S5** (work review) —
run a Ralph loop: review → fix → re-review until the panel passes, capped at the
per-phase cap (default 3 rounds). The orchestrator drives the loop natively.

**Config (loaded in Preflight):** from `${CLAUDE_PLUGIN_DATA}/config.json` →
`{ "ralphLoop": { "maxIterations": { "spec-phase": 3, "implementation-phase": 3 } } }`.
`ralphLoop.maxIterations.spec-phase` / `.implementation-phase` is the per-phase round cap (default 3).

- **The native loop.** The orchestrator runs the rounds
  itself; each round's members go out **together via the transport rule** (one
  `Workflow` call, or one parallel `Task` batch on fallback), and the
  orchestrator records each lens's verdict (+ blocking items, terse) in the plan
  doc. **Round 0** = the full frozen panel; all-PASS short-circuits.
  **Re-review rounds (N>0)** dispatch only **`(FAILed ∪ touched) ∩ frozen panel`**:
  *FAILed* = last verdict FAIL (or missing/unparseable). *touched* (S5) = every
  lens whose `applies_to` matches the fix's changed files — record the **pre-fix
  HEAD** (in the plan doc) before dispatching the producer, then re-run
  `select-panel.py --phase work --worktree <worktree> --base <pre-fix HEAD>`;
  its `selected` list is the touched set (cores match any path and always re-run —
  skips come from unmatched optionals). Ad-hoc lenses re-run iff FAILed; S1
  re-reviews stay full-panel (S1 fixes edit the spec itself). A skipped lens keeps
  its PASS as its current verdict; the `∪ touched` half is the correctness guard —
  a fix can regress a lens that passed. Advance when every frozen-panel lens's
  current verdict (fresh or carried) is PASS with no open BLOCKING; else fix and
  re-dispatch; cap = `maxIterations.spec-phase` (S1) /
  `maxIterations.implementation-phase` (S5), default 3.

The loop obeys these rules: every dispatched reviewer is a fresh instance;
convergence is decided from the on-disk verdicts (the marker is printed ONLY when
convergence is genuinely true — never to escape the loop); on the marker the phase
is done and the command
proceeds (S1→S2, S5→S6); if the per-phase cap (`maxIterations.spec-phase` /
`.implementation-phase`, default 3) is hit WITHOUT the marker → non-convergence STOP
with the 3-way classification (oscillation | unfixable | requirements-conflict) and
a handoff — do not proceed.

## Pipeline (E1′, E2′, S1–S7)

Legend: **E#** = entry phase (command-specific; `′` = fix variant); **S#** = shared
spine (common to build & fix).

- **E1′ — locate the existing branch (no new worktree).** Find the target autopilot
  branch: read the project's **plan doc** (RESUME block) if present; else the most recent
  `autopilot/*` branch. **If none → STOP** ("no autopilot branch found — run
  `/autopilot:build <requirements>` first"). Never create a new branch. E1′ **reuses
  the existing plan doc if present, else creates one.**
  - **Worktree:** use the branch's existing worktree; if it was removed, check the
    branch out in place — never create a second worktree for it.
  - **base_ref:** reuse the value in that branch's **plan doc** RESUME block if present; else
    `git merge-base main autopilot/<slug>` (default branch = `main` unless the repo
    says otherwise). Record worktree/branch/base_ref.
  - **Dirty tree:** if the worktree has uncommitted changes, STOP with a handoff
    (commit or stash first) so they aren't folded into the re-squash — unless Auto
    Mode is on (then proceed, deferring to Auto Mode).
- **E2′ — brainstorm the feedback.** Use `superpowers:brainstorming` on `$ARGUMENTS`
  (the feedback) → write a **change-spec** appended to the existing spec doc (the
  original spec stays as context). At decision points, convene the expert council (see
  "Deciding at decision points (expert council)") to discuss and decide; record the
  decision + rationale. (Trivial defaults: decide + record.)
- **S1 — change-spec review (Ralph loop).** Review the **change-spec** (with the
  original as context), not the original. Panel derived from the change-spec's
  keywords; reviewers read the change-spec doc (as in build's S1). Run the **S1
  Ralph loop** (above) over the (change-)spec. **Fixes:** the orchestrator edits the
  spec doc directly (the spec is a small artifact it holds; only S5 delegates fixes
  to a producer). On convergence it records `AUTOPILOT: SPEC READY`.
  **Root-contradiction STOP:** if the reviewers find the core requirement asks for
  two things that cannot both be true, STOP and hand off — quote the two conflicting
  clauses (this is a handoff, never a question; mere vagueness is decided, not
  stopped).
- **S2 — plan the delta.** Use `superpowers:writing-plans` → write the implementation
  plan for the change into the **plan doc** (separate from the change-spec), appended
  under a change-scoped heading; record how the work will be verified. On a consequential
  plan fork → convene the expert council (see "Deciding at decision points (expert
  council)") to decide.
- **S3 — produce.** Code → `superpowers:subagent-driven-development`: keep its
  per-task reviews (early-catch), SKIP its final whole-implementation review — S5 is
  the authoritative whole-diff gate that re-reviews the same diff. It may commit per
  task; the S6 re-squash folds its commits. Non-code → producer subagents via the same
  dispatch pattern. The orchestrator never edits the work product itself.
- **S4 — verify.** Use `superpowers:verification-before-completion`: run the
  discovered checks. For THIS plugin = `claude plugin validate` +
  `python3 tests/test_scripts.py` + the documented manual smoke. Cap fixes at 3;
  never weaken, skip, or delete a check; a drop in the check count → STOP.
- **S5 — work review (Ralph loop).** Panel derived from the **delta diff**
  (`git diff --name-only base_ref...HEAD`); reviewers run a path-scoped diff. Run the
  **S5 Ralph loop** (above) over the work. The core `doc-reviewer` is always in the
  S5 panel and now gates docs repo-wide: stale / missing / contradictory docs = BLOCKING (the
  S5 producer fix updates them); bloat = NON-BLOCKING. **Fixes:** ONE fresh producer
  subagent primed with the deduped open blockers + cited files only. On convergence
  it records `AUTOPILOT: WORK READY`.
- **S6 — re-squash.** Squash the branch back to **one** clean commit (fold the new
  feedback commits into the existing single commit). Local, unpushed history rewrite
  **within the branch's own commits** — permitted by the destructive-op stop (and
  skipped under Auto Mode). Idempotent: if already exactly 1 ahead of base_ref, skip.
  Record the pre-squash HEAD SHA in the RESUME block so an interrupted re-squash is
  detected on resume.
- **S7 — finish (no merge).** Use `superpowers:finishing-a-development-branch` →
  report: review history, decisions, deferred non-blockers (stop-reason first if the
  run stopped); offer integration options as an informational report menu, NOT a
  question. **NO merge.** Then emit the **Result handoff** block (below) as the final output.

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on: Every STOP handoff ends by emitting the **Result handoff** block (`status`=`stopped`, or `capped-without-pass` at a cap).
1. **Destructive op — only when Auto Mode is OFF.** Before any force-push, write
   outside the worktree, history rewrite beyond this branch, or rm/reset of
   uncommitted work. **If the session is in Auto Mode** (auto-accept /
   bypass-permissions), skip this stop — destructive-op judgment is deferred to
   Auto Mode. The other three stops below apply regardless of Auto Mode.
2. **Non-convergence at cap** — a Ralph loop hits `cap` (with the classification).
3. **Non-review phase failure** — one retry, then STOP.
4. **Root-contradiction** — the feedback irreconcilably contradicts a locked
   requirement (or the core requirement is self-contradictory); cite the two clauses.

## Result handoff (always emit last)

On **every** terminal path — S7 finish AND any safety-stop handoff — emit, as the final
output, exactly one fenced `autopilot-result` block (one JSON object) so a calling
skill/workflow consumes the outcome without parsing prose:

```autopilot-result
{ "status": "converged", "branch": "autopilot/<slug>", "base_ref": "<sha>", "head": "<sha>", "blockers": [], "reason": "" }
```

- `status` — `converged` (reached S7) | `capped-without-pass` (a Ralph loop hit its cap) | `stopped` (any other safety stop).
- `branch` / `base_ref` / `head` — branch name, its base SHA, its final commit SHA (`head` = `base_ref` if nothing was produced).
- `blockers` — residual open BLOCKING items (strings) when `status != converged`, else `[]`.
- `reason` — empty when converged; else classification + detail (cap → oscillation | unfixable | requirements-conflict; stop → root-contradiction | phase-failure | destructive-op).

Additive only — it changes no phase's behavior.

## Token discipline

Thin orchestrator · by-reference dispatch (never pipe diffs into N prompts) ·
smallest panel (2–4, conditional lenses only on signal) · round-0 short-circuit ·
per-phase cap (`maxIterations.spec-phase` / `.implementation-phase`, default 3),
re-dispatch only the `(FAILed ∪ touched)` subset · bounded subagent prompts, no
superpowers skills loaded into reviewers · producer primed by blockers + cited files
only · expert councils bounded (2–4), convened only at genuine decision points, in one
parallel batch · workflow transport returns a round's verdicts as one JSON payload
(reviewer output stays off the main thread).

## State & resumption

Persist two things so the run survives compaction: the brainstormed
**change-spec** and the **plan doc** (implementation plan + progress section, carrying a small RESUME block):

```
RESUME: phase=<E1'|E2'|S1..S7> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> pre_squash_head=<sha>
```

(`pre_squash_head` is recorded once **S6** runs, so an interrupted re-squash is detected
on resume.)

**Keep RESUME current:** rewrite the RESUME block at every phase transition — update `phase=` as you advance (E1′→E2′→S1…→S7), `review_round=` each loop iteration, and `pre_squash_head=` once the squash runs; the resume contract depends on RESUME reflecting the true current phase, and a stale `phase=` breaks resumption.

**Where these live follows the user's / project's existing convention** —
honor CLAUDE.md preferences and existing repo patterns. The command imposes no fixed
path (do not assume `dev-docs/`) and no gitignore-vs-commit policy.

**Resume contract:** on resume, reconcile worktree/branch/base_ref existence first,
then continue from `phase`; an interrupted review round is re-run from scratch
(re-dispatch the whole frozen panel — bounded, idempotent), so only `review_round`
need be persisted to locate the loop.
