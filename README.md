# Claude Autopilot

A Claude Code **plugin** that packages a high-ceremony, autonomous pipeline for
shipping complex work products (code, but also docs, designs, data, plans). It
replaces a copy-pasted "do all this, summon a team to review, never ask me" prompt
with one explicit command.

> Status: **v0.9.0** — the build/fix surfaces are now **skills** (`skills/build`,
> `skills/fix`): model-invocable and composable as a step inside a larger
> skill/workflow, while `/autopilot:build` and `/autopilot:fix` still work for users.
> A third surface, **`skills/medium-build`** (`/autopilot:medium-build`), is the trimmed
> path (no S1 roster panel, no writing-plans; a one-shot single-expert spec review and a
> capped work review). A fourth, **`skills/light-build`** (`/autopilot:light-build`), is
> the **superpowers-free**, low-ceremony path: autonomy + expert-council-at-forks with no
> spec doc and no spec review — just produce → verify → a single capped correctness +
> requirement-fidelity review. **Neither light-build nor medium-build gates scope** —
> choosing the right surface is your call (see each section below for when it fits).
> The **named review roster** is complete for both phases in `agents/`, and the
> **selection stage** (`scripts/select-panel.py`) wires the roster into the S1/S5
> review loops — the skills select the panel from the roster and dispatch each
> reviewer natively as `autopilot:<name>`, preferring one `Workflow` call per review
> round (`scripts/review-round.js`) with automatic `Task` fallback (see
> [Review roster](#review-roster-agents)).

## Repository structure

The git repo is **both the marketplace and the plugin**:

```
claude-autopilot/                 # git repo = marketplace + plugin
├── .claude-plugin/
│   ├── plugin.json               # name: autopilot (version 0.9.0)
│   └── marketplace.json          # name: claude-autopilot, plugins:[{source:"./"}]
├── skills/
│   ├── build/SKILL.md            # skill; /autopilot:build       still works
│   ├── fix/SKILL.md              # skill; /autopilot:fix         still works
│   ├── medium-build/SKILL.md     # skill; /autopilot:medium-build — trimmed path (spec + E3 + capped review)
│   ├── light-build/SKILL.md      # skill; /autopilot:light-build  — superpowers-free, low-ceremony
│   └── _shared/review-loop.md    # no-Workflow fallback for the S1/S5 convergence loop
├── scripts/
│   ├── autopilot-config.py       # reads/initializes ${CLAUDE_PLUGIN_DATA}/config.json
│   ├── lint-roster.py            # A3 roster lint: validates each reviewer's frontmatter + contract
│   ├── review-loop.js            # Dynamic Workflows transport: the S1/S5 convergence loop (round0 + fix → re-review)
│   ├── review-round.js           # Dynamic Workflows transport: one review round → verdict JSON
│   └── select-panel.py           # selector: (phase, signals) → panel JSON
├── agents/                       # named review roster (read-only)
│   ├── reviewer-contract.md      # authoring template, inlined into each reviewer
│   ├── spec-fitness-reviewer.md  # spec / core
│   ├── architecture-reviewer.md  # spec core / work optional (@structural)
│   ├── correctness-reviewer.md   # work / core — purely behavioral
│   ├── requirement-fidelity-reviewer.md   # work / core — work ⊨ requirement & spec
│   ├── doc-reviewer.md           # work / core — repo-wide docs vs the change + concise
│   ├── code-quality-reviewer.md  # work / optional (code)
│   ├── test-reviewer.md          # work / optional (code)
│   ├── performance-reviewer.md   # work / optional (code)
│   └── security-reviewer.md      # both / optional — conditional, dual-phase
├── tests/
│   └── test_scripts.py           # stdlib unittest for the helper scripts
├── README.md
└── .gitignore                    # ignores per-run state files
```

## Installation

### 1. Install the dependency: superpowers (required)

The **build / fix / medium-build** surfaces orchestrate skills from the **superpowers**
plugin (brainstorming, writing-plans, subagent-driven-development, using-git-worktrees,
verification-before-completion, finishing-a-development-branch,
dispatching-parallel-agents). Claude Code has **no plugin dependency / auto-install
mechanism**, so you must install superpowers yourself first:

```
/plugin install superpowers@claude-plugins-official
```

(`planning-with-files` is optional.) Those three surfaces also **preflight-check** for
superpowers and, if it's missing, stop and hand you these instructions rather than failing
midway. **`light-build` is the exception — it is superpowers-free** (every phase uses a
native tool, the plugin's own script, or inline logic) and runs even if superpowers is not
installed; it has no preflight.

### 2. Install Claude Autopilot

This repo is its own single-repo marketplace, so add it and install:

```
/plugin marketplace add https://github.com/ophis/claude-autopilot.git
/plugin install autopilot@claude-autopilot
```

`https://github.com/ophis/claude-autopilot.git` is the marketplace's git URL (the
`owner/repo` shorthand `ophis/claude-autopilot` or a local path works too). You can
also browse and install via the interactive `/plugin` menu (Marketplaces → add →
install).

**Updating:** this plugin uses explicit semver (currently `0.9.0`). A release bumps
`version` in both `plugin.json` and `marketplace.json`; users then refresh with:

```
/plugin marketplace update claude-autopilot
/plugin install autopilot@claude-autopilot
```

## `/autopilot:build <requirements>`

A skill, so it is model-invocable now — call it directly, or compose it as a step in a
larger skill/workflow; `/autopilot:build` is preserved for users. Hand it a requirement
and it drives, end to end and without asking you questions:

- **E1 — Worktree:** create `autopilot/<slug>` worktree+branch; create the plan doc (progress + RESUME).
- **E2 — Brainstorm:** turn requirements into the spec (expert council at decision points).
- **S1 — Spec review:** Ralph loop over the spec until the panel passes.
- **S2 — Plan:** write the execution plan + how it will be verified.
- **S3 — Produce:** implement (subagent-driven for code).
- **S4 — Verify:** run the discovered checks.
- **S5 — Work review:** Ralph loop over the work; the core `doc-reviewer` gates repo-wide doc currency.
- **S6 — Squash:** idempotent squash to one clean commit.
- **S7 — Finish:** report + integration menu. **Never merges.**

You can also hand `/autopilot:build` a path to an existing spec file instead of free-text requirements — it then skips the brainstorm + spec-review (E2/S1) and plans straight from your spec (`E1 → S2`; e.g. `/autopilot:build path/to/spec.md`).

At a genuine decision point it convenes a small **expert council** (ad-hoc sub-agents)
to deliberate, then decides and records — it does not ask you. It stops only to hand off on a
safety condition (non-convergence after 3 review rounds; an unrecoverable phase
failure; a self-contradictory requirement; or — **only when Auto Mode is off** — a
destructive git op). Reviews converge via a structured `VERDICT/BLOCKING/
NON-BLOCKING` contract decided from disk, not vibes.

On every terminal path (S7 finish or any safety stop) the run emits, as its final
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

Expect: a new `autopilot/<slug>` worktree+branch; the spec and work review loops
each reach `VERDICT: PASS`; the test actually runs and passes; the run ends at a
**single squashed commit with no merge** and a final report.

## `/autopilot:medium-build <requirements>`

The **trimmed** path: the same autonomous, thin-orchestrator, disk-backed, never-merge
disciplines as `build`, but a shorter spine for speed. It still writes a spec and reviews
it, but drops the S1 roster panel and writing-plans, uses a **one-shot single expert
reviewer** as the spec review, slices a terse task list inline, and runs a **minimal,
cap-1** work review. It is a skill (model-invocable / composable) and emits the same final
`autopilot-result` block; `/autopilot:medium-build` is preserved for users.

- **E1 — Worktree:** create `autopilot/<slug>` worktree+branch; create the plan doc.
- **E2 — Brainstorm:** turn requirements into the spec.
- **E3 — Expert spec review:** one `general-purpose` expert reviews the spec (advice, not the VERDICT grammar); the orchestrator revises the spec **once** and proceeds — no loop, no marker.
- **Task list:** a terse ordered 1-line-per-task list written straight into the plan doc (no writing-plans).
- **S3 — Produce:** subagent-driven from the plan-doc task list.
- **S4 — Verify:** run the discovered checks.
- **S5 — Work review:** a minimal panel (pin `correctness` + `requirement-fidelity` + `doc`), **capped at 1** review+fix round.
- **S6 — Squash → S7 — Finish:** one clean commit + report. **Never merges.**

**No scope gate.** medium-build is a harness, not a gatekeeper — it runs whatever it is
given and never escalates or hands off on scope. **When it fits:** a focused change where
you still want a written, independently-reviewed spec, but not `build`'s full S1 roster
panel or writing-plans. For bigger or higher-blast-radius work where you want the full
spine, use `/autopilot:build`; for the leanest, superpowers-free path with no spec at all,
use `/autopilot:light-build`. Choosing the surface is your responsibility.

```
/autopilot:medium-build fix the off-by-one in the pagination helper
```

## `/autopilot:light-build <requirements>`

The **superpowers-free**, low-ceremony path. It keeps autopilot's autonomy and
**expert-council-at-forks** but drops the rigor: no spec doc, no brainstorm, no spec review,
no writing-plans. **The requirement IS the spec.** It is **dual-use** — for simple tasks,
and as a lighter alternative to `build` when you want the autonomous interaction model
without the ceremony. It is a skill (model-invocable / composable), emits the same final
`autopilot-result` block, and `/autopilot:light-build` is preserved for users.

Its defining trait is **self-containment**: every phase uses a native tool, the plugin's
own script, or inline logic — it invokes **no `superpowers:*` skill** and runs even if
superpowers is not installed.

- **E1 — Worktree:** create `autopilot/<slug>` worktree+branch (native `EnterWorktree`). **Lazy state:** no spec doc, and no file by default — a minimal state file (the requirement recorded verbatim + a one-line RESUME block) is materialized only at the first compaction-risk boundary; a simple single-shot run writes nothing.
- **S3 — Produce:** dispatch a producer subagent via plain `Task`. On a **genuine fork** the producer returns a `FORK:` marker (options, no guessing) → the orchestrator convenes the expert council, decides, records, and **re-dispatches the producer with the decision**. Producers never consult the council directly.
- **S4 — Verify:** run the discovered checks inline.
- **S5 — Work review:** a **pinned** panel — `correctness` + `requirement-fidelity` + `doc`, `requirement-fidelity` checking the work against the requirement text — **capped at 1** review+fix round. This is the sole correctness gate.
- **S6 — Squash → S7 — Finish:** one clean commit + report. **Never merges.**

**No scope gate.** light-build is a harness, not a gatekeeper — it runs whatever it is
given. **When it fits:** simple tasks, or any work where you want autonomy + forks-resolved-
by-experts and are comfortable with a single capped review as the only gate (no spec, no
spec review). Choosing the surface is your responsibility.

```
/autopilot:light-build add a --json flag to the status command
```

## `/autopilot:fix <feedback>`

The feedback half of the loop. After you review a `build` result, hand `fix` your
review feedback and it drives the **same pipeline on the existing autopilot branch**:
it locates that branch (no new worktree), brainstorms your feedback into a
change-spec, then plans → implements → verifies → reviews (docs currency included) →
**re-squashes** to one clean commit. Still never merges. If there's no autopilot
branch yet, it stops and tells you to run `/autopilot:build` first. Like `build`, it
is a skill — model-invocable / composable as a workflow step (`/autopilot:fix` still
works for users) and it emits the same final `autopilot-result` block.

- **E1′ — Locate:** find the existing autopilot branch (no new worktree); none → stop.
- **E2′ — Brainstorm:** turn feedback into a change-spec appended to the spec doc.
- **S1 — Change-spec review.**
- **S2 — Plan the delta.**
- **S3 — Produce.**
- **S4 — Verify.**
- **S5 — Work review** (docs currency included).
- **S6 — Re-squash:** fold the new commits back into one clean commit.
- **S7 — Finish:** report. **Never merges.**

Legend: **E#** = entry phase (command-specific; `′` = fix variant); **S#** = the
shared spine S1–S7 both commands run.

```
/autopilot:fix the token-refresh path isn't covered by tests
```

Together, `build` → review → `fix` → review → … is the human-in-the-loop cycle.

### Invoking from a workflow

Because they are skills, `build` and `fix` can be invoked **by name** from another
skill or workflow, not just typed by a user. A nested run is self-contained: it
creates its **own** `autopilot/<slug>` worktree + branch and persists its own
spec/plan docs (RESUME state is per-run namespaced, so nested runs don't stomp each
other). The pipeline **never merges**, so the calling workflow owns integration of the
returned branch — it reads the outcome from the final `autopilot-result` block
(`status` / `branch` / `base_ref` / `head` / `blockers` / `reason`).

## Review roster (`agents/`)

The committed, accountable review roster. Each reviewer is a **read-only,
single-lens** agent that returns the strict `VERDICT / BLOCKING / NON-BLOCKING`
contract, so a review is reproducible and a lens is attributable — unlike anonymous
ad-hoc reviewers chosen anew each time. `phase` is when a lens runs — `spec` (S1
spec-review), `work` (S5 work-review), or `both`.

| File | Lens | Phase | Tier |
| --- | --- | --- | --- |
| `agents/reviewer-contract.md` | Authoring template inlined into each reviewer (not dispatched) | — | — |
| `agents/spec-fitness-reviewer.md` | Spec fitness, gaps, ambiguity, scope, testability | spec | core |
| `agents/architecture-reviewer.md` | Structure, boundaries, coupling, extensibility | both | spec core / work optional (`@structural`) |
| `agents/correctness-reviewer.md` | Intent/logic, edge & boundary cases, error paths | work | core |
| `agents/requirement-fidelity-reviewer.md` | Work realizes the requirement & spec — right thing built, no missing items, no drift/scope creep | work | core |
| `agents/doc-reviewer.md` | Docs **repo-wide** still accurate after the change (not just touched files); edits concise / not bloated | work | core |
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
requirement-fidelity + doc-reviewer — so every review is
non-empty for any deliverable. `optional` lenses are **conditional**: they run only
when the spec/diff matches their `applies_to`, auditably skipped otherwise. The
`code-quality`/`test`/`performance` pack matches code files; `security` matches auth,
input-handling, network, file/DB I/O, dependency, or crypto signals;
`architecture` is core in the spec phase but a structural-signal-gated optional in
the work phase — it runs in S5 only when the diff changes file topology
(`@structural`: any added/deleted/renamed/copied file).

Each reviewer's frontmatter is **self-describing** (`lens`/`phase`/`tier`/
`applies_to`), so the selection stage discovers and routes the roster with no code
change; new lenses (domain packs) join the same way — a new file under `agents/`.

**Selection stage (`scripts/select-panel.py`).** S1 and S5 call this script to pick the
panel: it globs `agents/`, reads each frontmatter, and returns the selected reviewers as
`{agent, subagent_type, tier, matched}` — every `core` agent for the phase, plus every
`optional` whose `applies_to` matches the signals (spec keywords for S1; changed paths,
`git diff --name-only base...HEAD`, for S5). The orchestrator then runs **all** core
(the floor), **curates** the optionals (may drop a marginal one), and may add an
**ad-hoc** lens for a gap no roster agent covers. Each roster member runs at its own
model and read-only tool allowlist on either transport (identical prompts):
**preferred**, one `Workflow` call per review round running the plugin's
`scripts/review-round.js` (Dynamic Workflows — background fan-out, schema-validated
verdict JSON; a member's infra failure returns `synthetic: true` and is retried once
via `Task`); **fallback** (tool unavailable or a call failed — sticky for the run),
the parallel `Task(subagent_type="autopilot:<name>")` batch. An ad-hoc review lens
rides the same `Workflow` transport (dispatched as `general-purpose`, schema-validated
like the roster). Nothing to configure.
(Requires the installed plugin ≥ v0.4.0; the workflow transport needs the version
shipping `scripts/review-round.js`.)
Doc upkeep is folded into S5: the core `doc-reviewer` flags stale/missing docs **repo-wide**
(touched files and docs elsewhere the change contradicts) as BLOCKING (fixed in the S5 loop),
so there is no separate docs phase.

## Configuration

The plugin keeps its own config in its data dir — never Claude's managed
`settings.json`. Edit `${CLAUDE_PLUGIN_DATA}/config.json`
(`~/.claude/plugins/data/<plugin-id>/config.json`):

```json
{ "ralphLoop": { "maxIterations": { "spec-phase": 3, "implementation-phase": 3 } } }
```

- **`ralphLoop.maxIterations.spec-phase` / `.implementation-phase`** — per-phase
  round cap for the S1 spec-review / S5 work-review loop (default 3 each).
- **Deprecated: `ralphLoop.enabled`.** The old toggle that drove the loops via the
  optional `ralph-loop` plugin is ignored — the built-in native loop (which can
  re-dispatch only the affected lens subset on re-review rounds) is the only
  driver. A config file still carrying the key is harmless.

The commands run `scripts/autopilot-config.py` at startup; it creates this file with
defaults if absent, so editing it takes effect on the next run.

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
