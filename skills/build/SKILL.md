---
name: build
description: "Use to build a new work product from a requirement, end to end: create an isolated worktree, write and review a spec, write a task list, implement, verify, and review-loop to a single review-ready branch (never merges). Pass the requirement text, or a path to an existing spec file; a leading --medium selects the trimmed mode (one-shot spec review, cap-1 work review)."
argument-hint: "[--medium] <requirements|spec-file-path>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, SendMessage, Workflow, Skill, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite, ScheduleWakeup
---

# Autopilot: build

You are the orchestrator for an autonomous build run. Drive the pipeline end to end:
dispatch and judge.

## Your input ($ARGUMENTS)

`$ARGUMENTS` is the single source of intent. A leading `--medium` token selects **medium
mode** (strip it before the rules below): it differs only at S3 (→ S3', see **Pipeline**)
and S7 (cap 1, trimmed panel, see **Review rounds**). The rest is one of two modes:

- **Requirements mode (default):** free-text requirements → full pipeline (S1 → S2 → S3 → S4 → …).
- **Spec-file mode:** if `$ARGUMENTS` is a path to an **existing spec
  file**, adopt it and **skip S2 and S3** (run S1 → S4 → …). The spec
  must be **self-contained** — enough to plan, implement, and verify without further
  clarification. A non-existent path is
  treated as requirements text. (Full rules in **Entry modes** under Pipeline.)

Empty input → STOP with a handoff asking for requirements.

## Preflight (dependencies)

- **Load config:** `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/scripts/autopilot-config.py"`. It prints the effective config, including the per-phase Ralph caps `ralphLoop.maxIterations.spec-phase` / `.implementation-phase`.
- Before S1, confirm **superpowers** plugin is available. If **not** available, STOP with a
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
- **Disk-backed.** Persist the spec and a **plan doc** (task list + progress
  section + RESUME block) so the run survives compaction. Location follows the
  user's/project's convention — see **Resume & state**.
- **A STOP is a handoff, never a question:** emit current state + the exact next step a
  human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

## Resume & state

**On start, resume first.** Look for an existing **plan doc** with a RESUME block in the
project's convention location. If found: reconcile worktree/branch/base_ref existence on
disk, then continue from `phase` in the recorded `mode`. An interrupted S3' re-runs whole.
An interrupted review round is **re-run from scratch**
(re-dispatch the whole frozen panel — bounded — on the transport its freeze line records:
Workflow members fresh + gists; Task continuing recorded agent IDs where reachable, after a
resumed session expect the continuation fallback (fresh + gists)), only `review_round` need be
persisted to locate the loop. No plan doc → start at S1.

**Persist two things** so the run survives compaction: the **spec** (S2's output, or the
user-provided spec file) and the **plan doc** (task list + progress section +
RESUME block):

```
RESUME: phase=<S1..S9> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> spec_file=<path> mode=<full|medium>
```

**Keep RESUME current:** rewrite it at every
phase transition — `phase=` as you advance (S1→S2→S3…→S9, S3' in place of S3 in medium mode;
spec-file mode advances S1→S4),
`review_round=` each loop iteration; stale `phase=` breaks resumption. **Location follows
the user's / project's convention** — honor CLAUDE.md and existing repo patterns.

## Deciding at decision points (expert council)

- At a genuine fork — two-plus viable approaches with materially different trade-offs, or a
  choice shaping architecture / data model / interface / scope, costly to reverse, or one a
  later review might miss — **convene a council**: 2–4 ad-hoc expert personas in one parallel
  batch, each returning a concise position
  (recommendation, rationale, trade-offs, dissent). You **synthesize, decide, and record** a
  brief decision (see **Progress log format**) — the decider, breaking ties.
- Otherwise decide solo and record (a wrong guess is caught by review). Never fabricate
  personas to hit a count — fewer than two real lenses → solo.

## Review rounds (S3 & S7)

- **Select & compose.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/select-panel.py"
  --phase spec --spec-file <spec doc>` (S3) / `... --phase work --worktree <worktree>
  --base <base_ref>` (S7) → a `selected` list of `{agent, subagent_type, tier, matched}`.
  The panel = ALL `core` agents (mandatory) + the `optional` agents you judge relevant (may
  drop marginal ones; medium-mode S7 drops them unless a changed-path signal clearly warrants
  one) + any ad-hoc inline lens for a genuine gap no roster agent covers.
- **Freeze & log** the composed panel to the **plan doc** progress section as the
  freeze shape (see **Progress log format**); reuse it every round of that phase.
- **Dispatch the whole round together** — never one at a time, re-reviews included. Build
  each member's run-input prompt once — "PHASE=<spec|work>. Inputs: worktree=…, base_ref=…,
  spec_doc=…, plan_doc=…, requirement=…, focus=…. Output ONLY the verdict, no extra prose."
  (absolute paths; reviewers read the worktree, never main). Roster members are
  `autopilot:<name>` and get ONLY the run-input prompt (the agent body is its system
  prompt); ad-hoc lenses are `general-purpose`, prompt = persona + "Read-only. Modify
  nothing." + the Verdict grammar block below (read-only is prompt-enforced only).
  - **Workflow transport (default):** one call per round with the whole round's members —
    `Workflow({name: "autopilot:autopilot-review-round", args: {phase: "<spec|work>", members: [{agent, subagent_type, prompt}, …]}})`
    → `{phase, verdicts: [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}, …]}` in member
    order (never pass `resumeFromRunId` — every round is a fresh run). A `synthetic: true`
    member is re-dispatched once via `Task` with its prompt; still no verdict → FAIL.
    Members expose no agent ID, so a re-reviewed lens is a FRESH member whose prompt adds
    its prior items (`<lens>#<n> "<gist>"`, its persisted gists) + the fix diff reference;
    OPEN prior blockers come back in BLOCKING prefixed with their ID.
  - **Task transport (fallback):** the `Workflow` call itself fails (tool unavailable, name
    not resolvable, error, or no result) → run that round via `Task` and stay on Task for
    the rest of the phase (freeze line `->Task`):
    - **Round 0:** one parallel batch of `Task(subagent_type=<member's>, prompt=<member's>)`.
      Record every returned agent ID (see **Progress log format**).
    - **Re-review = continuation:** `SendMessage` to each re-reviewed lens's recorded agent
      ID (all in one batch) with: the fix diff reference, and the fixer's claimed fixes for
      that lens's items (`<lens>#<n> "<gist>"` → where addressed | not addressed) plus `[other]` =
      every other change (location only) — claims to verify, never "I fixed it". Ask for the
      `Prior items:` list, then the verdict. Ad-hoc lenses: restate "Read-only. Modify nothing."
    - **Continuation fallback:** continuation errors, the ID is unknown (earlier rounds on
      Workflow, compaction, resumed session), or no verdict comes back → fresh `Task` of that
      lens with its persisted blocker gists as a checklist (it also emits `Prior items:` for
      them; none → plain fresh review); its new agent ID replaces the recorded one; still no
      verdict → FAIL.
  - **Wait for the whole round:** a Workflow call completes with every verdict at once; Task
    dispatches and continuations run in the background (`run_in_background`), replies
    arriving as hand-back messages plus completion notifications — wait for every member's;
    never poll or judge early. Then ONE fix over all open blockers, then ONE re-review round;
    never fix as single verdicts arrive.
  - **Item IDs:** before deduping for the fixer, label every BLOCKING / NON-BLOCKING item
    `<lens>#<n>`; numbering continues per lens across the phase (never reused). A repeated
    OPEN item keeps its ID (reviewers prefix it); number only new items.
