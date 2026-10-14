---
name: light-build
description: "Low-ceremony autonomous build: work on the current feature branch or a new isolated worktree, write a task list, implement each task itself, and run a capped correctness + requirement-fidelity + doc + verification review to a single review-ready branch, or a draft PR when asked (never merges). No spec doc or spec review, and no other plugin needed. Use for simple tasks, or when you want autonomy and expert-council decisions without build's spec rigor. Pass the requirement text."
argument-hint: "<requirements>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, Task, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite
---

# Autopilot: light-build

Paths are relative to this skill's directory.

Drive one requirement through S1 → S4 → S5 → S6 → S7 to a single review-ready branch,
autonomously. Step numbers match build's; light-build skips build's spec (S2) and spec
review (S3). You implement the work; independent reviewer subagents judge it.

- **The requirement is the spec.**
- **No scope gate.** Run whatever you are given; choosing the surface is the user's call.
- **Self-contained.** Name or invoke no external plugin skill, and run no dependency
  preflight.

**On start, before anything else (a resume included), read [`../../references/autopilot-common.md`](../../references/autopilot-common.md) in full.**
It holds the rules light-build shares with build: disciplines, hosts, state and resume,
progress log, council, worktree, task list, produce, review round, S6 fixes, finish,
safety stops, and the result block. This file adds light-build's input, state, steps, review settings
and forks.

## Input

`input` (common: Terms) is a free-text requirement. If it is empty, stop with a handoff asking for
requirements.

## State

The plan doc is created at S4. Until then, hold `worktree`, `branch` and `base_ref` in
context. In order, the plan doc holds the `Rules:` line, the requirement, the full verify command, the
RESUME block, the progress section, Notes, and the task list as the last section.

```
RESUME: phase=<S[14-7]> worktree=<path> branch=<name> base_ref=<sha> review_round=<n>
```

Task `done` marks and decisions go in the progress section; hold a decision made before
S4 in context and log it at S4. The S6 panel, verdicts and evidence go in the run note.

## Pipeline

### S1. Worktree

Create or reuse the worktree (common: Worktree (S1)). Hold `worktree`, `branch` and
`base_ref` (HEAD) in context.

### S4. Task list

Write the task list per common: Task list (S4). S4 always creates the plan doc. A small
change is one task. When the change adds or reshapes state, the header also names the
data shape: the types or records and the structure that holds them, kept plain when it is
clear and local. Put the full verify command above RESUME.

### S5. Produce

Per common: Produce (S5). A delegated producer is dispatched with `Task` and also gets the
requirement.

### S6. Work review

Run the review loop over the work with the settings below. Fix per common: S6 fixes. Settle
a genuine fork during a fix with the council.

### S7. Finish

Per common: Finish (S7). Then emit the result block.

## Review settings (S6)

- **Panel**: pin `autopilot:correctness-reviewer`, `autopilot:requirement-fidelity-reviewer`,
  `autopilot:doc-reviewer` and `autopilot:verification-reviewer`. Add no optional lens.
- **Freeze line**: `S6 panel: pinned=[correctness,requirement-fidelity,doc,verification] verification=<local|ci> transport=Workflow`.
- **Cap**: 2 rounds, `r1` plus one fix and re-review.
- **Re-review set**: the lenses that failed, plus the verifier every round, including
  after a PASS, and correctness after a verifier FAIL. Other lenses carry their PASS.
- **Prompt doc fields**: `plan_doc=…`.
- **Advance to**: S7.

## Forks

A genuine fork you hit while implementing or fixing goes straight to the council. A
delegated producer's `FORK:` return follows common: Produce (S5).

A trivial or low-stakes ambiguity is not a fork. Pick the obvious default (a producer does
the same); S6 catches a wrong guess.
