---
description: "Autonomous pipeline: worktree → spec+review loop → plan → subagent implementation → verify → review loop → squash. Produces a review-ready branch; never merges. Explicit-only."
argument-hint: "<requirements>"
disable-model-invocation: true
---

# Autopilot: build

You are the orchestrator for an autonomous build run. Drive the pipeline below end
to end. Dispatch and judge; do not do the work yourself.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent and has two modes:

- **Requirements mode (default):** free-text requirements → full pipeline (E1 → E2
  brainstorm → S1 spec-review → S2 → …).
- **Spec-file mode:** if `$ARGUMENTS` (trimmed) is a path to an **existing readable
  file** (a spec the user already wrote), adopt it as the run's spec and **skip E2 and
  S1** (run E1 → S2 → …). If it is NOT an existing file, treat it as requirements text
  (normal mode), so a typo'd path safely falls back. The provided spec must be
  **self-contained** — clear enough to plan, implement, and verify without further
  clarification (ideally states acceptance/verification criteria).

If it is empty, STOP with a handoff asking for requirements.

## Preflight (dependencies)

**Load config (run first, every run):** run `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. The `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}'` prefix is **required**: Claude Code inline-substitutes the value into the command text but does *not* export it to the bash subprocess, so the script only receives it when forwarded explicitly (otherwise it uses its fallback dir). It creates `${CLAUDE_PLUGIN_DATA}/config.json` with defaults if absent and prints the effective config. Note `ralphLoop.enabled` and the per-phase caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase` for the S1/S5 Ralph loop. User edits to that file take effect on the next run.

Before E1, confirm the **superpowers** plugin is available — its skills must appear
in your skill list (brainstorming, writing-plans, subagent-driven-development,
using-git-worktrees, verification-before-completion, finishing-a-development-branch,
dispatching-parallel-agents). This whole pipeline is built on them, and Claude Code
has no plugin auto-dependency mechanism, so this preflight is the safety net.

If superpowers is **not** available, STOP with a handoff (not a question): tell the
user it is required and how to install it —
`/plugin install superpowers@claude-plugins-official` — and to re-run `/autopilot:build` after.
(`planning-with-files` is optional.)

`ralph-loop` is required only when `ralphLoop.enabled` is `true` in
`${CLAUDE_PLUGIN_DATA}/config.json`; otherwise it is not needed.

## Operating disciplines

- **Autonomous — never ask the user.** At a decision point, **convene the expert
  council** (see "Deciding at decision points (expert council)") to deliberate, then
  decide + record; trivial vagueness → decide + record solo. Only the safety stops
  interrupt the run.
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never
  hoard whole files, diffs, or logs in the main thread. Read only bounded slices
  when you must inspect something yourself.
- **Disk-backed.** Persist the spec and a **plan doc** — the implementation plan, a
  progress section, and a RESUME block — so the run survives compaction. Location
  follows the user's/project's convention — see **State & resumption**.
- **A STOP is a handoff, never a question:** emit current state + the exact next
  step a human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

## Resume first

Before anything else, look for an existing **plan doc** with a RESUME block in the
project's convention location. If found: reconcile worktree/branch/base_ref
existence on disk, then continue from `phase`. An interrupted review round is
**re-run from scratch** (re-dispatch the whole frozen panel — bounded and
idempotent), so trust only `ralph_round` for loop position. If no plan doc
exists, start at E1.

## Selecting & dispatching the review panel