- Each reviewer returns its verdict; collect verdicts → the Ralph loop.

**S3** (spec review) and **S7** (work review) run a native loop: review → fix → re-review
until the frozen panel PASSes, capped per phase by `ralphLoop.maxIterations.spec-phase` /
`.implementation-phase` (default 3, from config); medium mode caps S7 at 1 (round 0 + at most
one re-review), ignoring `.implementation-phase`. Full blocker text primes the fix
transiently; logged only as a concise gist. Re-reviewed lenses carry their prior items (see **Dispatch the whole round together**); convergence holds only when genuinely
all-PASS. The orchestrator runs the rounds itself, logging each briefly (see
**Progress log format**).

- **Round 0** = full frozen panel; all-PASS short-circuits.
- **Re-review (N>0):**
  - S3 stays full-panel. Before each S3 fix, snapshot the spec to `<spec stem>.r<N>.md` beside
    it; the S3 diff reference is `diff -u <snapshot> <spec_doc>` (snapshots stay, gitignored).
  - S7 dispatches only **`(FAILed ∪ touched) ∩ frozen panel`** — *FAILed* = last verdict
    FAIL/missing; *touched* = lenses whose `applies_to` matches the fix's changed files
    (record the **pre-fix HEAD**, re-run `select-panel.py --phase work --worktree <worktree> --base <pre-fix HEAD>`; cores always match). Skipped lenses carry their PASS; `∪ touched`
    re-checks what a fix might regress. S7 diff reference:
    `git -C <worktree> diff <pre-fix HEAD>..HEAD`.
  - Ad-hoc lenses re-run iff FAILed.
