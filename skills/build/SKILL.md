---
name: build
description: "Use to build a new work product from a requirement, end to end: create an isolated worktree, write and review a spec, write a task list, implement, and review-loop to a single review-ready branch (never merges). Pass the requirement text, or a path to an existing spec file."
argument-hint: "<requirements|spec-file-path>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, Task, Workflow, Skill, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite, ScheduleWakeup
---

# Autopilot: build

Paths are relative to this skill's directory.

Drive one requirement through S1–S8 to a single review-ready branch, autonomously. You
implement the work; independent reviewer subagents judge it.

**On start, before anything else (a resume included), read [`../../references/autopilot-common.md`](../../references/autopilot-common.md) in full.**
It holds the rules build shares with light-build: disciplines, hosts, state and resume,
progress log, council, worktree, task list, produce, review round, S6 fixes, squash and
finish, safety stops, and the result block. This file adds build's input, state, steps and review settings.

## Input

`input` (common: Terms) takes one of three forms:

- **Requirement** (default): free text. Run the full pipeline.
- **Spec file**: the path of an existing spec file. Skip S2 and S3, and record
  `spec_file=<abs path>` in RESUME. The spec must be self-contained: enough to plan,
  implement and verify with no further clarification.
- **Empty**: stop.

## State

The run persists two docs so it survives compaction:

- **Spec doc**: S2's output, or the given spec file.
- **Plan doc**: the RESUME block, the progress section, Notes, and the task list as the
  last section.

```
RESUME: phase=<S[1-8]> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> spec_file=<path>
```

The progress section holds the progress log and the full verify command. From S6, the
run note holds the S6 state; log S6 lines there when the plan doc is tracked.

In S3, keep each round's full BLOCKING items in the progress section until the next round's
verdicts are logged.
On safety stop 4, at any phase, record the handoff in the plan doc.

## Pipeline

### S1. Worktree

Create or reuse the worktree (common: Worktree (S1)). Then create the plan doc and record
`worktree`, `branch` and `base_ref` (HEAD) in RESUME.

### S2. Spec

Skipped in spec-file mode. Read the affected code, then write the spec doc following
[spec.md](spec.md), including its check. Settle a genuine fork with the council.

### S3. Spec review

Skipped in spec-file mode. Run the review loop over the spec with the S3 settings below.
Fix the spec doc yourself. A root contradiction is safety stop 4.

### S4. Task list

Write the task list per common: Task list (S4). Its header also holds the spec path. Put
the full verify command in the progress section.

### S5. Produce

Per common: Produce (S5). Non-code work follows the same steps.

### S6. Work review

Run the review loop over the work with the S6 settings below. Fix per common: S6 fixes.

### S7. Squash

Per common: Squash and finish (S7, S8).

### S8. Finish

Per common: Squash and finish (S7, S8). Then emit the result block.

## Review settings

|  | S3 spec review | S6 work review |
| --- | --- | --- |
| Panel source | `python3 scripts/select-panel.py --phase spec --spec-file <spec doc>` | `python3 scripts/select-panel.py --phase work --worktree <worktree> --base <base_ref>` |
| Cap | 3 rounds | 3 rounds |
| Re-review set | the full panel, on the whole spec | the lenses that failed, plus every core lens and any verifier |
| Prompt doc fields | `spec_doc=…, plan_doc=…` | `spec_doc=…, plan_doc=…` |
| Advance to | S4 | S7 |
| Freeze line | `S3 panel: core=[…] +optional=[…] transport=Workflow` | `S6 panel: core=[…] +optional=[…] transport=Workflow` |

- The selector returns a `selected` list of `{agent, subagent_type, tier, matched}`.
- The panel is every `core` agent, plus the `optional` agents you judge relevant; you may
  drop a marginal optional one. In S6, apply the verifier rule.
- Change a cap only when the requirement says so, and only for this run.
