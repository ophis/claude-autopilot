---
name: build
description: "Use to build a new work product from a requirement, end to end: work on the current feature branch or a new isolated worktree, write and review a spec, write a task list, implement, and review-loop to a single review-ready branch, plus a draft PR when the repo has CI or you ask for one (never merges). Pass the requirement text, or a path to an existing spec file."
argument-hint: "<requirements|spec-file-path>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, Task, Workflow, ToolSearch, EnterWorktree, ExitWorktree, TodoWrite
---

# Autopilot: build

Paths are relative to this skill's directory.

Drive one requirement through S1–S7 to a single review-ready branch, autonomously. You
implement the work; independent reviewer subagents judge it.

**On start, before anything else (a resume included), read [`../../references/autopilot-common.md`](../../references/autopilot-common.md) in full.**
This file adds build's input, spec doc, steps and review settings.

## Input

`input` (common: Terms) takes one of three forms:

- **Requirement** (default): free text. Run the full pipeline.
- **Spec file**: the path of an existing spec file. Skip S2 and S3, and record
  `spec_file=<abs path>` in RESUME. The spec must be self-contained: enough to plan,
  implement and verify with no further clarification.
- **Empty**: stop.

The **spec doc** is the given spec file, or S2's output at the resolver's `spec_doc`
(common: Worktree (S1)).

## Pipeline

### S1. Worktree

Per common: Worktree (S1).

### S2. Spec

Skipped in spec-file mode. Read the affected code, then write the spec doc following
[spec.md](spec.md), including its check.

### S3. Spec review

Skipped in spec-file mode. Run the review loop over the spec with the S3 settings below.
Fix the spec doc yourself. A root contradiction is safety stop 4.

### S4. Task list

Write the task list per common: Task list (S4). Its header also holds the spec path.

### S5. Produce

Per common: Produce (S5). Non-code work follows the same steps.

### S6. Work review

Run the review loop over the work with the S6 settings below. Fix per common: S6 fixes.

### S7. Finish

Per common: Finish (S7). Then emit the result block.

## Review settings

|  | S3 spec review | S6 work review |
| --- | --- | --- |
| Panel source | `python3 scripts/select-panel.py --phase spec --spec-file <spec doc>` | `python3 scripts/select-panel.py --phase work --worktree <worktree> --base <base_ref>` |
| Cap | 3 rounds | 3 rounds |
| Re-review set | the full panel, on the whole spec | the lenses that failed, plus every core lens |
| Prompt doc fields | `spec_doc=…, plan_doc=…` | `spec_doc=…, plan_doc=…` |
| Advance to | S4 | S7 |
| Freeze line | `S3 panel: core=[…] +optional=[…] transport=Workflow` | `S6 panel: core=[…] +optional=[…] verification=<local\|ci> transport=Workflow` |

- The selector returns a `selected` list of `{agent, subagent_type, tier, matched}`.
- The panel is every `core` agent, plus the `optional` agents you judge relevant; drop a
  marginal optional one only with a logged `decision(panel)` line naming it and why.
- Change a cap only when the requirement says so, and only for this run.
