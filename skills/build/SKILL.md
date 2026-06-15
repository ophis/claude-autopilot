---
name: build
description: "Use to build a new work product from a requirement, end to end: create an isolated worktree, write and review a spec, plan, implement, verify, and review-loop to a single review-ready branch (never merges). Pass the requirement text, or a path to an existing spec file."
argument-hint: "<requirements|spec-file-path>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, Skill, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite, ScheduleWakeup
---

# Autopilot: build

You are the orchestrator for an autonomous build run. Drive the pipeline end to end:
dispatch and judge.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent, in one of two modes:

- **Requirements mode (default):** free-text requirements → full pipeline (E1 → E2 → S1 → S2 → …).
- **Spec-file mode:** if `$ARGUMENTS` is a path to an **existing spec
  file**, adopt it and **skip E2 and S1** (run E1 → S2 → …). The spec
  must be **self-contained** — enough to plan, implement, and verify without further
  clarification. A non-existent path is
  treated as requirements text. (Full rules in **Entry modes** under Pipeline.)

Empty input → STOP with a handoff asking for requirements.

## Preflight (dependencies)

- **Load config:** `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. It prints the effective config, including the per-phase Ralph caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase`.
- Before E1, confirm **superpowers** plugin is available. If **not** available, STOP with a
  handoff: superpowers required, install via `/plugin install superpowers@claude-plugins-official`,
  then re-run `/autopilot:build`.

## Operating disciplines

- **Autonomous — never ask user.** At a decision point, **convene expert
  council or decide solo** (see "Deciding at decision points").
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never hoard
  whole files, diffs, or logs in main thread; read only bounded slices when you must
  inspect something yourself.
- **Worktree-pinned dispatch.** Give every subagent absolute worktree path + branch and
  have it act only there — absolute paths / `git -C <worktree>`, never inherited cwd — and
  **before any write assert** `git -C <worktree> branch --show-current` is the run branch;
  **never** main/master. Producers dispatched via subagent-driven-development
  inherit this through their task context.
- **Disk-backed.** Persist the spec and a **plan doc** (implementation plan + progress
  section + RESUME block) so the run survives compaction. Location follows the
  user's/project's convention — see **Resume & state**.
- **A STOP is a handoff, never a question:** emit current state + the exact next step a
  human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

## Resume & state

**On start, resume first.** Look for an existing **plan doc** with a RESUME block in the
project's convention location. If found: reconcile worktree/branch/base_ref existence on
disk, then continue from `phase`. An interrupted review round is **re-run from scratch**
(re-dispatch the whole frozen panel — bounded), only `review_round` need be
persisted to locate the loop. No plan doc → start at E1.

**Persist two things** so the run survives compaction: the **spec** (E2's output, or the
user-provided spec file) and the **plan doc** (implementation plan + progress section +
RESUME block):

```
RESUME: phase=<E1|E2|S1..S7> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> spec_file=<path>
```

**Keep RESUME current:** rewrite it at every
phase transition — `phase=` as you advance (E1→E2→S1…→S7; spec-file mode advances E1→S2),
`review_round=` each loop iteration; stale `phase=` breaks resumption. **Location follows
the user's / project's convention** — honor CLAUDE.md and existing repo patterns.

## Deciding at decision points (expert council)

- At a genuine fork — two-plus viable approaches with materially different trade-offs, or a
  choice shaping architecture / data model / interface / scope, costly to reverse, or one a
  later review might miss — **convene a council**: 2–4 ad-hoc expert personas in one parallel
  batch via `superpowers:dispatching-parallel-agents`, each returning a concise position
  (recommendation, rationale, trade-offs, dissent). You **synthesize, decide, and record** a
  one-line decision (see **Progress log format**) — the decider, breaking ties.
- Otherwise decide solo and record (a wrong guess is caught by review). Never fabricate
  personas to hit a count — fewer than two real lenses → solo.

## Review rounds (S1 & S5)