- **Select from the script.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py"
  --phase spec --spec-file <spec doc>` for S1, and `... --phase work --worktree <worktree>
  --base <base_ref>` for S5. It returns JSON: a `selected` list, each entry
  `{agent, subagent_type, tier, matched}`.
- **Compose the panel:** run ALL returned `core` agents (mandatory floor — never skip
  a core); include the `optional` agents the orchestrator judges relevant (may drop a
  marginal optional); and you MAY add ad-hoc inline lenses for a genuine gap no roster
  agent covers.
- **Freeze & log** the composed panel to the **plan doc** (progress section): which core (all), which
  optionals in/out + why, any ad-hoc added. Reuse the frozen panel every round of that
  phase.
- **Dispatch the whole round's panel in one parallel batch** — issue every `Task` call together in a single message (`superpowers:dispatching-parallel-agents`), never one at a time. This applies to **every** review round in both S1 and S5 (including re-review rounds — whatever subset of lenses a round dispatches, send them together). Parallel dispatch is the intended efficiency; reviewers are independent and read-only.
  - *Roster member* → `Task(subagent_type="autopilot:<name>", …)` (use the
    `subagent_type` from the script). The agent's body is its system prompt; pass ONLY
    run inputs: "PHASE=<spec|work>. Inputs: worktree=…, base_ref=…, requirement=…,
    focus=…. Return ONLY the verdict block." It runs at its own model + read-only
    allowlist.
  - *Ad-hoc member* → `general-purpose` with an inline persona, same verdict contract.
- Each reviewer returns the verdict block; collect verdicts → the Ralph loop (unchanged).

Requires the installed plugin to ship the roster (≥0.3.0).

## Deciding at decision points (expert council)

At a **decision point**, the orchestrator **convenes an expert council**: a small team
(2–4) of **ad-hoc expert sub-agents** (personas derived from the decision's domain),
dispatched in **one parallel batch** via `superpowers:dispatching-parallel-agents`. Each
returns a **concise position** (recommendation + rationale + key trade-offs + any
dissent). The **orchestrator then synthesizes, decides, and records** the decision + the
council's key points (incl. dissent) in the spec/findings/progress. The orchestrator is
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

## Verdict grammar (paste inline into every summon prompt)

```
VERDICT: PASS            # or exactly: VERDICT: FAIL
BLOCKING: none           # or one "- " item per line
NON-BLOCKING: none       # or one "- " item per line
```

PASS ⟺ `BLOCKING: none`; FAIL ⟹ ≥1 blocker. Cite evidence (file:line / spec
clause); flag blockers, not preferences. A missing, unparseable, or empty-on-FAIL
verdict counts as **FAIL**. Convergence is decided from these on-disk verdicts,
never from vibes.

## Ralph loop (S1 and S5)

The two review-convergence phases — **S1** (spec review) and **S5** (work review) —
run a Ralph loop: review → fix → re-review until the panel passes, capped at the
per-phase cap (default 3 rounds). The driver is chosen by config.

**Config (loaded in Preflight):** from `${CLAUDE_PLUGIN_DATA}/config.json` →
`{ "ralphLoop": { "enabled": false, "maxIterations": { "spec-phase": 3, "implementation-phase": 3 } } }`.
`ralphLoop.enabled` picks the driver; `ralphLoop.maxIterations.spec-phase` / `.implementation-phase` is the per-phase round cap (default 3). `ralph-loop` is required only when enabled.

- **Default (`enabled: false`) — native loop.** The orchestrator runs the rounds
  itself: each round, dispatch the frozen panel fresh **in parallel (all that round's members in one batch)** and collect verdicts to disk;
  round-0 all-PASS short-circuits; advance on all-PASS with no open BLOCKING, else
  apply fixes and re-dispatch; cap = `maxIterations.spec-phase` (S1) /
  `maxIterations.implementation-phase` (S5), default 3.
- **`enabled: true` — ralph-loop plugin.** Drive the phase with one
  `/ralph-loop:ralph-loop` whose looped prompt is ONE round and whose
  completion-promise is the phase marker:
  - **S1** → `/ralph-loop:ralph-loop "Run ONE spec-review round: dispatch the frozen S1 panel fresh (read the spec doc); write each VERDICT to the plan doc. If every lens is PASS with no open BLOCKING, print exactly 'AUTOPILOT: SPEC READY'; otherwise edit the spec to resolve every BLOCKING item and do NOT print the marker." --max-iterations <maxIterations.spec-phase> --completion-promise "AUTOPILOT: SPEC READY"`
  - **S5** → `/ralph-loop:ralph-loop "Run ONE work-review round: dispatch the frozen S5 panel fresh against the diff (git diff base_ref...HEAD); write each VERDICT. If every lens is PASS with no open BLOCKING, print exactly 'AUTOPILOT: WORK READY'; otherwise dispatch ONE producer subagent to fix every BLOCKING item, then do NOT print the marker." --max-iterations <maxIterations.implementation-phase> --completion-promise "AUTOPILOT: WORK READY"`

Both drivers obey the same rules: a fresh panel each round; convergence is decided
from the on-disk verdicts (the marker is printed ONLY when convergence is genuinely
true — never to escape the loop); on the marker the phase is done and the command
proceeds (S1→S2, S5→S6) (in spec-file mode the run starts at S2 directly — no S1, no marker); if the per-phase cap (`maxIterations.spec-phase` /
`.implementation-phase`, default 3) is hit WITHOUT the marker → non-convergence STOP
with the 3-way classification (oscillation | unfixable | requirements-conflict) and
a handoff — do not proceed.

## Pipeline (E1, E2, S1–S7)

Legend: **E#** = entry phase (command-specific; `′` = fix variant); **S#** = shared
spine (common to build & fix).

**Entry modes (build):** *requirements mode* (default) runs E1 → E2 → S1 → S2 → …;
*spec-file mode* (when `$ARGUMENTS` is an existing spec file) runs **E1 → S2** — E2
and S1 are skipped, the provided spec becomes the run's spec (record its absolute path
in the RESUME block as `spec_file=<path>`; S2 plans from it; S5's `requirement-fidelity`
reviewer uses it as the work⊨spec reference). Because S1 is skipped, no
`AUTOPILOT: SPEC READY` marker and no S1 root-contradiction stop occur in this mode.

- **E1 — worktree (step 1).** Use `superpowers:using-git-worktrees` → branch
  `autopilot/<slug>`. Slug = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens,
  collapsed/trimmed, truncated to ~40 chars. In **spec-file mode**, derive the slug
  from the spec file's basename — drop the extension and any leading `YYYY-MM-DD-`
  date prefix and trailing `-spec`/`-design`, then apply the slug rule above (e.g.
  `dev-docs/2026-06-08-foo-spec.md` → `foo`). Record worktree/branch/base_ref (HEAD)
  in the RESUME block; create the **plan doc** (RESUME + progress section) per the project's
  convention. On worktree/branch collision: one retry with a uniquified slug
  (`-2`, …), else STOP.
- **E2 — brainstorm (step 2).** Use `superpowers:brainstorming` on `$ARGUMENTS` →
  write the spec into the spec doc. At decision points, convene the expert council (see
  "Deciding at decision points (expert council)") to discuss and decide; record the
  decision + rationale. (Trivial defaults: decide + record.) (**Spec-file mode:**
  skipped — the user-provided spec is adopted as-is.)
- **S1 — spec review (steps 2–3).** Run the **S1 Ralph loop** (above) over the
  (change-)spec. **Fixes:** the orchestrator edits the spec doc directly (the spec
  is a small artifact it holds; only S5 delegates fixes to a producer). On
  convergence it records `AUTOPILOT: SPEC READY`. **Root-contradiction STOP:** if
  the reviewers find the core requirement asks for two things that cannot both be
  true, STOP and hand off — quote the two conflicting clauses (this is a handoff,
  never a question; mere vagueness is decided, not stopped). (**Spec-file mode:**
  skipped — the provided spec is adopted as-is; its `AUTOPILOT: SPEC READY` marker and
  the root-contradiction stop do not apply in this mode.)
- **S2 — plan (step 4).** Use `superpowers:writing-plans` → generate the
  implementation plan and write it into the **plan doc's implementation-plan section**
  (NOT the spec doc); record how the work will be verified. On a consequential plan fork →
  convene the expert council (see "Deciding at decision points (expert council)") to
  decide.
- **S3 — produce (step 5).** Produce the work product. Code →
  `superpowers:subagent-driven-development` (it may commit per task and run its own
  task-level review — that is fine; S5 is the authoritative gate and the S6 squash
  folds its commits). Non-code → producer subagents via the same dispatch pattern.
  The orchestrator never edits the work product itself.
- **S4 — verify (step 6).** Use `superpowers:verification-before-completion`: run
  the discovered checks. For THIS plugin = `claude plugin validate` + the documented
  manual smoke. Cap fixes at 3. Never weaken, skip, or delete a check; a drop in the
  check count → STOP.
- **S5 — work review (step 7).** Run the **S5 Ralph loop** (above) over the work.
  **Fixes:** ONE fresh producer subagent primed with the deduped open blockers + the
  cited files only. Docs are now part of S5: the core `doc-reviewer` gates doc
  currency/concision (stale/missing/contradictory docs = BLOCKING → fixed by the S5
  producer; bloat = NON-BLOCKING). On convergence it records `AUTOPILOT: WORK READY`.
- **S6 — squash (step 8).** Idempotent squash to one commit (skip if already exactly
  1 ahead of base_ref). Working notes (spec/plan/progress) are committed or ignored
  per the project's convention — do not force either.
- **S7 — finish (step 9).** Use `superpowers:finishing-a-development-branch` →
  report: review history, decisions, deferred non-blockers (stop-reason first if the
  run stopped); offer integration options as an informational report menu, NOT a
  question. NO merge.

## Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on:
1. **Destructive op — only when Auto Mode is OFF.** Before any force-push, write
   outside the worktree, history rewrite beyond this branch, or rm/reset of
   uncommitted work. **If the session is in Auto Mode** (auto-accept /
   bypass-permissions), skip this stop — destructive-op judgment is deferred to
   Auto Mode. The other three stops below apply regardless of Auto Mode.
2. **Non-convergence at cap** — a Ralph loop hits `cap` (with the classification).
3. **Non-review phase failure** — one retry, then STOP.
4. **Root-contradiction** — the core requirement is self-contradictory; cite the
   two clauses.

## Token discipline

Thin orchestrator · by-reference dispatch (never pipe diffs into N prompts) ·
smallest panel (2–4, conditional lenses only on signal) · round-0 short-circuit ·
per-phase cap (`maxIterations.spec-phase` / `.implementation-phase`, default 3),
re-dispatch only FAILed/touched lenses · bounded subagent prompts, no
superpowers skills loaded into reviewers · producer primed by blockers + cited files
only · expert councils bounded (2–4), convened only at genuine decision points, in one
parallel batch.

## State & resumption

Persist two things so the run survives compaction: the **spec** (E2's output in
requirements mode, or the user-provided file in spec-file mode — E1 writes only the
plan doc (its progress section); S2 fills the implementation-plan section), and the
**plan doc** (implementation plan + progress section, carrying the RESUME block):

```
RESUME: phase=<E1|E2|S1..S7> worktree=<path> branch=<name> base_ref=<sha> ralph_round=<n> spec_file=<path>
```

(`spec_file` is present only in spec-file mode.)

**Keep RESUME current:** rewrite the RESUME block at every phase transition — update `phase=` as you advance (E1→E2→S1…→S7; spec-file mode advances E1→S2) and `ralph_round=` each loop iteration; the resume contract depends on RESUME reflecting the true current phase, and a stale `phase=` breaks resumption.

**Where these live follows the user's / project's existing convention** — honor
CLAUDE.md preferences and existing repo patterns. The command imposes no fixed path
(do not assume `dev-docs/`) and no gitignore-vs-commit policy.

**Resume contract:** on resume, reconcile worktree/branch existence first, then
continue from `phase`; an interrupted review round is re-run from scratch
(re-dispatch the whole frozen panel — bounded, idempotent), so only `ralph_round`
need be persisted to locate the loop.
