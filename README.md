# Claude Autopilot

A Claude Code and Codex **plugin** that packages a high-ceremony, autonomous pipeline for
shipping complex work products (code, but also docs, designs, data, plans). It
replaces a copy-pasted "do all this, summon a team to review, never ask me" prompt
with one explicit command.

> Status: **v0.12.10** — the build surface is now a **skill** (`skills/build`):
> model-invocable and composable as a step inside a larger
> skill/workflow, while `/autopilot:build` still works for users.
> A second surface, **`skills/light-build`** (`/autopilot:light-build`), is
> the low-ceremony path: autonomy + expert-council-at-forks with no
> spec doc and no spec review — an S4 task list, then produce → one capped core
> review with mandatory full verification. **light-build does not gate scope** —
> choosing the right surface is your call (see its section below for when it fits).
> The **named review roster** is complete for both phases in `agents/`, and the
> **selection stage** (`scripts/select-panel.py`) wires the roster into the S3/S6
> review loops — the skills select the panel from the roster and dispatch each round
> through the available host transport
> (see [Host runtime](skills/host-runtime.md) and [Review roster](#review-roster-agents)).

## Repository structure

The git repo is **both the marketplace and the plugin**:

```
claude-autopilot/                 # git repo = marketplace + plugin
├── .claude-plugin/
│   ├── plugin.json               # name: autopilot (version 0.12.10)
│   └── marketplace.json          # name: claude-autopilot, plugins:[{source:"./"}]
├── skills/
│   ├── build/SKILL.md            # skill; /autopilot:build       still works
│   ├── build/spec.md             # spec-writing guide for build S2
│   ├── light-build/SKILL.md      # skill; /autopilot:light-build  — low-ceremony
│   └── host-runtime.md          # shared Claude Code / Codex execution mappings
├── scripts/
│   ├── _frontmatter.py           # shared frontmatter reader (imported by select-panel.py + lint-roster.py)
│   ├── autopilot-config.py       # reads/initializes host-specific plugin config
│   ├── lint-roster.py            # A3 roster lint: validates each reviewer's frontmatter + contract
│   └── select-panel.py           # selector: (phase, signals) → panel JSON
├── workflows/
│   └── review-round.js           # plugin workflow autopilot:autopilot-review-round — one parallel review round (when the host exposes Workflow)
├── agents/                       # named review roster (ordinary reviewers read-only)
│   ├── reviewer-contract.md      # authoring template, inlined into ordinary reviewers
│   ├── spec-fitness-reviewer.md  # spec / core
│   ├── architecture-reviewer.md  # spec core / work optional (@structural)
│   ├── correctness-reviewer.md   # work / core — purely behavioral
│   ├── requirement-fidelity-reviewer.md   # work / core — work ⊨ requirement & spec
│   ├── doc-reviewer.md           # work / core — repo-wide docs vs the change + concise
│   ├── code-quality-reviewer.md  # work / optional (code)
│   ├── test-reviewer.md          # work / optional (code)
│   ├── performance-reviewer.md   # work / optional (code)
│   ├── security-reviewer.md      # both / optional — conditional, dual-phase
│   └── verification-reviewer.md  # work / core — full checks in isolated checkout
├── tests/
│   └── test_scripts.py           # stdlib unittest for the helper scripts
├── README.md
└── .gitignore                    # ignores per-run state files
```

## Installation

No other plugin is required: every phase of both surfaces uses a native tool, the
plugin's own script, or inline logic.

In Claude Code, this repo is its own single-repo marketplace, so add it and install:

```
/plugin marketplace add https://github.com/ophis/claude-autopilot.git
/plugin install autopilot@claude-autopilot
```

`https://github.com/ophis/claude-autopilot.git` is the marketplace's git URL (the
`owner/repo` shorthand `ophis/claude-autopilot` or a local path works too). You can
also browse and install via the interactive `/plugin` menu (Marketplaces → add →
install).

**Updating:** this plugin uses explicit semver (currently `0.12.10`). A release bumps
`version` in both `plugin.json` and `marketplace.json`; users then refresh with:

```
/plugin marketplace update claude-autopilot
/plugin install autopilot@claude-autopilot
```

### Codex

Install `autopilot@claude-autopilot` from the `claude-autopilot` marketplace in
Codex's plugin manager, then select the installed `autopilot:build` or
`autopilot:light-build` skill and include your requirement in the invoking message.
For a local candidate, explicitly invoke its absolute SKILL.md path. The
[shared host runtime](skills/host-runtime.md) maps the same workflow to exposed
Codex tools; subagent support is required. Codex inherits the session model by
default and reads reviewer instructions from the plugin's canonical agent files.

## `/autopilot:build <requirements>`

A skill, so it is model-invocable now — call it directly, or compose it as a step in a
larger skill/workflow; `/autopilot:build` is preserved for users. Hand it a requirement
and it drives, end to end and without asking you questions:

- **S1 — Worktree:** create `<prefix>-<slug>` worktree+branch (`<prefix>` = the ticket ID when the work is for one single ticket, e.g. `TASK-123`, else `autopilot`); create the plan doc (progress + RESUME).
- **S2 — Spec:** write the spec from the requirement and the affected code (expert council at decision points).
- **S3 — Spec review:** Ralph loop over the spec until the panel passes.
- **S4 — Task list:** a code-free task list (files, cross-task interfaces, tests first, the checks each task runs, commit message); keep the full verify command in the plan progress section, outside producer briefs.
- **S5 — Produce:** one fresh producer per task, in order; each runs only checks covering its changed files, never a full suite; no per-task review (S6 is the gate).
- **S6 — Work review:** Ralph loop over the work; the core `doc-reviewer` gates repo-wide doc currency and the mandatory core `verification-reviewer` runs the full target checks against the same fixed revision as the other reviewers. An unavailable environment stops safely after one retry; genuine check failures enter the fix loop.
- **S7 — Squash:** idempotent squash to one clean commit.
- **S8 — Finish:** report + integration menu. **Never merges.**

You can also hand `/autopilot:build` a path to an existing spec file instead of free-text requirements — it then skips the spec + spec-review (S2/S3) and plans straight from your spec (`S1 → S4`; e.g. `/autopilot:build path/to/spec.md`).

At a genuine decision point it convenes a small **expert council** (ad-hoc sub-agents)
to deliberate, then decides and records — it does not ask you. It stops only to hand off on a
safety condition (non-convergence after 3 review rounds; an unrecoverable phase
failure; a self-contradictory requirement; or an unauthorized destructive git op requiring host approval). Reviews converge via a structured `VERDICT/BLOCKING/
NON-BLOCKING` contract decided from disk, not vibes.

On every terminal path (S8 finish or any safety stop) the run emits, as its final
output, one fenced `autopilot-result` JSON block (`status` / `branch` / `base_ref` /
`head` / `blockers` / `reason`) so a calling workflow reads the outcome without parsing
prose.

State (the spec doc and the plan doc) is persisted so a run survives context compaction and
can be resumed; where those files live follows your own project convention.

### Smoke test (the build eval)

In a throwaway git repo:

```
/autopilot:build add a function add(a,b) with a passing unit test
```

Run in each host (Codex: invoke the installed skill with the same requirement).
Expect: a new isolated worktree+branch; the spec and work review loops
each reach `VERDICT: PASS`; the test actually runs and passes; the run ends at a
**single squashed commit with no merge** and a final report.

Also exercise both surfaces on each host with a fixture whose full checks expose
a failure outside S5's targeted checks: require an S6 FAIL, one committed fix,
fresh re-review and full verification of the fixed SHA. Interrupt a run after S5,
resume from its recorded state, and confirm the final head tree equals the tree
with all-PASS review evidence. Record host, exact invocation/check commands, exit
codes and final `autopilot-result`; record an unavailable scenario with its actual
reason rather than a PASS.

## `/autopilot:light-build <requirements>`

The low-ceremony path. It keeps autopilot's autonomy,
**expert-council-at-forks**, and an S4 task list (orchestrator-written, code-free;
one fresh producer per task) — but drops the rigor: no spec doc (S2), no spec review.
**The requirement IS the spec.** It is **dual-use** — for simple tasks,
and as a lighter alternative to `build` when you want the autonomous interaction model
without the ceremony. It is a skill (model-invocable / composable), emits the same final
`autopilot-result` block, and `/autopilot:light-build` is preserved for users.

- **S1 — Worktree:** create `<prefix>-<slug>` worktree+branch through the host runtime. **State:** no spec doc — the state file is materialized at S4 (see **S4 — Task list**).
- **S4 — Task list:** the orchestrator writes a code-free task list (Global Constraints + per-task `### Task N` briefs: files, Consumes/Produces, tests first, commit message) into the state file — S4 always materializes it. S5 dispatches one fresh producer per task, in order.
- **S5 — Produce:** dispatch one fresh producer per S4 task, in order from the first not `done`, via native host dispatch. On a **genuine fork** the producer returns a `FORK:` marker (options, no guessing) → the orchestrator convenes the expert council, decides, records, and **re-dispatches the producer with the decision**. Producers never consult the council directly.
- **S6 — Work review:** a **pinned** panel — `correctness` + `requirement-fidelity` + `doc` + mandatory `verification`, with full checks run in an isolated checkout against the same revision as other reviewers — **capped at 1** review+fix round. The verifier runs every round; other passed lenses carry their PASS. This is the sole correctness gate.
- **S7 — Squash → S8 — Finish:** one clean commit + report. **Never merges.**

**No scope gate.** light-build is a harness, not a gatekeeper — it runs whatever it is
given. **When it fits:** simple tasks, or any work where you want autonomy + forks-resolved-
by-experts and are comfortable with a single capped review as the only gate (no spec
doc, no spec review — just an S4 task list). Choosing the surface is your responsibility.

```
/autopilot:light-build add a --json flag to the status command
```

Together, `build` → review → re-run `build` to iterate → … is the human-in-the-loop
cycle.

### Invoking from a workflow

Because it is a skill, `build` can be invoked **by name** from another
skill or workflow, not just typed by a user. A nested run is self-contained: it
creates its **own** `<prefix>-<slug>` worktree + branch and persists its own
spec/plan docs (RESUME state is per-run namespaced, so nested runs don't stomp each
other). The pipeline **never merges**, so the calling workflow owns integration of the
returned branch — it reads the outcome from the final `autopilot-result` block
(`status` / `branch` / `base_ref` / `head` / `blockers` / `reason`).

## Review roster (`agents/`)

The committed, accountable review roster. Each reviewer is a **single-lens** agent
that returns the strict `VERDICT / BLOCKING / NON-BLOCKING`
contract, so a review is reproducible and a lens is attributable — unlike anonymous
ad-hoc reviewers chosen anew each time. `phase` is when a lens runs — `spec` (S3
spec-review), `work` (S6 work-review), or `both`. Ordinary reviewers are read-only
and never run a full suite; the verification reviewer runs it in an isolated checkout.

| File | Lens | Phase | Tier |
| --- | --- | --- | --- |
| `agents/reviewer-contract.md` | Authoring template inlined into ordinary reviewers (not dispatched); verification reviewer has a dedicated execution contract | — | — |
| `agents/spec-fitness-reviewer.md` | Spec fitness, gaps, ambiguity, scope, testability | spec | core |
| `agents/architecture-reviewer.md` | Structure, boundaries, coupling, extensibility | both | spec core / work optional (`@structural`) |
| `agents/correctness-reviewer.md` | Intent/logic, edge & boundary cases, error paths | work | core |
| `agents/requirement-fidelity-reviewer.md` | Work realizes the requirement & spec — right thing built, no missing items, no drift/scope creep | work | core |
| `agents/doc-reviewer.md` | Docs **repo-wide** still accurate after the change (not just touched files); edits concise / not bloated | work | core |
| `agents/verification-reviewer.md` | Full target checks with commands, exit codes, failure counts and diagnostics | work | core |
| `agents/code-quality-reviewer.md` | Readability, naming, duplication, dead code, needless complexity, comment quality | work | optional |
| `agents/test-reviewer.md` | Tests meaningful & assert the spec; coverage of new/changed code | work | optional |
| `agents/performance-reviewer.md` | Complexity, N+1, allocation, resource leaks, hotspots | work | optional |
| `agents/security-reviewer.md` | Authz, input validation, secrets, injection, supply chain | both | optional |

The work-phase core lenses form a **requirement → spec → work** chain:
`requirement-fidelity` (the right thing built, faithfully per the spec — no
missing items, no drift or scope creep), `correctness` (built bug-free);
`doc-reviewer` keeps docs **repo-wide** current (not just touched files) and concise.

The **floor** that always runs is the phase's `core` lenses — spec phase:
spec-fitness + architecture; work phase: correctness +
requirement-fidelity + doc-reviewer + verification-reviewer — so every review is
non-empty for any deliverable. `optional` lenses are **conditional**: they run only
when the spec/diff matches their `applies_to`, auditably skipped otherwise. The
`code-quality`/`performance` pack matches code-source files, `test` also matches
test files/dirs; `security` matches auth,
input-handling, network, file/DB I/O, dependency, or crypto signals;
`architecture` is core in the spec phase but a structural-signal-gated optional in
the work phase — it runs in S6 only when the diff changes file topology
(`@structural`: any added/deleted/renamed/copied file).

Each reviewer's frontmatter is **self-describing** (`lens`/`phase`/`tier`/
`applies_to`), so the selection stage discovers and routes the roster with no code
change; new lenses (domain packs) join the same way — a new file under `agents/`.

