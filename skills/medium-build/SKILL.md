---
name: medium-build
description: "Use to build a change end to end on the trimmed path: create an isolated worktree, write a spec, one-shot expert spec review, slice a terse task list, implement, verify, and a trimmed work-review loop to a single review-ready branch (never merges). Pass the requirement text."
argument-hint: "<requirements>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, Skill, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite
---

# Autopilot: medium-build

You are the orchestrator for an autonomous **medium-build** run — the **trimmed path**.
Drive the pipeline below end to end: dispatch and judge. It is `build` with a shorter spine:
no S1 roster panel, no writing-plans; a single expert reviewer serves as a one-shot spec
review (E3), and S5 is a minimal capped loop.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent: free-text requirements for a small change.
Empty input → STOP with a handoff asking for requirements.

## Preflight (dependencies)

**Load config (run first, every run):** `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. It creates `${CLAUDE_PLUGIN_DATA}/config.json` with defaults if absent and prints the effective config, including the per-phase Ralph caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase`. medium-build ignores those defaults for S5 (it pins cap = 1 — see **Review rounds**); the load still confirms config health. User edits take effect next run.

Before E1, confirm the **superpowers** plugin is available — its skills must appear in your
skill list (the whole pipeline is built on them). If **not** available, STOP with a
handoff: it is required, install via
`/plugin install superpowers@claude-plugins-official`, then re-run `/autopilot:medium-build`.

## Operating disciplines

- **Autonomous — never ask the user.** At a decision point, **convene the expert
  council** (see "Deciding at decision points") to deliberate, then decide + record;
  trivial vagueness → decide + record solo. Only the safety stops interrupt the run.
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never hoard
  whole files, diffs, or logs in the main thread; read only bounded slices when you must
  inspect something yourself.
- **Worktree-pinned dispatch.** Every subagent you dispatch — producer, fix-producer,
  reviewer, council advisor — operates **only** inside the run's worktree on its branch,
  **never** main/master. Build each prompt with the absolute worktree path + branch and
  require the subagent to: act by absolute paths under the worktree (or `git -C <worktree>`),
  never rely on inherited cwd, and **before any write assert**
  `git -C <worktree> branch --show-current` equals the run branch — else STOP without editing. Producers dispatched via
  subagent-driven-development inherit this through their task context. (Reviewers are
  read-only but still target the worktree, not main.)
- **Disk-backed.** Persist the spec and a **plan doc** (implementation plan + progress
  section + RESUME block) so the run survives compaction. Location follows the
  user's/project's convention — see **State & resumption**.
- **A STOP is a handoff, never a question:** emit current state + the exact next step a
  human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

## Resume first (the resume contract)

Before anything else, look for an existing **plan doc** with a RESUME block in the
project's convention location. If found: reconcile worktree/branch/base_ref existence on
disk, then continue from `phase`. An interrupted **E3** (expert spec review)
re-runs **whole** (idempotent, cheap — there is no marker to resume mid-pass); an
interrupted S5 review round is **re-run from scratch** (re-dispatch the whole frozen
panel — bounded, idempotent), so only `review_round` need be persisted to locate the
loop. No plan doc → start at E1.

## Deciding at decision points (expert council)

