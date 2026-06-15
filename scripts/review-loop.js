// Claude Autopilot review-loop (a Dynamic Workflows script).
//
// Owns the entire S1/S5 convergence loop: round-0 dispatch + all-PASS
// short-circuit, deterministic convergence judgment, the fix step (one producer
// agent, with the FORK -> council decision path), FAILed-only re-review, cap
// counting, and the 3-way non-convergence classification. The launcher (main
// session) creates the worktree (E1) and composes the frozen panel; this script
// only runs the loop and returns a structured result (see spec section 4). It
// inlines the round dispatch (parallel(agent({schema})) + the VERDICT_SCHEMA /
// normalize copied from review-round.js) so it is one self-contained layer and
// nestable under a future full-spine workflow (spec section 11 #4).
//
// Runtime contract: plain JS with no module dependencies — agent(), parallel(),
// phase(), log(), and the input value `args` are globals provided by the
// workflow runtime. No filesystem, environment, network, or clock/randomness
// APIs are available or used; `args` is the script's only input (an object OR
// its JSON string form — a tool boundary may stringify it; the tail parses it
// back). Every git/test/file action is an agent() (which has Bash + Edit); the
// script itself never shells. Return value (always — the script never throws):
//   { converged, rounds, head, verdicts, blockers, reason, decisions }  (section 4)
export const meta = {
  name: 'autopilot-review-loop',
  description: 'S1/S5 review convergence loop (round0 + fix -> re-review until all-PASS or cap)',
  phases: [{ title: 'Review' }],
}

// `synthetic` is intentionally NOT in the schema: reviewers never set it —
// normalize() populates it in code on every path. Copied verbatim from
// review-round.js (single source once that transport retires).
const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    agent: { type: 'string' },
    VERDICT: { type: 'string', enum: ['PASS', 'FAIL'] },
    BLOCKING: { type: 'array', items: { type: 'string' } },
    NON_BLOCKING: { type: 'array', items: { type: 'string' } },
  },
  required: ['VERDICT', 'BLOCKING', 'NON_BLOCKING'],
  additionalProperties: false,
}

// ──PURE START — self-contained helpers (no runtime globals), sliced + driven by tests.
function normalize(member, v) {
  if (!v) {
    // agent() returned null (skip or terminal error): an infrastructure failure
    // of one member, not a review FAIL — surfaced as a synthetic blocking FAIL.
    return {
      agent: member.agent,
      VERDICT: 'FAIL',
      BLOCKING: ['no verdict returned (skip/terminal error)'],
      NON_BLOCKING: [],
      synthetic: true,
    }
  }
  const blocking = Array.isArray(v.BLOCKING) ? v.BLOCKING.filter(x => typeof x === 'string') : []
  const nonBlocking = Array.isArray(v.NON_BLOCKING) ? v.NON_BLOCKING.filter(x => typeof x === 'string') : []
  // Semantic invariant the schema cannot express: PASS ⟺ blocking empty.
  const verdict = v.VERDICT === 'PASS' && blocking.length === 0 ? 'PASS' : 'FAIL'
  return { agent: member.agent, VERDICT: verdict, BLOCKING: blocking, NON_BLOCKING: nonBlocking, synthetic: false }
}

const dedup = a => [...new Set(a)]
const failedOf = vs => vs.filter(v => v.VERDICT === 'FAIL')

// Merge a fresh (subset) round over the prior verdicts: fresh overrides by agent,
// a lens not re-reviewed keeps its prior verdict.
function carryForward(prev, fresh) {
  const m = new Map(prev.map(v => [v.agent, v]))
  fresh.forEach(v => m.set(v.agent, v))
  return [...m.values()]
}

// 3-way non-convergence classification (heuristic — spec section 11 #3): the
// last two FAIL-blocker-sets identical -> oscillation, else unfixable.
function classify(history) {
  const l2 = history.slice(-2).map(r => failedOf(r).flatMap(v => v.BLOCKING).sort().join('|'))
  return l2.length === 2 && l2[0] === l2[1] ? 'oscillation' : 'unfixable'
}

// Deterministic per-member run-input prompt (ctx = {ph,worktree,base_ref,spec_doc,plan_doc,requirement}).
const memberPrompt = (m, ctx) =>
  `PHASE=${ctx.ph}. Inputs: worktree=${ctx.worktree}, base_ref=${ctx.base_ref}, spec_doc=${ctx.spec_doc || '-'}, ` +
  `plan_doc=${ctx.plan_doc || '-'}, requirement=<<${ctx.requirement}>>, focus=${m.focus}. Output ONLY the verdict, no prose.`

// Re-review subset: FAILed lenses only on every surface (the launcher passes the
// panel; the (FAILed ∪ touched) regression guard is deferred — spec section 11 #2).
const subsetFor = (failed, panel) => {
  const f = new Set(failed.map(v => v.agent))
  return panel.filter(m => f.has(m.agent))
}

// Council personas for a fork — small judgment, heuristic (spec section 11 #6a).
function pickPersonas(fork) {
  // fork content not yet used — personas are fixed (heuristic; spec section 11 #6a). `fork` kept for the roll-out upgrade to fork-derived personas.
  return ['a pragmatic implementer', 'a long-term maintainer']
}
// ──PURE END