- **Advance** when every lens in the round is PASS with no open BLOCKING → proceed
  (S3→S4, S7→S8; spec-file mode starts at S4, no S3). Cap hit without convergence →
  non-convergence STOP (oscillation | unfixable | requirements-conflict) + handoff.
  Convergence comes only from reviewers' own verdicts: never override one — never downgrade
  a blocker, never mark an item INVALID yourself.

## Verdict grammar (paste into ad-hoc review prompts only)

Output **only** the verdict — no preamble, no analysis prose, no essay. Emit exactly
this block:

```
VERDICT: PASS            # or exactly: VERDICT: FAIL
BLOCKING: none           # or one "- " item per line
NON-BLOCKING: none       # or one "- " item per line
```

When continued (or given a prior-items checklist), precede it with one line per prior item:

```
Prior items:
- <lens>#<n>: RESOLVED | OPEN | INVALID — <evidence>
```

Every OPEN prior blocker is repeated in BLOCKING, prefixed with its ID
(`- <lens>#<n>: …`). PASS ⟺ no blocking items; an
unparseable verdict or a `FAIL` with no blocking items counts as **FAIL**.
Cite evidence (file:line / spec clause); flag blockers, not preferences.

<!-- progress-log-format:start -->
## Progress log format

The plan doc's progress section is a simple short-entry log (audit trail, not a
transcript): a brief entry for the panel freeze, every review round (VERDICT roll-up +
blocker), and every decision — keep them short, not necessarily one line. Only
`review_round` (RESUME block) is load-bearing for resume; the per-lens blocker gists prime
fresh re-review members, the agent IDs Task continuation. Keep these plus the final
residual NON-BLOCKING items.

Shapes (keep each short; `S3` rounds use the same shapes as `S7`):
- **Panel freeze:** `S7 panel: core=[correctness,requirement-fidelity,doc] +optional=[code-quality] transport=Workflow` (append `->Task` if the fallback fires).
- **Agent IDs:** `S7 reviewers: correctness=<id> requirement-fidelity=<id> … fixer=<id>` (reviewer IDs on Task only).
- **Review round** (VERDICT roll-up + a concise gist per blocker, with item IDs): `S7 r0: correctness=FAIL requirement-fidelity=PASS -> correctness#1 off-by-one in slice bound; fix dispatched`.
- **Decision** (council or solo, incl. a resolved FORK): `decision(<topic>): chose X over Y - <short reason>; dissent: <one phrase | none>`.
<!-- progress-log-format:end -->

## Pipeline (S1–S9)

**Entry modes:**
- *requirements mode* (default) runs S1 → S2 → S3 → S4 → …;
- *spec-file mode* runs **S1 → S4 → ...**, skipping
  S2 and S3: the provided spec becomes the run's spec — record its absolute path in RESUME
  as `spec_file=<path>`. S3 skipped.

**The pipeline**
- **S1 — worktree.**
  - If already in an isolated worktree (not on `main`/`master`), reuse it — do not nest another. `base_ref` is current local HEAD.
  - Else create worktree on local HEAD, then enter:
    - `<prefix>` = the ticket ID when the work is for one single ticket (e.g. Linear `TASK-123`), else `autopilot`.
    - `<path>` = `.claude/worktrees/<prefix>-<slug>`, ensure `.claude/worktrees/` is gitignored (add it to `.gitignore` if not)
    - `<slug>` = `$ARGUMENTS` lowercased, non-alphanumerics → hyphens, collapsed to <=40 chars; with a ticket prefix, a short feature description instead (not the ticket ID again). On worktree/branch collision: retry with a uniquified slug (`-2`, …).
    - `git worktree add <path> -b <prefix>-<slug> HEAD`
    - `EnterWorktree({path: <path>})`
  - Create the **plan doc** (with RESUME + progress section) at location per the project's convention. Record `worktree`, `branch`, and `base_ref` (HEAD) in the RESUME block.
