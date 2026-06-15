---
name: build
description: "Use to build a new work product from a requirement, end to end: create an isolated worktree, write and review a spec, plan, implement, verify, and review-loop to a single review-ready branch (never merges). Pass the requirement text, or a path to an existing spec file."
argument-hint: "<requirements>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, Skill, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite, ScheduleWakeup
---

# Autopilot: build

You are the orchestrator for an autonomous build run. Drive the pipeline below end
to end: dispatch and judge.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent, in one of two modes:

- **Requirements mode (default):** free-text requirements → full pipeline (E1 → E2 → S1 → S2 → …).
- **Spec-file mode:** if `$ARGUMENTS` (trimmed) is a path to an **existing readable spec
  file**, adopt it as the run's spec and **skip E2 and S1** (run E1 → S2 → …). The spec
  must be **self-contained** — enough to plan, implement, and verify without further
  clarification (ideally with acceptance/verification criteria). A non-existent path is
  treated as requirements text. (Full mode rules in **Entry modes** under Pipeline.)

Empty input → STOP with a handoff asking for requirements.

## Preflight (dependencies)

**Load config (run first, every run):** `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. It creates `${CLAUDE_PLUGIN_DATA}/config.json` with defaults if absent and prints the effective config, including the per-phase Ralph caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase`. User edits to that file take effect next run.

Before E1, confirm the **superpowers** plugin is available — its skills must appear in your
skill list (the whole pipeline is built on them). If **not** available, STOP with a
handoff: it is required, install via
`/plugin install superpowers@claude-plugins-official`, then re-run `/autopilot:build`.

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
disk, then continue from `phase`. An interrupted review round is **re-run from scratch**
(re-dispatch the whole frozen panel — bounded, idempotent), so only `review_round` need be
persisted to locate the loop. No plan doc → start at E1.

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
by S1/S5). Pay-per-use: fires zero-plus times per run. Fewer than two distinct lenses →
smaller council or solo; never fabricate personas to hit a count.

## Review rounds (S1 & S5)

- **Select & compose.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py"
  --phase spec --spec-file <spec doc>` (S1) / `... --phase work --worktree <worktree>
  --base <base_ref>` (S5) → a `selected` list of `{agent, subagent_type, tier, matched}`.
  The panel = ALL `core` agents (mandatory) + the `optional` agents you judge relevant (may
  drop a marginal one) + any ad-hoc inline lens for a genuine gap no roster agent covers.
- **Freeze & log** the composed panel to the **plan doc** progress section as the one-line
  freeze shape (see **Progress log format**); reuse it every round of that phase.
- **Dispatch the whole round together** — never one at a time, re-reviews included. Build
  each member's run-input prompt once — "PHASE=<spec|work>. Inputs: worktree=…, base_ref=…,
  spec_doc=…, plan_doc=…, requirement=…, focus=…. Output ONLY the verdict, no prose."
  Reviewers read the worktree at the given absolute paths, never main.
  (absolute paths) — the identical prompt rides whichever transport carries it:
  - **Workflow transport (preferred; roster and ad-hoc members):** one call per round —
    `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/scripts/review-round.js", args: {phase: "<spec|work>", members: [{agent, subagent_type, prompt}, …]}})`,
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

**S1** (spec review) and **S5** (work review) run a native loop: review → fix → re-review
until the frozen panel PASSes, capped per phase by `ralphLoop.maxIterations.spec-phase` /
`.implementation-phase` (default 3, from config). Blocker text primes the fix transiently,
never logged. Every reviewer is a fresh instance; convergence is read from the verdicts,
and the marker is printed only when genuinely converged.

- **The loop.** The orchestrator runs the rounds itself and logs each round as one line
  (see **Progress log format**).
- **Round 0** = full frozen panel; all-PASS short-circuits.
- **Re-review (N>0)** dispatches only **`(FAILed ∪ touched) ∩ frozen panel`** — *FAILed* =
  last verdict FAIL/missing; *touched* (S5) = lenses whose `applies_to` matches the fix's
  changed files (record the **pre-fix HEAD**, re-run `select-panel.py --phase work
  --worktree <worktree> --base <pre-fix HEAD>`; cores always match). Ad-hoc lenses re-run iff FAILed; S1 stays full-panel
  (its fixes edit the spec). Skipped lenses carry their PASS; `∪ touched` re-checks what a
  fix might regress.
- **Advance** when every frozen-panel lens is PASS with no open BLOCKING → marker → proceed
  (S1→S2, S5→S6; spec-file mode starts at S2, no S1/marker). Cap hit without the marker →
  non-convergence STOP (oscillation | unfixable | requirements-conflict) + handoff.

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

## Pipeline (E1, E2, S1–S7)

Legend: **E#** = entry phase (command-specific; `′` = fix variant); **S#** = shared
spine (common to build & fix).

**Entry modes (build):** *requirements mode* (default) runs E1 → E2 → S1 → S2 → …;
*spec-file mode* (when `$ARGUMENTS` is an existing spec file) runs **E1 → S2**, skipping
E2 and S1: the provided spec becomes the run's spec — record its absolute path in the
RESUME block as `spec_file=<path>`; S2 plans from it; S5's `requirement-fidelity` reviewer
uses it as the work⊨spec reference. With S1 skipped, this mode has no `AUTOPILOT: SPEC
READY` marker and no S1 root-contradiction stop.

