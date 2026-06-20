Shared operating protocol for the autopilot build skills. Each skill reads this at Preflight and defines only its own pipeline + deltas. Written superpowers-free and transport-neutral.

## C1 — Operating disciplines

- **Autonomous — never ask user.** At a decision point, **convene expert
  council or decide solo** (see **§C2 Deciding at decision points**).
- **Thin orchestrator.** Dispatch by reference and judge structured output. Never hoard
  whole files, diffs, or logs in main thread; read only bounded slices when you must
  inspect something yourself.
- **Worktree-pinned dispatch.** Give every subagent absolute worktree path + branch and
  have it act only there — absolute paths / `git -C <worktree>`, never inherited cwd — and
  **before any write assert** `git -C <worktree> branch --show-current` is the run branch;
  **never** main/master.
- **A STOP is a handoff, never a question:** emit current state + the exact next step a
  human (or a resumed run) would take. Do not pose questions.
- **No merge.** The run ends at a review-ready branch. You never merge to the base.

(Each skill's state-persistence discipline — Disk-backed or Lazy state — stays inline in the skill.)

## C2 — Deciding at decision points (expert council)

- At a genuine fork — two-plus viable approaches with materially different trade-offs, or a
  choice shaping architecture / data model / interface / scope, costly to reverse, or one a
  later review might miss — **convene a council**: 2–4 ad-hoc expert personas in one parallel
  batch, each returning a concise position
  (recommendation, rationale, trade-offs, dissent). You **synthesize, decide, and record** a
  brief decision (see **§C5 Progress / working-note shapes**) — the decider, breaking ties.
- Otherwise decide solo and record (a wrong guess is caught by review). Never fabricate
  personas to hit a count — fewer than two real lenses → solo.

## C3 — Dispatch transport (neutral core)

Build each review member's run-input prompt once — "PHASE=<spec|work>. Inputs: worktree=…,
base_ref=…, spec_doc=…, plan_doc=…, requirement=…, focus=…. Output ONLY the verdict, no extra
prose." (absolute paths; reviewers read the worktree, never main) — the identical prompt rides
whichever transport carries it:

- **Workflow transport (preferred):** one call per round —
  `Workflow({scriptPath: "${CLAUDE_PLUGIN_ROOT}/scripts/review-round.js", args: {phase: "<spec|work>", members: [{agent, subagent_type, prompt}, …]}})`,
  `args` is a real JSON object (it tolerates a stringified one; don't rely on it). The call returns
  a task ID; the round's verdicts arrive in its completion notification as `{phase, verdicts:
  [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}, …]}` — wait for it (never poll/judge
  early). Never pass `resumeFromRunId` — every round is a fresh run. `synthetic: true` = that
  member's infra failure, not a FAIL: once the round's initial results are all in, re-dispatch just those lenses once via `Task`; still
  nothing → FAIL. No `verdicts` array, or one shorter than sent (incl. `[]`) → failed/partial →
  Task fallback for the missing members.
- **Task fallback:** if `Workflow` is unavailable or a call failed, dispatch roster members as
  `Task(subagent_type="autopilot:<name>", …)` — body is the system prompt; send ONLY the
  run-input prompt, all calls in one batch. The transport + any fallback that fired ride the
  freeze line's `transport=` field (see **§C5 Progress / working-note shapes**) — not a separate
  log line.

## C4 — Verdict grammar (paste into ad-hoc review prompts only)

Output ONLY the verdict — no prose/preamble. When a `StructuredOutput` tool is offered
(Workflow transport), the verdict IS that call: `{VERDICT: PASS|FAIL, BLOCKING: [...],
NON_BLOCKING: [...]}`, nothing else. Else (Task fallback) emit exactly:

```
VERDICT: PASS            # or exactly: VERDICT: FAIL
BLOCKING: none           # or one "- " item per line
NON-BLOCKING: none       # or one "- " item per line
```

PASS ⟺ no blocking items. Cite evidence (file:line / spec or requirement clause); flag
blockers, not preferences. A missing, unparseable, or empty-on-FAIL verdict counts as **FAIL**.
Convergence is decided from these on-disk verdicts, never from vibes.

## C5 — Progress / working-note shapes

The progress section is a simple short-entry log (audit trail, not a transcript): a brief
entry for the panel freeze, every review round (VERDICT roll-up + blocker), and every decision
— keep them short, not necessarily one line. Only `review_round` (RESUME block) is load-bearing
for resume. Keep these plus the final residual NON-BLOCKING items.

Shapes (keep each short):
- **Review round** (VERDICT roll-up + a concise gist per blocker): `S7 r0: correctness=FAIL requirement-fidelity=PASS -> 1 blocker (off-by-one in slice bound), fix dispatched`.
- **Decision** (council or solo, incl. a resolved FORK): `decision(<topic>): chose X over Y - <short reason>; dissent: <one phrase | none>`.

(The panel-freeze shape + where the record lives is skill-specific and stays inline.)

## C6 — Safety stops (handoffs, not questions)

Stop and hand off (state + exact next step) only on the cases below. Every STOP handoff
ends by emitting the **§C7 Result handoff** block (`status`=`stopped`, or `capped-without-pass`
at a cap).
1. **Destructive op — only when Auto Mode is OFF.** Before any force-push, write outside
   the worktree, history rewrite beyond this branch, or rm/reset of uncommitted work.
   **In Auto Mode** (auto-accept / bypass-permissions), skip this stop — destructive-op
   judgment is deferred to Auto Mode. The other three stops apply regardless of Auto Mode.
2. **Non-convergence at cap** — a review loop hits its cap (per-phase for build, cap=1 for
   medium/light), with the classification.
3. **Non-review phase failure** — one retry, then STOP.
4. **Root-contradiction** — the core requirement is self-contradictory; cite the two
   clauses.

## C7 — Result handoff (always emit last)

On **every** terminal path — S9 finish AND any safety-stop handoff — emit as the final
output exactly one fenced `autopilot-result` block (one JSON object) so a caller consumes
the outcome without parsing prose:

```autopilot-result
{ "status": "converged", "branch": "autopilot-<slug>", "base_ref": "<sha>", "head": "<sha>", "blockers": [], "reason": "" }
```

- `status` — `converged` (reached S9) | `capped-without-pass` (a review loop hit its cap) | `stopped` (any other safety stop).
- `branch` / `base_ref` / `head` — branch name, its base SHA, its final commit SHA (`head` = `base_ref` if nothing was produced).
- `blockers` — residual open BLOCKING items (strings) when `status != converged`, else `[]`.
- `reason` — empty when converged; else classification + detail (cap → oscillation | unfixable | requirements-conflict; stop → root-contradiction | phase-failure | destructive-op).
