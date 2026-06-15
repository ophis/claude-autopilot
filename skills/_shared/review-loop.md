# Shared no-Workflow review-loop fallback

This is the **in-session fallback for `scripts/review-loop.js`**, shared across surfaces
(build / fix / medium-build / light-build) — the SKILL pointer Reads it only when the
`Workflow` tool is unavailable. The caller passes the
loop's parameters — **`phase`, `cap`, and the frozen `panel`** (each member `{agent,
subagent_type, focus}`) — plus `worktree`, `base_ref`, `requirement`, `spec_doc`, `plan_doc`.
Do not hard-code any surface's values. Convergence is decided **only** from the structured
verdicts, never from your opinion.

## Loop

1. **Round 0 = the full frozen panel.** Dispatch every panel member in **one parallel `Task`
   batch** (`Task(subagent_type=<member.subagent_type>, …)`, all calls in a single message),
   each primed with `PHASE=<phase>` + the inputs (absolute paths) + its `focus`, "Output ONLY
   the verdict, no prose." Collect the verdicts. **If every lens is PASS with no open BLOCKING
   → all-PASS short-circuit: converged, no fix round.**
2. **On any FAIL → ONE fresh producer subagent.** Prime it with the **deduped open BLOCKING
   items + cited files only** (never paste reviewer prose wholesale). The producer fixes them
   in the worktree (spec-phase fixes edit `spec_doc` instead) and commits. If the producer
   returns a **`FORK:`** (2+ viable approaches, materially different trade-offs): **convene an
   expert council** (2–4 ad-hoc personas, one parallel `Task` batch), **decide** as the tie-
   breaker, **record** a one-line decision, and **re-dispatch the producer with the decision
   baked in** ("DECISION: …; proceed — do not re-fork"). The producer executes the fork; it
   never consults the council itself.
3. **Re-review FAILed lenses only.** Re-dispatch just the lenses that FAILed (spec phase
   re-reviews the full panel). A **skipped lens keeps its prior verdict** (carry forward).
4. **Advance when every frozen-panel lens is PASS with no open BLOCKING** — record the
   convergence marker and proceed to the next phase.
5. **Cap.** Count each fix round against `cap` (round 0 is free). If still failing at `cap`
   without convergence → **STOP** (a handoff, not a question) with the residual blockers and a
   **3-way classification**:
   - **oscillation** — the same blocker set keeps recurring across rounds (fix bounces).
   - **unfixable** — a blocker the producer cannot resolve within scope.
   - **requirements-conflict** — the blockers stem from contradictory requirements; cite them.

Every dispatched reviewer is a fresh instance; an interrupted round re-runs whole (bounded,
idempotent). The marker is printed only when convergence is genuinely true — never to escape
the loop.