**Selection stage (`scripts/select-panel.py`).** S3 and S6 call this script to pick the
panel: it globs `agents/`, reads each frontmatter, and returns the selected reviewers as
`{agent, subagent_type, tier, matched}` — every `core` agent for the phase, plus every
`optional` whose `applies_to` matches the signals (spec keywords for S3; changed paths,
`git diff --name-only base...HEAD`, for S6). The orchestrator then runs **all** core
(the floor) and **curates** the optionals (may drop a marginal one). Each member uses
its host-mapped model and tool boundaries; ordinary reviewers remain read-only.
[Host runtime](skills/host-runtime.md) selects Workflow when available or native
agent dispatch, loading canonical reviewer files for generic agents and respecting
concurrency capacity. Re-reviewed lenses start fresh with prior items (ID + blocker
gist) and, in S6, the fix diff. S6 re-reviews failed lenses plus every core lens
(light-build: failed lenses plus the verification reviewer every round); S3
re-reviews the full panel. The S6 fixer is continued through the host's native
operation and runs only checks covering its changed files.
Rounds are batched, and convergence comes only from the reviewers' own verdicts.
Nothing to configure.
Doc upkeep is folded into S6: the core `doc-reviewer` flags stale/missing docs **repo-wide**
(touched files and docs elsewhere the change contradicts) as BLOCKING (fixed in the S6 loop),
so there is no separate docs phase.