When a choice is genuinely in doubt, **convene an expert council** — 2–4 ad-hoc expert
sub-agents (personas from the decision's domain), in **one parallel batch** via
`superpowers:dispatching-parallel-agents`, each returning a concise position (recommendation
+ rationale + trade-offs + any dissent). The orchestrator **synthesizes, decides, and
records** a one-line decision (see **Progress log format**); it is the decider and breaks
ties.

**Convene** when the choice has two-plus viable approaches with materially different
trade-offs, shapes architecture / data model / interface / scope, is costly to reverse, or is
a fork a later review might miss. **Decide solo** (and record) when an obvious default or
convention dictates, or it is cosmetic / local / easily reversible (a wrong guess is caught
by S5). Pay-per-use: fires zero-plus times per run. Fewer than two distinct lenses → smaller
council or solo; never fabricate personas to hit a count.

## E3 — expert spec review (one-shot; not a Ralph loop)

E3 is the trimmed path's spec check — it **replaces both S1 and the human-review gate** with
a single reviewer pass. It is **ONE-SHOT: not a Ralph loop, with no convergence marker.**

- After E2 writes the spec, **dispatch ONE `general-purpose` expert sub-agent** (by
  reference, read-only — "Read-only. Modify nothing.") to review the spec for soundness /
  completeness / approach. It returns a **concise position (advice)** — **NOT** the
  `VERDICT/BLOCKING/NON-BLOCKING` grammar (that grammar belongs to the S5 review panel
  only). One reviewer is the light-path default; this is the spec check, not a deliberation.
  (Only if the spec presents a genuine fork with materially different trade-offs, escalate
  to a small council per "Deciding at decision points".)
- The orchestrator **synthesizes** the position, **revises the spec once** (edit the spec
  doc directly), and **records the one-line decision** (see **Progress log format**). Then
  it **proceeds** — there is **no `AUTOPILOT: SPEC READY` marker**, no second pass.
- This is the autonomous, independent spec check (the reviewer ≠ the author) standing in
  for the dropped human gate — cheaper than `build`'s S1 roster panel.
- **Resume:** an interrupted E3 re-runs **whole** (idempotent, cheap) — there is no marker
  to resume mid-pass.
- **Root-contradiction STOP still applies:** if the reviewer finds the core requirement
  asks for two things that cannot both be true, STOP and hand off — quote the two
  conflicting clauses (a handoff, never a question; mere vagueness is decided, not stopped).

## Task-list slice (replaces S2 / writing-plans) — the entry action of S3

medium-build has **no S2 / writing-plans**. After C, the orchestrator writes a **terse task
list** — **one line per task, ordered, no code, no TDD scaffold** — into the **plan doc's
implementation-plan section** (the same location `build`'s writing-plans uses, just
authored inline). **S3's subagent-driven-development then discovers the task list from the
plan doc** exactly as in `build` (plan doc → SDD); the list is NOT passed as a separate
argument. This slice is the **entry action of S3**, not its own resumable phase.

## Review rounds (S5)

- **Select, trim, freeze.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py"
  --phase work --worktree <worktree> --base <base_ref>` → a `selected` list of
  `{agent, subagent_type, tier, matched}`. Its `core` lenses (correctness,
  requirement-fidelity, doc) are the mandatory floor — take them as-is; **trim, don't pad**
  (the trimmed-path policy): drop the `optional` lenses unless a changed-path signal clearly
  warrants one, never add beyond what the script returns. Freeze & log the composed panel to
  the **plan doc** progress section as the one-line freeze shape (see **Progress log
  format**); reuse it every round of S5.
- **Dispatch the whole round together** — never one at a time, re-reviews included. Build
  each member's run-input prompt once — "PHASE=work. Inputs: worktree=…, base_ref=…,
  spec_doc=…, plan_doc=…, requirement=…, focus=…. Output ONLY the verdict, no prose."
  Reviewers read the worktree at the given absolute paths, never main.
  (absolute paths) — the identical prompt rides whichever transport carries it:
  - **Workflow transport (preferred; roster and ad-hoc members):** one call per round —
    `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/scripts/review-round.js", args: {phase: "work", members: [{agent, subagent_type, prompt}, …]}})`,
    `args` a real JSON object (it tolerates a stringified one; don't rely on it). Members keep
    their own model + read-only allowlist (`agentType` resolves like `Task`). The call returns
    a task ID; the round's verdicts arrive in its completion notification as `{phase, verdicts:
    [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}, …]}` — wait for it (never poll/judge
    early). Never pass `resumeFromRunId` — every round is a fresh run. `synthetic: true` = that
    member's infra failure, not a FAIL: once all initial results are in (incl. ad-hoc),
    re-dispatch just those lenses once via `Task`; still nothing → FAIL. No `verdicts` array, or
    one shorter than sent (incl. `[]`) → failed/partial → Task fallback for the missing members.
  - **Ad-hoc members ride the SAME `members` list** as `subagent_type: "general-purpose"`,
    their `prompt` carrying the persona + "Read-only. Modify nothing." + the "Verdict grammar"
    block below (call `StructuredOutput` when offered). Their read-only is **prompt-enforced
    only** (no tool allowlist), so the prompt MUST carry it. They follow the SAME dual fallback
    as roster: the whole-round Task fallback, and the per-member `synthetic` single Task
    re-dispatch — dispatch ad-hoc directly via `Task` only when the whole round already fell back.
  - **Task fallback:** if `Workflow` is unavailable or a call failed, dispatch roster members as
    `Task(subagent_type="autopilot:<name>", …)` — body is the system prompt; send ONLY the
    run-input prompt, all calls in one message (`superpowers:dispatching-parallel-agents`), rest
    of the run. The transport + any fallback that fired ride the freeze line's `transport=` field
    (see **Progress log format**) — not a separate log line.
- Each reviewer returns the verdict block; collect verdicts → the Ralph loop.

medium-build has no S1, so **S5** (work review) is the only convergence loop: review → fix →
re-review, **cap = 1** (round 0 + at most one fix round — NOT the config default; E3 is
one-shot, not governed here). Blocker text primes the fix transiently, never logged. Every
reviewer is a fresh instance; convergence is read from the verdicts, and the marker is
printed only when genuinely converged.

- **The loop.** The orchestrator runs the rounds itself and logs each round as one line
  (see **Progress log format**).
- **Round 0** = full frozen panel; all-PASS short-circuits.
- **The one re-review (N=1)** dispatches only **`(FAILed ∪ touched) ∩ frozen panel`** —
  *FAILed* = last verdict FAIL/missing; *touched* = lenses whose `applies_to` matches the
  fix's changed files (record the **pre-fix HEAD**, re-run `select-panel.py --phase work
  --worktree <worktree> --base <pre-fix HEAD>`; cores always match). Ad-hoc lenses re-run iff FAILed. Skipped
  lenses carry their PASS; `∪ touched` re-checks what a fix might regress.
- **Advance** when every frozen-panel lens is PASS with no open BLOCKING → `AUTOPILOT: WORK
  READY` → S6. Cap (= 1) hit without the marker → non-convergence STOP (oscillation |
  unfixable | requirements-conflict) + handoff.

## Verdict grammar (paste into ad-hoc summon prompts only — roster agents already embed it)

Output ONLY the verdict — no prose/preamble. When a `StructuredOutput` tool is offered
(Workflow transport), the verdict IS that call: `{VERDICT: PASS|FAIL, BLOCKING: [...],
NON_BLOCKING: [...]}`, nothing else. Else (Task fallback) emit exactly:

```
VERDICT: PASS            # or exactly: VERDICT: FAIL
BLOCKING: none           # or one "- " item per line
NON-BLOCKING: none       # or one "- " item per line
```

PASS ⟺ no blocking items. Cite evidence (file:line / spec clause); flag blockers, not
preferences. A missing, unparseable, or empty-on-FAIL verdict counts as **FAIL**.
Convergence is decided from these on-disk verdicts, never from vibes.

<!-- progress-log-format:start -->
## Progress log format

The plan doc's progress section is a simple one-line-per-event log (audit trail, not a
transcript): one line each for the panel freeze, every review round (lens=VERDICT roll-up +
blocker count), and every decision. Only `review_round` (RESUME block) is load-bearing for
resume; blocker text is transient — hold it to prime the fix, never persist it to disk. Keep
these plus the final residual NON-BLOCKING items; drop everything else.
<!-- progress-log-format:end -->

## Pipeline (E1, E2, E3, S3–S7)

Legend: **E#** = entry phase; **E3** = the one-shot expert spec review; **S#** =
the shared spine (trimmed path skips S1 and S2). Pipeline: **E1 → E2 → E3 → S3 → S4 → S5 →
S6 → S7**.

- **E1 — worktree (step 1).** Use `superpowers:using-git-worktrees` → branch
  `autopilot/<slug>`. Slug = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens,
  collapsed/trimmed, truncated to ~40 chars. Record worktree/branch/base_ref (HEAD) in the
  RESUME block; create the **plan doc** (RESUME + progress section) per the project's
  convention. On worktree/branch collision: one retry with a uniquified slug (`-2`, …),
  else STOP.
- **E2 — brainstorm (step 2).** Use `superpowers:brainstorming` on `$ARGUMENTS` → write the
  spec into the spec doc (spec + inline self-review: placeholder / consistency / scope /
  ambiguity). At decision points, convene the expert council; record the decision (see
  **Progress log format**; trivial defaults: decide + record).
- **E3 — expert spec review (step 3).** Run the **one-shot spec review** (see "E3 — expert
  spec review" above): dispatch ONE `general-purpose` expert reviewer, synthesize, revise
  the spec once, record the one-line decision, proceed. **Not a Ralph loop, no marker.**
- **Task-list slice.** Write the terse ordered 1-line-per-task list into the plan doc's
  implementation-plan section (see "Task-list slice"). This is the entry action of S3.
- **S3 — produce (step 4).** Produce the work product. Code →
  `superpowers:subagent-driven-development`, driven by the plan doc's task list: keep its
  per-task reviews (early-catch), SKIP its final whole-implementation review — S5 is the
  authoritative whole-diff gate. Producers do **NOT** consult the council. It may commit
  per task; the S6 squash folds its commits. Non-code → producer subagents via the same
  dispatch pattern. The orchestrator never edits the work product itself. (worktree-pinned — see Operating disciplines)
- **S4 — verify (step 5).** Use `superpowers:verification-before-completion`: run the
  discovered checks. For THIS plugin = `claude plugin validate` + `python3
  tests/test_scripts.py` + the documented manual smoke. Cap fixes at 3. Never weaken, skip,
  or delete a check; a drop in the check count → STOP.
- **S5 — work review (step 6).** Run the S5 review loop (see **Review rounds**; **cap = 1**)
  over the work. **Fixes:** ONE fresh producer subagent primed with the deduped open blockers +
  cited files only (worktree-pinned — see Operating disciplines). Docs are always part of S5: the pinned `doc-reviewer` gates repo-wide
  doc currency/concision (stale/missing/contradictory docs = BLOCKING → fixed by the S5
  producer; bloat = NON-BLOCKING). On convergence it records `AUTOPILOT: WORK READY`.
- **S6 — squash (step 7).** Idempotent squash to one commit (skip if already exactly 1
  ahead of base_ref). Working notes (spec/plan/progress) are committed or ignored per the
  project's convention — do not force either.
- **S7 — finish (step 8).** Use `superpowers:finishing-a-development-branch` → report
  review history, decisions, deferred non-blockers (stop-reason first if the run stopped);
  offer integration options as an informational report menu, NOT a question. NO merge. Then
  emit the **Result handoff** block (below) as the final output.

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on the cases below. Every STOP handoff
ends by emitting the **Result handoff** block (`status`=`stopped`, or
`capped-without-pass` at the cap).
1. **Destructive op — only when Auto Mode is OFF.** Before any force-push, write outside
   the worktree, history rewrite beyond this branch, or rm/reset of uncommitted work.
   **In Auto Mode** (auto-accept / bypass-permissions), skip this stop — destructive-op
   judgment is deferred to Auto Mode. The other three stops apply regardless of Auto Mode.
2. **Non-convergence at cap** — the S5 Ralph loop hits `cap` (= 1) without the marker (with
   the classification).
3. **Non-review phase failure** — one retry, then STOP.
4. **Root-contradiction** — the core requirement is self-contradictory; cite the two
   clauses.

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

Thin orchestrator · by-reference dispatch (never pipe diffs into N prompts) · trimmed path =
fewer phases (no S1/S2) + a **minimal S5 panel** (pin correctness + requirement-fidelity +
doc; drop marginal optionals) + **cap = 1** · round-0 short-circuit ·
re-dispatch only the `(FAILed ∪ touched)` subset · bounded subagent prompts, no superpowers
skills loaded into reviewers · producer primed by blockers + cited files only · E3 is one
`general-purpose` spec reviewer (one-shot) · workflow transport returns a
round's verdicts as one JSON payload (reviewer output stays off the main thread) · progress
log is one-line-per-event (see **Progress log format**).

## State & resumption

Persist two things so the run survives compaction: the **spec** (E2's output, revised once
in E3 — E1 writes only the plan doc's progress section, the task-list slice fills the
implementation-plan section) and the **plan doc** (implementation plan + progress section,
carrying the RESUME block):

```
RESUME: phase=<E1|E2|E3|S3|S4|S5|S6|S7> worktree=<path> branch=<name> base_ref=<sha> review_round=<n>
```

**Keep RESUME current:** rewrite it at every phase transition — `phase=` as you advance
(E1→E2→E3→S3→S4→S5→S6→S7) and `review_round=` each S5 loop iteration. The resume contract
(**Resume first**) depends on `phase=` reflecting the true current phase; a stale one breaks
resumption. An interrupted **E3** re-runs whole (no marker to resume mid-pass); an
interrupted S5 round re-runs whole (only `review_round` locates the loop).

**Where these live follows the user's / project's existing convention** — honor CLAUDE.md
preferences and existing repo patterns. The command imposes no fixed path (do not assume
`dev-docs/`) and no gitignore-vs-commit policy.