- **E1 — worktree (step 1).** Use `superpowers:using-git-worktrees` → branch
  `autopilot/<slug>`. Slug = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens,
  collapsed/trimmed, truncated to ~40 chars. In **spec-file mode**, derive the slug from
  the spec file's basename — drop the extension, any leading `YYYY-MM-DD-` date prefix, and
  trailing `-spec`/`-design`, then apply the slug rule (e.g.
  `dev-docs/2026-06-08-foo-spec.md` → `foo`). Record worktree/branch/base_ref (HEAD) in the
  RESUME block; create the **plan doc** (RESUME + progress section) per the project's
  convention. On worktree/branch collision: one retry with a uniquified slug (`-2`, …),
  else STOP.
- **E2 — brainstorm (step 2).** Use `superpowers:brainstorming` on `$ARGUMENTS` → write the
  spec into the spec doc. At decision points, convene the expert council; record the
  decision (see **Progress log format**; trivial defaults: decide + record). (Skipped in
  **spec-file mode** — provided spec adopted as-is; see **Entry modes**.)
- **S1 — spec review (steps 2–3).** Run the S1 review loop (see **Review rounds**) over the
  (change-)spec. **Fixes:** the orchestrator edits the spec doc directly (the spec is a
  small artifact it holds; only S5 delegates fixes to a producer). On convergence it
  records `AUTOPILOT: SPEC READY`. **Root-contradiction STOP:** if the reviewers find the
  core requirement asks for two things that cannot both be true, STOP and hand off — quote
  the two conflicting clauses (a handoff, never a question; mere vagueness is decided, not
  stopped). (Skipped in **spec-file mode** — no marker, no root-contradiction stop; see
  **Entry modes**.)
- **S2 — plan (step 4).** Use `superpowers:writing-plans` → write the implementation plan
  into the **plan doc's implementation-plan section** (NOT the spec doc); record how the
  work will be verified. On a consequential plan fork → convene the expert council.
- **S3 — produce (step 5).** Produce the work product. Code →
  `superpowers:subagent-driven-development`: keep its per-task reviews (early-catch), SKIP
  its final whole-implementation review — S5 is the authoritative whole-diff gate that
  re-reviews the same diff. It may commit per task; the S6 squash folds its commits.
  Non-code → producer subagents via the same dispatch pattern. The orchestrator never edits
  the work product itself. (worktree-pinned — see Operating disciplines)
- **S4 — verify (step 6).** Use `superpowers:verification-before-completion`: run the
  discovered checks. For THIS plugin = `claude plugin validate` + `python3
  tests/test_scripts.py` + the documented manual smoke. Cap fixes at 3. Never weaken, skip,
  or delete a check; a drop in the check count → STOP.
- **S5 — work review (step 7).** Run the S5 review loop (see **Review rounds**) over the work.
  **Fixes:** ONE fresh producer subagent primed with the deduped open blockers + cited
  files only (worktree-pinned — see Operating disciplines). Docs are part of S5: the core `doc-reviewer` gates repo-wide doc
  currency/concision (stale/missing/contradictory docs = BLOCKING → fixed by the S5
  producer; bloat = NON-BLOCKING). On convergence it records `AUTOPILOT: WORK READY`.
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
output exactly one fenced `autopilot-result` block (one JSON object) so a calling
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

Thin orchestrator · by-reference dispatch (never pipe diffs into N prompts) · smallest
panel (2–4, conditional lenses only on signal) · round-0 short-circuit · per-phase cap
(`maxIterations.spec-phase` / `.implementation-phase`, default 3), re-dispatch only the
`(FAILed ∪ touched)` subset · bounded subagent prompts, no superpowers skills loaded into
reviewers · producer primed by blockers + cited files only · expert councils bounded
(2–4), at genuine decision points only, one parallel batch · workflow transport returns a
round's verdicts as one JSON payload (reviewer output stays off the main thread) · progress
log is one-line-per-event (see **Progress log format**).

## State & resumption

Persist two things so the run survives compaction: the **spec** (E2's output in
requirements mode, or the user-provided file in spec-file mode — E1 writes only the plan
doc's progress section, S2 fills the implementation-plan section) and the **plan doc**
(implementation plan + progress section, carrying the RESUME block):

```
RESUME: phase=<E1|E2|S1..S7> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> spec_file=<path>
```

(`spec_file` is present only in spec-file mode.)

**Keep RESUME current:** rewrite it at every phase transition — `phase=` as you advance
(E1→E2→S1…→S7; spec-file mode advances E1→S2) and `review_round=` each loop iteration. The
resume contract (**Resume first**) depends on `phase=` reflecting the true current phase; a
stale one breaks resumption.

**Where these live follows the user's / project's existing convention** — honor CLAUDE.md
preferences and existing repo patterns. The command imposes no fixed path (do not assume
`dev-docs/`) and no gitignore-vs-commit policy.
