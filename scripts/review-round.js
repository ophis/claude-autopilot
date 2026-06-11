// Claude Autopilot review-round transport (a Dynamic Workflows script).
//
// Dumb transport for ONE review round: the orchestrator computes the panel and
// builds each member's exact run-input prompt; this script only fans the members
// out in parallel and returns schema-validated verdicts. It owns no review
// logic: the PASS demotion below is defense-in-depth at the transport edge —
// the orchestrator's verdict judgment (advance only when every lens is PASS
// with no open BLOCKING) remains authoritative.
//
// Runtime contract: plain JS with no module dependencies — agent(), parallel(),
// phase(), log(), and the input value `args` are globals provided by the
// workflow runtime. No filesystem, environment, network, or clock/randomness
// APIs are available or used; `args` is the script's only input:
//   { phase: "spec"|"work", members: [{ agent, subagent_type, prompt }, ...] }
// Return value (always — the script never throws):
//   { phase, verdicts: [{ agent, verdict, blocking, non_blocking, synthetic }, ...] }
// with exactly one entry per member, in member order.
export const meta = {
  name: 'autopilot-review-round',
  description: 'Dispatch one autopilot review round and return schema-validated verdicts',
  phases: [{ title: 'Review' }],
}

// `synthetic` is intentionally NOT in the schema: reviewers never set it —
// normalize() populates it in code on every path.
const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    agent: { type: 'string' },
    verdict: { type: 'string', enum: ['PASS', 'FAIL'] },
    blocking: { type: 'array', items: { type: 'string' } },
    non_blocking: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'blocking', 'non_blocking'],
  additionalProperties: false,
}

function normalize(member, v) {
  if (!v) {
    // agent() returned null (skip or terminal error): an infrastructure failure
    // of one member, not a review FAIL — the orchestrator re-dispatches the
    // lens once via Task before judging the round.
    return {
      agent: member.agent,
      verdict: 'FAIL',
      blocking: ['no verdict returned (skip/terminal error)'],
      non_blocking: [],
      synthetic: true,
    }
  }
  const blocking = Array.isArray(v.blocking) ? v.blocking.filter(x => typeof x === 'string') : []
  const nonBlocking = Array.isArray(v.non_blocking) ? v.non_blocking.filter(x => typeof x === 'string') : []
  // Semantic invariant the schema cannot express: PASS ⟺ blocking empty.
  const verdict = v.verdict === 'PASS' && blocking.length === 0 ? 'PASS' : 'FAIL'
  return { agent: member.agent, verdict, blocking, non_blocking: nonBlocking, synthetic: false }
}

const members = args && Array.isArray(args.members) ? args.members : []
phase('Review')
log(`dispatching ${members.length} reviewer(s)`)
const results = await parallel(members.map(m => () =>
  agent(m.prompt, { agentType: m.subagent_type, schema: VERDICT_SCHEMA, label: m.agent, phase: 'Review' })
))
return { phase: args ? args.phase : undefined, verdicts: members.map((m, i) => normalize(m, results[i])) }
