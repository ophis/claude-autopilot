# Claude Autopilot

A Claude Code **plugin** that packages a high-ceremony, autonomous pipeline for
shipping complex work products (code, but also docs, designs, data, plans). It
replaces a copy-pasted "do all this, summon a team to review, never ask me" prompt
with one explicit command.

> Status: **v0.1** — the `/autopilot:build` command is implemented as the first,
> **agent-free** slice. The full design (named review-agent roster, `fix` command,
> selection stage) lives in [`SPEC.md`](./SPEC.md) and is future work.

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

(`planning-with-files` is optional.) `/autopilot:build` also **preflight-checks**
for superpowers and, if it's missing, stops and hands you these instructions rather
than failing midway.

### 2. Install Claude Autopilot

This repo is its own single-repo marketplace, so add it and install:

```
/plugin marketplace add ophis/claude-autopilot
/plugin install autopilot@claude-autopilot
```

`ophis/claude-autopilot` is the GitHub `owner/repo` shorthand (a full git URL or a
local path works too). You can also browse and install via the interactive
`/plugin` menu (Marketplaces → add → install).

**Updating:** `plugin.json` has no `version`, so Claude Code tracks this plugin by
commit SHA — every push is a new version. Refresh with:

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

### Smoke test (the v0.1 eval)

In a throwaway git repo:

```
/autopilot:build add a function add(a,b) with a passing unit test
```

Expect: a new `autopilot/<slug>` worktree+branch; the spec and work review loops
each reach `VERDICT: PASS`; the test actually runs and passes; the run ends at a
**single squashed commit with no merge** and a final report.

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
committed with the branch as the build's audit trail (this is our development
workflow, not something the command imposes on its users).

See [`SPEC.md`](./SPEC.md) for the full design and rationale.