### Plugin workflow (`workflows/review-round.js`)

The v0.9.x per-round transport, restored unchanged and shipped as a plugin workflow:
`Workflow({name: "autopilot:autopilot-review-round", args})` (the name comes from its
`meta.name`). It runs one review round — every member in parallel, each verdict
schema-validated — when the host exposes it; native dispatch is the fallback (see
[Host runtime](skills/host-runtime.md)).

- **Input** `args`: `{phase, members: [{agent, subagent_type, prompt}]}`.
- **Output**: `{phase, verdicts: [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}]}`,
  in member order. `VERDICT` is `PASS` only when the reviewer said `PASS` and
  `BLOCKING` is empty. A member that yields no verdict becomes `FAIL` with
  `synthetic: true` and is not retried (the skills re-dispatch it once through native host dispatch).

## Configuration

The plugin keeps its own config in its data dir, separate from host settings.
Claude uses `${CLAUDE_PLUGIN_DATA}/config.json` (fallback
`~/.claude/plugins/data/autopilot-claude-autopilot/config.json`); Codex uses
`${CODEX_HOME:-~/.codex}/plugins/data/autopilot-claude-autopilot/config.json`.
`autopilot-config.py --host claude|codex --data-dir <directory>` can select an explicit
data directory. Omitting flags retains the existing Claude behavior. Example config:

```json
{ "ralphLoop": { "maxIterations": { "spec-phase": 3, "implementation-phase": 3 } } }
```

- **`ralphLoop.maxIterations.spec-phase` / `.implementation-phase`** — per-phase
  round cap for the S3 spec-review / S6 work-review loop (default 3 each).
- **Deprecated: `ralphLoop.enabled`.** The old toggle that drove the loops via the
  optional `ralph-loop` plugin is ignored — the built-in native loop (which can
  re-dispatch only the affected lens subset on re-review rounds) is the only
  driver. A config file still carrying the key is harmless.

build runs `scripts/autopilot-config.py` at startup; it creates the file with defaults
if absent, so edits take effect on the next run. light-build retains its pinned cap of 1.

## Local development

Test changes to this plugin from a local checkout, without installing from a
marketplace:

```
# Load the plugin straight from the working copy (path = the plugin root):
claude --plugin-dir /path/to/claude-autopilot

# After editing files, reload in-session (no restart):
/reload-plugins

# Validate manifests + frontmatter (use --strict in CI to fail on warnings):
claude plugin validate /path/to/claude-autopilot --strict

# Lint the review roster (A3: validates each reviewer's frontmatter + contract):
python3 scripts/lint-roster.py

# Run the script tests (stdlib unittest, no deps):
python3 tests/test_scripts.py
```

Per-build development docs live in `dev-docs/<date>-<slug>-{spec,plan}.md`,
kept locally (gitignored) as the build's audit trail — this is our development
workflow, not something the command imposes on its users.