- **S2 — brainstorm. (Skipped in spec-file mode)** Use `superpowers:brainstorming` on `$ARGUMENTS` → write the spec into the spec doc. At
  decision points, see **Deciding at decision points**; record the decision (see
  **Progress log format**).
- **S3 — spec review. (Skipped in spec-file mode)** Run the S3 review loop (see **Review rounds**) over the
  spec. **Fixes:** the orchestrator edits the spec doc directly
  (snapshot first; it writes the claimed-fixes list).
  **Medium mode → S3' (one-shot expert spec review, not a Ralph loop):** dispatch ONE
  `general-purpose` expert subagent ("Read-only. Modify nothing.") to review the spec → a
  concise position; only on a genuine fork escalate to a small council (see **Deciding at
  decision points**). Synthesize, revise the spec, record the decision (**Progress log
  format** Decision shape), proceed.
  **Root-contradiction STOP:** if reviewers find the core requirement asks for two things
  that cannot both be true, STOP and hand off — quote the two conflicting clauses (a
  handoff, never a question; mere vagueness is decided, not stopped), record the handoff in plan file.
- **S4 — task list.** Do NOT invoke `superpowers:writing-plans`. Write a code-free task
  list into the plan doc's implementation-plan section:
  - Header: spec path; Global Constraints (exact values, the verify command); Review Focus.
  - Per task, a `### Task N: <name>` heading (SDD's `task-brief` extracts by it) with:
    Files; Consumes/Produces (exact names/signatures crossing tasks); tests to write
    first, incl. edge cases; commit message.
  - No code. On a consequential fork → convene the expert council.
- **S5 — produce.** Produce the work product. Code →
  `superpowers:subagent-driven-development`: keep its per-task reviews (early-catch), SKIP
  its final whole-implementation review — S7 is the authoritative whole-diff gate. Non-code → producer subagents via the
  same dispatch pattern. The orchestrator never edits the work product itself.
  (worktree-pinned — see Operating disciplines)
- **S6 — verify.** Use `superpowers:verification-before-completion`: run the
  discovered checks. Never weaken, skip,
  or delete a check.
- **S7 — work review.** Run the S7 review loop (see **Review rounds**) over the work.
  **Fixes:** the first fix dispatches ONE fresh producer subagent primed with the deduped
  open blockers (with item IDs) + cited files only; later fixes continue it via `SendMessage`
  (unknown ID / error → fresh producer, whose ID replaces the recorded one). It returns the claimed-fixes mapping for every change
  it made, incl. non-blockers fixed opportunistically (worktree-pinned — see Operating disciplines). Docs are part of S7.
- **S8 — squash.** Idempotent squash to one commit (skip if already exactly 1
  ahead of `base_ref`). Working notes (spec/plan/progress) are committed or ignored per the
  project's convention — do not force either.
- **S9 — finish.** Inline (no skill): report
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

On **every** terminal path — S9 finish AND any safety-stop handoff — emit as the final
output exactly one fenced `autopilot-result` block (one JSON object) so a caller consumes
the outcome without parsing prose:

```autopilot-result
{ "status": "converged", "branch": "<prefix>-<slug>", "base_ref": "<sha>", "head": "<sha>", "blockers": [], "reason": "" }
```

- `status` — `converged` (reached S9) | `capped-without-pass` (a Ralph loop hit its cap) | `stopped` (any other safety stop).
- `branch` / `base_ref` / `head` — branch name, its base SHA, its final commit SHA (`head` = `base_ref` if nothing was produced).
- `blockers` — residual open BLOCKING items (strings) when `status != converged`, else `[]`.
- `reason` — empty when converged; else classification + detail (cap → oscillation | unfixable | requirements-conflict; stop → root-contradiction | phase-failure | destructive-op).
