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
    VERDICT: { type: 'string', enum: ['PASS', 'FAIL'] },
    BLOCKING: {
      type: 'array',
      items: { type: 'string' },
      description: 'One blocker per item; none is an empty array [], never a "none" item.',
    },
    NON_BLOCKING: {
      type: 'array',
      items: { type: 'string' },
      description: 'One point per item; none is an empty array [], never a "none" item.',
    },
  },
  required: ['VERDICT', 'BLOCKING', 'NON_BLOCKING'],
  additionalProperties: false,
  // PASS ⟹ BLOCKING empty: the runtime rejects a PASS that lists any item, so
  // the reviewer retries instead of the round recording a FAIL it never gave.
  if: { properties: { VERDICT: { const: 'PASS' } } },
  then: { properties: { BLOCKING: { type: 'array', maxItems: 0 } } },
}

function normalize(member, v) {
  if (!v) {
    // agent() returned null (skip or terminal error): an infrastructure failure
    // of one member, not a review FAIL — the orchestrator re-dispatches the
    // lens once via Task before judging the round.
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
  // Recorded PASS ⟺ reviewer PASS with blocking empty; rechecks the schema's rule.
  const verdict = v.VERDICT === 'PASS' && blocking.length === 0 ? 'PASS' : 'FAIL'
  return { agent: member.agent, VERDICT: verdict, BLOCKING: blocking, NON_BLOCKING: nonBlocking, synthetic: false }
}

// Defensive: a tool boundary may hand `args` over as a JSON string instead of an
// object. Parse it back so the round still dispatches; malformed/empty stays a no-op.
let input = args
if (typeof input === 'string') {
  try { input = JSON.parse(input) } catch (_e) { input = null }
}
const members = input && Array.isArray(input.members) ? input.members : []
phase('Review')
log(`dispatching ${members.length} reviewer(s)`)
const results = await parallel(members.map(m => () =>
  agent(m.prompt, { agentType: m.subagent_type, schema: VERDICT_SCHEMA, label: m.agent, phase: 'Review' })
))
return { phase: input ? input.phase : undefined, verdicts: members.map((m, i) => normalize(m, results[i])) }
