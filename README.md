# Claude Autopilot

A Claude Code **plugin** that packages a high-ceremony, autonomous pipeline for
shipping complex work products (code, but also docs, designs, data, plans). It
replaces a copy-pasted "do all this, summon a team to review, never ask me" prompt
with one explicit command.

> Status: **v0.2.0** — the `/autopilot:build` and `/autopilot:fix` commands are
> implemented. The **named spec-review roster** now ships its first slice in
> `agents/` (see [Review roster](#review-roster-agents)). The work-phase review pack
> and the selection stage that auto-routes the roster into S1/S5 remain future work;
> until that wiring lands the commands still summon their review lenses ad-hoc inline.

## Installation

### 1. Install the dependency: superpowers (required)

This plugin orchestrates skills from the **superpowers** plugin (brainstorming,
writing-plans, subagent-driven-development, using-git-worktrees,
verification-before-completion, finishing-a-development-branch,
dispatching-parallel-agents). Claude Code has **no plugin dependency / auto-install
mechanism**, so you must install superpowers yourself first:

```
/plugin marketplace add obra/superpowers
/plugin install superpowers@superpowers
```

(`planning-with-files` is optional.) (`ralph-loop` is optional — needed only if you
enable `ralphLoop` in config; see Configuration.) Both
commands also **preflight-check** for superpowers and, if it's missing, stop and hand
you these instructions rather than failing midway.

### 2. Install Claude Autopilot

This repo is its own single-repo marketplace, so add it and install:

```
/plugin marketplace add ophis/claude-autopilot
/plugin install autopilot@claude-autopilot
```

`ophis/claude-autopilot` is the GitHub `owner/repo` shorthand (a full git URL or a
local path works too). You can also browse and install via the interactive
`/plugin` menu (Marketplaces → add → install).

**Updating:** this plugin uses explicit semver (currently `0.2.0`). A release bumps
`version` in both `plugin.json` and `marketplace.json`; users then refresh with:

```
/plugin marketplace update claude-autopilot
/plugin install autopilot@claude-autopilot
```

## `/autopilot:build <requirements>`

Explicit-only (never model-invoked). Hand it a requirement and it drives, end to
end and without asking you questions:

1. Worktree on a new branch (`autopilot/<slug>`).
2. Brainstorm the spec (summon a team on doubt; decide).
3. Review the spec — summon a fresh team, fix, re-review until clean.
4. Write the execution plan.
5. Implement (subagent-driven).
6. Run/verify tests & checks.
7. Review the work — summon a fresh team, fix, re-review until clean.
8. Update the docs.
9. Squash to one clean commit.
10. Report for your review. **It never merges** — you review and integrate.

When in doubt it summons an ad-hoc expert team, decides, has another team challenge
the decision, then fixes — it does not ask you. It stops only to hand off on a
safety condition (non-convergence after 3 review rounds; an unrecoverable phase
failure; a self-contradictory requirement; or — **only when Auto Mode is off** — a
destructive git op). Reviews converge via a structured `VERDICT/BLOCKING/
NON-BLOCKING` contract decided from disk, not vibes.

State (spec, plan, progress) is persisted so a run survives context compaction and
can be resumed; where those files live follows your own project convention.

### Smoke test (the v0.2.0 eval)

In a throwaway git repo:

```
/autopilot:build add a function add(a,b) with a passing unit test
```

Expect: a new `autopilot/<slug>` worktree+branch; the spec and work review loops
each reach `VERDICT: PASS`; the test actually runs and passes; the run ends at a
**single squashed commit with no merge** and a final report.

## `/autopilot:fix <feedback>`

The feedback half of the loop. After you review a `build` result, hand `fix` your
review feedback and it drives the **same pipeline on the existing autopilot branch**:
it locates that branch (no new worktree), brainstorms your feedback into a
change-spec, then plans → implements → verifies → reviews → updates docs →
**re-squashes** to one clean commit. Still never merges. If there's no autopilot
branch yet, it stops and tells you to run `/autopilot:build` first.

```
/autopilot:fix the token-refresh path isn't covered by tests
```

Together, `build` → review → `fix` → review → … is the human-in-the-loop cycle.

(Phase prefixes you'll see in both commands: **E#** = entry phase, command-specific
— `build` E1/E2, `fix` E1′/E2′; **S#** = the shared spine S1–S8 both run.)

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
| `agents/architecture-reviewer.md` | Structure, boundaries, coupling, extensibility | both | core |
| `agents/correctness-reviewer.md` | Intent/logic, edge & boundary cases, error paths | work | core |
| `agents/requirement-satisfaction-reviewer.md` | Work satisfies the original requirement, end to end | work | core |
| `agents/spec-alignment-reviewer.md` | Work faithfully implements the spec; no drift or scope creep | work | core |
| `agents/doc-reviewer.md` | Docs current after the change; edits concise / not bloated | work | core |
| `agents/code-quality-reviewer.md` | Readability, naming, duplication, dead code, needless complexity | work | optional |
| `agents/test-reviewer.md` | Tests meaningful & assert the spec; coverage of new/changed code | work | optional |
| `agents/performance-reviewer.md` | Complexity, N+1, allocation, resource leaks, hotspots | work | optional |
| `agents/security-reviewer.md` | Authz, input validation, secrets, injection, supply chain | both | optional |

The new work-phase core lenses form a **requirement → spec → work** chain:
`requirement-satisfaction` (built the right thing), `spec-alignment` (built per the
spec), `correctness` (built bug-free); `doc-reviewer` keeps docs current and concise.

The **floor** that always runs is the phase's `core` lenses — spec phase:
spec-fitness + architecture; work phase: correctness + architecture +
requirement-satisfaction + spec-alignment + doc-reviewer — so every review is
non-empty for any deliverable. `optional` lenses are **conditional**: they run only
when the spec/diff matches their `applies_to`, auditably skipped otherwise. The
`code-quality`/`test`/`performance` pack matches code files; `security` matches auth,
input-handling, network, file/DB I/O, dependency, or crypto signals.

Each reviewer's frontmatter is **self-describing** (`lens`/`phase`/`tier`/
`applies_to`), so a future selection stage discovers and routes the roster with no
code change; new lenses (domain packs) join the same way — a new file under `agents/`.
The roster is **not yet wired** into the commands' S1/S5 loops; that selection stage
is the next step (both the spec- and work-phase floors now exist, so it can wire S1
and S5 together).

## Configuration

The plugin keeps its own config in its data dir — never Claude's managed
`settings.json`. Edit `${CLAUDE_PLUGIN_DATA}/config.json`
(`~/.claude/plugins/data/<plugin-id>/config.json`):

```json
{ "ralphLoop": { "enabled": false, "maxIterations": { "spec-phase": 3, "implementation-phase": 3 } } }
```

- **`ralphLoop.enabled`** — when `true`, the S1/S5 review-convergence loops are
  driven by the optional `ralph-loop` plugin (per-phase completion markers
  `AUTOPILOT: SPEC READY` / `AUTOPILOT: WORK READY`, cap 3). Default `false` uses the
  built-in native loop. `ralph-loop` is required only when enabled.
- **`ralphLoop.maxIterations.spec-phase` / `.implementation-phase`** — per-phase
  round cap for the S1 spec-review / S5 work-review loop (default 3 each).

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
```

Per-build development docs live in `dev-docs/<date>-<slug>-{spec,progress}.md`,
kept locally (gitignored) as the build's audit trail — this is our development
workflow, not something the command imposes on its users.