// ── decision-point schemas (non-determinism quarantined inside schema'd agents) ──
const POSITION_SCHEMA = {
  type: 'object',
  required: ['recommendation'],
  properties: {
    recommendation: { type: 'string' },
    rationale: { type: 'string' },
    tradeoffs: { type: 'string' },
    dissent: { type: 'string' },
  },
}
const DECISION_SCHEMA = {
  type: 'object',
  required: ['decision'],
  properties: { decision: { type: 'string' }, rationale: { type: 'string' } },
}
const FIX_SCHEMA = {
  type: 'object',
  required: ['status'],
  properties: {
    status: { enum: ['done', 'fork'] },
    head: { type: 'string' },
    changed_files: { type: 'array', items: { type: 'string' } },
    fork: {
      type: 'object',
      properties: {
        question: { type: 'string' },
        options: {
          type: 'array',
          items: { type: 'object', properties: { label: { type: 'string' }, tradeoff: { type: 'string' } } },
        },
      },
    },
  },
}

// ── input ──
let input = args
if (typeof input === 'string') {
  try { input = JSON.parse(input) } catch (_e) { input = null }
}
if (!input || typeof input !== 'object' || !Array.isArray(input.panel) || !Number.isInteger(input.cap)) {
  return { converged: false, rounds: 0, head: null, verdicts: [],
    blockers: ['review-loop: malformed or missing args (need an object with a panel array and an integer cap)'],
    reason: '', decisions: [] }
}
const { phase: ph, worktree, base_ref, requirement, spec_doc, plan_doc, cap, panel } = input
// `touched` reserved in args but not consumed yet — re-review is FAILed-only (spec section 8 / section 11 #2).
const ctx = { ph, worktree, base_ref, spec_doc, plan_doc, requirement }
phase('Review')
const decisions = [] // returned so the launcher persists them (no FS in workflow)

// ── inline round dispatch (was review-round.js) ──
async function dispatchRound(members) {
  const res = await parallel(members.map(m => () =>
    agent(memberPrompt(m, ctx), { agentType: m.subagent_type, schema: VERDICT_SCHEMA, label: m.agent, phase: 'Review' })))
  return members.map((m, i) => normalize(m, res[i]))
}

// ── decision point: producer FORK -> council -> decide ──
async function council(fork) {
  // FIX_SCHEMA only requires `status`, so a {status:'fork'} may arrive with fork/options absent.
  // Treat an ill-formed fork as a no-option fork rather than dereferencing undefined and throwing.
  const options = Array.isArray(fork && fork.options) ? fork.options : []
  const question = (fork && fork.question) || 'unspecified fork'
  const personas = pickPersonas(fork)
  const positions = await parallel(personas.map(p => () =>
    agent(
      `As a ${p}, advise on this fork:\n${question}\nOptions:\n` +
        options.map(o => `- ${o.label}: ${o.tradeoff}`).join('\n') +
        `\nReturn a concise position (recommendation + rationale + tradeoffs + dissent).`,
      { schema: POSITION_SCHEMA, label: `council:${p}`, phase: 'Review' })))
  const d = await agent(
    `Synthesize and DECIDE the fork: ${question}\nPositions:\n${JSON.stringify(positions.filter(Boolean))}\n` +
      `You are the decider. Return {decision, rationale}.`,
    { schema: DECISION_SCHEMA, label: 'synthesize', phase: 'Review' })
  log(`decision(${question.slice(0, 40)}…): ${d.decision}`)
  decisions.push({ question, ...d })
  return d
}

// ── the fix = ONE producer agent; may FORK; returns new head + changed files ──
const MAX_FORKS = 2
async function runFix(blockers) {
  // S1 (spec phase) fixes edit the spec doc; S5 (work phase) fixes write the worktree.
  const target = ph === 'spec'
    ? `Edit the spec doc at ${spec_doc} to resolve them (do NOT write the worktree)`
    : `In ${worktree} (operate by absolute path / git -C ${worktree}), fix them in the worktree, then commit`
  let note = ''
  for (let f = 0; f <= MAX_FORKS; f++) {
    const r = await agent(
      `Read-write producer. Fix ONLY these blockers; ${target}:\n- ${blockers.join('\n- ')}\n${note}\n` +
        `On a GENUINE fork (2+ viable approaches, materially different trade-offs) do NOT guess — ` +
        `return {status:'fork', fork:{question, options}}. ` +
        `Else {status:'done', head:<git -C ${worktree} rev-parse HEAD>, changed_files}.`,
      { schema: FIX_SCHEMA, label: 'fix-producer', phase: 'Review' })
    if (r.status === 'done') return r
    const d = await council(r.fork) // ← decision point handled here
    note = `DECISION: ${d.decision} (${d.rationale}); proceed — do not re-fork on this.`
  }
  return { status: 'stuck' } // repeated forks → deadlock
}

// ── the loop ──
let round = 0
let verdicts = await dispatchRound(panel) // round 0 = full frozen panel
const history = [verdicts]
let head = base_ref
while (true) {
  const failed = failedOf(verdicts)
  if (!failed.length) // all-PASS short-circuit → converged
    return { converged: true, rounds: round, head, verdicts, blockers: [], reason: '', decisions }
  if (round >= cap) // cap → non-convergence STOP
    return {
      converged: false, rounds: round, head, verdicts,
      blockers: dedup(failed.flatMap(v => v.BLOCKING)), reason: classify(history), decisions,
    }
  const fix = await runFix(dedup(failed.flatMap(v => v.BLOCKING))) // ← the WRITE (+ decision points)
  if (fix.status === 'stuck') // decision deadlock → STOP
    return {
      converged: false, rounds: round, head, verdicts,
      blockers: dedup(failed.flatMap(v => v.BLOCKING)), reason: 'requirements-conflict', decisions,
    }
  head = fix.head || head // retain prior sha if producer omitted head (only `status` is required)
  round++
  // S1 (spec phase) re-reviews stay full-panel; S5 (work phase) re-reviews FAILed lenses only.
  const reMembers = ph === 'spec' ? panel : subsetFor(failed, panel)
  verdicts = carryForward(verdicts, await dispatchRound(reMembers))
  history.push(verdicts)
}