- **Select & compose.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py"
  --phase spec --spec-file <spec doc>` (S1) / `... --phase work --worktree <worktree>
  --base <base_ref>` (S5) → a `selected` list of `{agent, subagent_type, tier, matched}`.
  The panel = ALL `core` agents (mandatory) + the `optional` agents you judge relevant (may
  drop marginal ones) + any ad-hoc inline lens for a genuine gap no roster agent covers.
- **Freeze & log** the composed panel to the **plan doc** progress section as the one-line
  freeze shape (see **Progress log format**); reuse it every round of that phase.
- **Dispatch the whole round together** — never one at a time, re-reviews included. Build
  each member's run-input prompt once — "PHASE=<spec|work>. Inputs: worktree=…, base_ref=…,
  spec_doc=…, plan_doc=…, requirement=…, focus=…. Output ONLY the verdict, no extra prose."
  (absolute paths; reviewers read the worktree, never main) — the identical prompt rides
  whichever transport carries it:
  - **Workflow transport (preferred):** one call per round —
    `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/scripts/review-round.js", args: {phase: "<spec|work>", members: [{agent, subagent_type, prompt}, …]}})`,
    `args` is a real JSON object (it tolerates a stringified one; don't rely on it). The call returns
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

**S1** (spec review) and **S5** (work review) run a native loop: review → fix → re-review
until the frozen panel PASSes, capped per phase by `ralphLoop.maxIterations.spec-phase` /
`.implementation-phase` (default 3, from config). Blocker text primes the fix transiently,
never logged. Every reviewer is a fresh instance; the marker prints only when genuinely
converged.

- **The loop.** The orchestrator runs the rounds itself, logging each as one line (see
  **Progress log format**).
- **Round 0** = full frozen panel; all-PASS short-circuits.
- **Re-review (N>0):**
  - S1 stays full-panel.
  - S5 dispatches only **`(FAILed ∪ touched) ∩ frozen panel`** — *FAILed* = last verdict
    FAIL/missing; *touched* = lenses whose `applies_to` matches the fix's changed files
    (record the **pre-fix HEAD**, re-run `select-panel.py --phase work --worktree <worktree>
    --base <pre-fix HEAD>`; cores always match). Skipped lenses carry their PASS; `∪ touched`
    re-checks what a fix might regress.
  - Ad-hoc lenses re-run iff FAILed.
- **Advance** when every lens in the round is PASS with no open BLOCKING → marker → proceed
  (S1→S2, S5→S6; spec-file mode starts at S2, no S1/marker). Cap hit without the marker →
  non-convergence STOP (oscillation | unfixable | requirements-conflict) + handoff.

## Verdict grammar (paste into ad-hoc review prompts only)

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
transcript): one line each for the panel freeze, every review round (VERDICT roll-up +
blocker), and every decision. Only `review_round` (RESUME block) is load-bearing for
resume. Keep these plus the final residual NON-BLOCKING items.
<!-- progress-log-format:end -->

## Pipeline (E1, E2, S1–S7)

Legend: **E#** = entry phase (command-specific; `′` = fix variant); **S#** = shared
spine.

**Entry modes (build):** *requirements mode* (default) runs E1 → E2 → S1 → S2 → …;
*spec-file mode* runs **E1 → S2**, skipping
E2 and S1: the provided spec becomes the run's spec — record its absolute path in RESUME
as `spec_file=<path>`. S1 skipped → no `AUTOPILOT: SPEC READY` marker.

- **E1 — worktree (step 1).** Use `superpowers:using-git-worktrees` → branch
  `autopilot/<slug>`. Slug = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens,
  collapsed/trimmed, truncated to <=40 chars. Record worktree/branch/base_ref (HEAD) in the
  RESUME block; create the **plan doc** (with RESUME + progress section) per the project's
  convention. On worktree/branch collision: retry with a uniquified slug (`-2`, …).
