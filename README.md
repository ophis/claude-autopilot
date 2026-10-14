# Claude Autopilot

A Claude Code and Codex **plugin** that packages a high-ceremony, autonomous pipeline for
shipping complex work products (code, but also docs, designs, data, plans). It
replaces a copy-pasted "do all this, summon a team to review, never ask me" prompt
with one explicit command.

> Status: **v1.8.0** — the build surface is now a **skill** (`skills/build`):
> model-invocable and composable as a step inside a larger
> skill/workflow, while `/autopilot:build` still works for users.
> A second surface, **`skills/light-build`** (`/autopilot:light-build`), is
> the low-ceremony path: autonomy + expert-council-at-forks with no
> spec doc and no spec review — an S4 task list, then produce → one capped core
> review, with full verification every round. **light-build does not gate scope** —
> choosing the right surface is your call (see its section below for when it fits).
> The **named review roster** is complete for both phases in `agents/`, and the
> **selection stage** (`skills/build/scripts/select-panel.py`) wires the roster into the S3/S6
> review loops — the skills select the panel from the roster and dispatch each round
> through the available host transport
> (see [Review roster](#review-roster-agents)).

## Repository structure

The git repo is **both the marketplace and the plugin**:

```
claude-autopilot/                 # git repo = marketplace + plugin
├── .claude-plugin/
│   ├── plugin.json               # name: autopilot (version 1.8.0)
│   └── marketplace.json          # name: claude-autopilot, plugins:[{source:"./"}]
├── skills/
│   ├── build/SKILL.md            # skill; /autopilot:build       still works
│   ├── build/spec.md             # spec-writing guide for build S2
│   ├── build/scripts/select-panel.py # selector: (phase, signals) → panel JSON
│   ├── build/scripts/check-spec.py   # S2 spec structure + AC coverage check
│   ├── build/scripts/ci-verdict.py   # publishing: one commit's CI checks → verifier verdict
│   ├── build/scripts/pr.py           # publishing: draft PR start / push / spec / finish, as JSON
│   ├── build/scripts/resolve-branch.py # S1: resume / stay / reuse / create / stop, as JSON
│   ├── build/scripts/_frontmatter.py # parser shared with dev lint
│   └── light-build/SKILL.md      # skill; /autopilot:light-build  — low-ceremony
├── references/
│   └── autopilot-common.md       # rules both skills share; each SKILL.md reads it first
├── scripts/
│   └── lint-roster.py            # roster lint: validates each reviewer's frontmatter + contract
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
│   └── verification-reviewer.md  # work / core — full checks locally or via the PR's CI
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

**Updating:** this plugin uses explicit semver (currently `1.8.0`). A release bumps
`version` in both `plugin.json` and `marketplace.json`; users then refresh with:

```
/plugin marketplace update claude-autopilot
/plugin install autopilot@claude-autopilot
```

### Codex

Invoke the available `autopilot:build` or `autopilot:light-build` skill and
include your requirement in the message. For a local checkout, explicitly ask
Codex to run its absolute `skills/build/SKILL.md` or `skills/light-build/SKILL.md`
path with your requirement. This repo ships Claude marketplace metadata; it does
not currently provide a Codex marketplace manifest or a verified Codex plugin
manager installation procedure. Subagent support is required. Codex reviewers
inherit the session model and receive the canonical agent body and run inputs.

## `/autopilot:build <requirements>`

A skill, so it is model-invocable now — call it directly, or compose it as a step in a
larger skill/workflow; `/autopilot:build` is preserved for users. Hand it a requirement
and it drives, end to end and without asking you questions:

- **S1 — Worktree:** on any branch but `main`/`master`/the local default branch, stay on it; otherwise create a worktree and branch following the [shared S1 conventions](references/autopilot-common.md#worktree-s1) (`<prefix>` = the ticket ID when the work is for one single ticket, e.g. `TASK-123`, else `autopilot`); create the plan doc (progress + RESUME).
- **S2 — Spec:** write the spec from the requirement and the affected code (expert council at decision points); `check-spec.py` checks its sections and that every acceptance criterion has a test or check.
- **S3 — Spec review:** Ralph loop over the spec until the panel passes.
- **S4 — Task list:** a code-free task list, each task one revertable commit (files, cross-task interfaces, tests first, the checks each task runs, commit message); the full verify command sits at the top of the plan doc, outside the task briefs, with the CI checks that run its tests when publishing.
- **S5 — Produce:** the orchestrator implements each task itself, in order (it may hand a self-contained task to a fresh producer); each task's new tests fail before its code exists; each task runs only checks covering its changed files, never a full suite; no per-task review (S6 is the gate).
- **S6 — Work review:** Ralph loop over the work; the core `doc-reviewer` gates repo-wide doc currency and the core `verification-reviewer` checks the same fixed revision as the other reviewers: it runs the full target checks locally, or when publishing reads the CI checks that run the tests for that commit (running the checks locally when CI gives none). A test run of 0 tests fails. An unavailable environment stops safely after one retry; genuine check failures enter the fix loop.
- **S7 — Finish:** report + integration menu (a squash merge gives one commit). **Never merges.**

You can also hand `/autopilot:build` a path to an existing spec file instead of free-text requirements — it then skips the spec + spec-review (S2/S3) and plans straight from your spec (`S1 → S4`; e.g. `/autopilot:build path/to/spec.md`).

**CI and PR mode.** A repo with CI (a pull_request workflow, a GitHub `origin`, an
authenticated `gh`) never runs its full suite locally: before the first S6 round the run
pushes and opens a draft PR, and each round lets CI verify the reviewed commit while the
other reviewers read it. Ask for a pull request in the requirement (e.g. `… and open a
PR`) and it also pushes each task commit as it lands, build posts the reviewed spec as a
comment, and on convergence the PR body gets the final report and the PR is marked ready.
Without the ask, the PR stays a draft for you or your caller to adopt; a PR that was
already ready is drafted for the run and made ready again on convergence, so nobody merges
it mid-review. CI that hasn't finished an hour after the first check stops the run; it
never falls back to a local full suite. A CI failure enters
the same fix loop as any blocker. A PR that conflicts with its base gets no CI, so the run
merges the base in (never rebases) and re-runs the round. With no CI, or a refused push,
the checks run locally.

At a genuine decision point it convenes a small **expert council** (ad-hoc sub-agents)
to deliberate, then decides and records — it does not ask you. It stops only to hand off on a
safety condition (non-convergence after 3 total review rounds per phase; an unrecoverable phase
failure; a self-contradictory requirement; or a destructive operation (force-push,
write outside the worktree, history rewrite beyond the branch, rm/reset of
uncommitted work), unless the session runs with automatic approval (Claude: Auto Mode)).
Reviews converge via a structured `VERDICT/BLOCKING/NON-BLOCKING` contract decided
from disk, not vibes.

On every terminal path (S7 finish or any safety stop) the run emits, as its final
output, one fenced `autopilot-result` JSON block (`status` / `branch` / `base_ref` /
`head` / `pr` / `blockers` / `reason`) so a calling workflow reads the outcome without
parsing prose.

State lives in one plan doc per run (plus build's spec doc), in the worktree's ignored
`.autopilot/` directory, including a Notes section of durable codebase facts, so a run
survives context compaction and can be resumed: after a compaction the orchestrator
re-reads the skill, the plan doc and `git log` before acting. At finish the docs are copied
to your project's plan location if its AGENTS.md / CLAUDE.md names one.

### Smoke test (the build eval)

In a throwaway git repo:

```
/autopilot:build add a function add(a,b) with a passing unit test
```

Expect (run from `main`): a new isolated worktree+branch; the spec and work review loops
each reach `VERDICT: PASS`; the test actually runs and passes; the run ends at a
review-ready branch (one commit per task, one per fix round) **with no merge** and a final report.
Contributor scenarios and evidence requirements: [smoke protocol](CONTRIBUTING.md#smoke-protocol).

## `/autopilot:light-build <requirements>`

The low-ceremony path. It keeps autopilot's autonomy,
**expert-council-at-forks**, and an S4 task list (orchestrator-written, code-free;
implemented by the orchestrator) — but drops the rigor: no spec doc (S2), no spec review.
**The requirement IS the spec.** It is **dual-use** — for simple tasks,
and as a lighter alternative to `build` when you want the autonomous interaction model
without the ceremony. It is a skill (model-invocable / composable), emits the same final
`autopilot-result` block, and `/autopilot:light-build` is preserved for users.

- **S1 — Worktree:** stay on the current branch unless it is `main`/`master`/the local default branch, else create a worktree and branch following the [shared S1 conventions](references/autopilot-common.md#worktree-s1). **State:** no spec doc; S1 creates the plan doc.
- **S4 — Task list:** the orchestrator writes a code-free task list (Global Constraints + per-task `### Task N` briefs, each task one revertable commit: files, Consumes/Produces, tests first, commit message) into the plan doc. S5 implements the tasks in order.
- **S5 — Produce:** the orchestrator implements each S4 task itself, in order from the first not `done`. At a **genuine fork** it convenes the expert council. It may hand a self-contained task to a fresh producer; a producer at a genuine fork returns a `FORK:` marker (options, no guessing) and the orchestrator convenes the council, decides, records, and **re-dispatches the producer with the decision**. Producers never consult the council directly.
- **S6 — Work review:** a **pinned** panel — `correctness` + `requirement-fidelity` + `doc` + `verification` (full checks at the reviewed SHA, the same revision as other reviewers, run locally or read from the PR's CI) — **capped at 3 rounds**: Round 1, then up to two fix/re-reviews. The verifier runs every round, correctness re-reviews a fix after a verifier FAIL, and other passed lenses carry their PASS. This is the sole correctness gate.
- **S7 — Finish:** report + integration menu. **Never merges.**

**No scope gate.** light-build is a harness, not a gatekeeper — it runs whatever it is
given. **When it fits:** simple tasks, or any work where you want autonomy + forks-resolved-
by-experts and are comfortable with a single capped review as the only gate (no spec
doc, no spec review — just an S4 task list). Choosing the surface is your responsibility.

```
/autopilot:light-build add a --json flag to the status command
```

Together, `build` → review → re-run `build` to iterate → … is the human-in-the-loop
cycle. Run the next requirement from the previous run's branch (the session stays in its
worktree after a run) and it continues that branch: its own plan doc, its review covering
only its new commits, and the same PR.

### Invoking from a workflow

Because it is a skill, `build` can be invoked **by name** from another
skill or workflow, not just typed by a user. A nested run stays on the caller's branch
unless that is `main`/`master`/the default branch, where it creates its **own** worktree +
branch following the skill's S1 conventions. Either way it persists its own spec/plan docs
(named per requirement, so runs don't stomp each other). The pipeline **never merges**, so the calling workflow owns integration of the
returned branch — it reads the outcome from the final `autopilot-result` block
(`status` / `branch` / `base_ref` / `head` / `pr` / `blockers` / `reason`).

## Review roster (`agents/`)

The committed, accountable review roster. Each reviewer is a **single-lens** agent
that returns the strict `VERDICT / BLOCKING / NON-BLOCKING`
contract, so a review is reproducible and a lens is attributable — unlike anonymous
ad-hoc reviewers chosen anew each time. `phase` is when a lens runs — `spec` (S3
spec-review), `work` (S6 work-review), or `both`. Ordinary reviewers are read-only
and never run a full suite; the core verification reviewer runs it in the frozen
source worktree at the reviewed SHA, or when publishing reads the CI checks that run the tests for that SHA.

| File | Lens | Phase | Tier |
| --- | --- | --- | --- |
| `agents/reviewer-contract.md` | Authoring template inlined into ordinary reviewers (not dispatched); verification reviewer has a dedicated execution contract | — | — |
| `agents/spec-fitness-reviewer.md` | Spec fitness, gaps, ambiguity, scope, testability | spec | core |
| `agents/architecture-reviewer.md` | Structure, boundaries, coupling, extensibility | both | spec core / work optional (`@structural`) |
| `agents/correctness-reviewer.md` | Intent/logic, edge & boundary cases, error paths | work | core |
| `agents/requirement-fidelity-reviewer.md` | Work realizes the requirement & spec — right thing built, no missing items, no drift/scope creep | work | core |
| `agents/doc-reviewer.md` | Docs **repo-wide** still accurate after the change (not just touched files); edits concise / not bloated | work | core |
| `agents/verification-reviewer.md` | Full target checks with commands, exit codes, test and failure counts and diagnostics, or the CI checks that run them | work | core |
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
requirement-fidelity + doc-reviewer + verification — so every review is
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

**Selection stage (`skills/build/scripts/select-panel.py`).** S3 and S6 call this script to pick the
panel: it globs `agents/`, reads each frontmatter, and returns the selected reviewers as
`{agent, subagent_type, tier, matched}` — every `core` agent for the phase, plus every
`optional` whose `applies_to` matches the signals (spec keywords for S3; changed paths,
`git diff --name-only base...HEAD`, for S6). The orchestrator then runs **all** core
(the floor) and **curates** the optionals (may drop a marginal one). On Claude Code,
each reviewer uses the `model:` / `effort:` in its `agents/<name>.md` frontmatter;
on Codex, it inherits the session model. Canonical tool boundaries apply; ordinary
reviewers remain read-only.
The skills select Workflow when available or native agent dispatch, loading complete
canonical reviewer files for generic agents and respecting
concurrency capacity. Re-reviewed lenses start fresh with prior items (ID + blocker
gist) and, in S6, the fix diff (the re-review sets are in each skill's review
settings). Rounds are batched, and convergence comes only from the reviewers' own verdicts.
Nothing to configure.
Doc upkeep is folded into S6: the core `doc-reviewer` flags stale/missing docs **repo-wide**
(touched files and docs elsewhere the change contradicts) as BLOCKING (fixed in the S6 loop),
so there is no separate docs phase.

### Plugin workflow (`workflows/review-round.js`)

The per-round review transport, shipped as a plugin workflow:
`Workflow({name: "autopilot:autopilot-review-round", args})` (the name comes from its
`meta.name`). It runs one review round — every member in parallel, each verdict
schema-validated — in Claude Code when Workflow is exposed; otherwise the skills
fall back to native dispatch.

- **Input** `args`: `{phase, members: [{agent, subagent_type, prompt}]}`.
- **Output**: `{phase, verdicts: [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}]}`,
  in member order. `VERDICT` is `PASS` only when the reviewer said `PASS` and
  `BLOCKING` is empty. A member that yields no verdict becomes `FAIL` with
  `synthetic: true` and is not retried (the skills re-dispatch it once through native host dispatch).

## Review caps

Build allows three total rounds per phase (S3 spec review and S6 work review):
initial Round 1, then up to two fix/re-reviews in Rounds 2–3. To change a cap for
one run, state it in the requirement. Light-build has the same cap in S6.

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

# Lint the review roster (validates each reviewer's frontmatter + contract):
python3 scripts/lint-roster.py

# Run the script tests (stdlib unittest, no deps):
python3 tests/test_scripts.py
```

Per-build development docs live in `dev-docs/<date>-<slug>-{spec,plan}.md`,
kept locally (gitignored) as the build's audit trail — this is our development
workflow, not something the command imposes on its users.