- **E2 — brainstorm (step 2).** Use `superpowers:brainstorming` on `$ARGUMENTS` → write the
  spec into the spec doc. At decision points, convene the expert council; record the
  decision (see **Progress log format**; trivial defaults: decide + record). (Skipped in
  **spec-file mode**)
- **S1 — spec review (steps 2–3).** Run the S1 review loop (see **Review rounds**) over the
  spec. **Fixes:** the orchestrator edits the spec doc directly. On convergence records `AUTOPILOT: SPEC READY`.
  **Root-contradiction STOP:** if reviewers find the core requirement asks for two things
  that cannot both be true, STOP and hand off — quote the two conflicting clauses (a
  handoff, never a question; mere vagueness is decided, not stopped), record the handoff in plan file. (Skipped in **spec-file mode**)
- **S2 — plan (step 4).** Use `superpowers:writing-plans` → write implementation plan
  into the **plan doc's implementation-plan section**; record how the
  work will be verified. On a consequential plan fork → convene the expert council.
- **S3 — produce (step 5).** Produce the work product. Code →
  `superpowers:subagent-driven-development`: keep its per-task reviews (early-catch), SKIP
  its final whole-implementation review — S5 is the authoritative whole-diff gate. Non-code → producer subagents via the
  same dispatch pattern. The orchestrator never edits the work product itself.
  (worktree-pinned — see Operating disciplines)
- **S4 — verify (step 6).** Use `superpowers:verification-before-completion`: run the
  discovered checks. Never weaken, skip,
  or delete a check.
- **S5 — work review (step 7).** Run the S5 review loop (see **Review rounds**) over the work.
  **Fixes:** ONE fresh producer subagent primed with the deduped open blockers + cited
  files only (worktree-pinned — see Operating disciplines). Docs are part of S5. On convergence records
  `AUTOPILOT: WORK READY`.
- **S6 — squash (step 8).** Idempotent squash to one commit (skip if already exactly 1
  ahead of base_ref). Working notes (spec/plan/progress) are committed or ignored per the
  project's convention — do not force either.
- **S7 — finish (step 9).** Use `superpowers:finishing-a-development-branch` → report
  review history, decisions, deferred non-blockers (stop-reason first if the run stopped);
  offer integration options as an informational report menu, NOT a question. NO merge. Then
  emit the **Result handoff** block (below) as the final output.

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on the cases below. Every STOP handoff
ends by emitting the **Result handoff** block (`status`=`stopped`, or
`capped-without-pass` at a cap).
1. **Destructive op — only when Auto Mode is OFF.** Before any force-push, write outside
   the worktree, history rewrite beyond this branch, or rm/reset of uncommitted work.
   **In Auto Mode** (auto-accept / bypass-permissions), skip this stop — destructive-op
   judgment is deferred to Auto Mode. The other three stops apply regardless of Auto Mode.
2. **Non-convergence at cap** — a Ralph loop hits `cap` (with the classification).
3. **Non-review phase failure** — one retry, then STOP.
4. **Root-contradiction** — the core requirement is self-contradictory; cite the two
   clauses.

## Result handoff (always emit last)

On **every** terminal path — S7 finish AND any safety-stop handoff — emit as the final
output exactly one fenced `autopilot-result` block (one JSON object) so a caller consumes
the outcome without parsing prose:

```autopilot-result
{ "status": "converged", "branch": "autopilot/<slug>", "base_ref": "<sha>", "head": "<sha>", "blockers": [], "reason": "" }
```

- `status` — `converged` (reached S7) | `capped-without-pass` (a Ralph loop hit its cap) | `stopped` (any other safety stop).
- `branch` / `base_ref` / `head` — branch name, its base SHA, its final commit SHA (`head` = `base_ref` if nothing was produced).
- `blockers` — residual open BLOCKING items (strings) when `status != converged`, else `[]`.
- `reason` — empty when converged; else classification + detail (cap → oscillation | unfixable | requirements-conflict; stop → root-contradiction | phase-failure | destructive-op).
