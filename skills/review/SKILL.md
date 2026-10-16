---
name: review
description: "Use to review a document (a spec, PRD, design or plan) against its author's own words with independent reviewer agents, fixing it yourself until every reviewer passes or the round cap. Works without a git repo, with this plugin's reviewers or a folder of your own. Pass doc=<path> requirement=<text or path>."
argument-hint: "doc=<path> requirement=<text|path> [lenses=<dir>] [repo=<path>] [log=<path>] [cap=<n>]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, Task, Workflow, ToolSearch
---

# Autopilot: review

Paths are relative to this skill's directory. Tool names in parentheses are Claude Code
forms. On another host, use the session's exposed equivalent.

Review one document until its panel all-PASSes or the cap is hit. You fix the document;
only the reviewers' verdicts decide.

**First read [`../../references/review-round.md`](../../references/review-round.md) in full.**
Every round here is a spec-phase round, so its (work) steps never apply.

## Input

From the arguments, or from the skill that sends you here:

- `doc`: the document's path. Required.
- `requirement`: the author's own words, verbatim: text, or the file holding them.
  Required. A rewrite or summary of them is not the requirement. A document these words
  name by path or link goes with them.
- `lenses`: a folder of reviewer files, each with this plugin's reviewer frontmatter
  (`phase: spec` or `both`, and a `tier`) and its contract
  ([`../../agents/reviewer-contract.md`](../../agents/reviewer-contract.md));
  `python3 <abs path of ../../scripts/lint-roster.py> --agents-dir <lenses>` checks them.
  Default: this plugin's `../../agents/`.
- `repo`: the checkout the document describes, read-only.
- `log`: the review log. Default: `<doc>.review.md`.
- `cap`: total rounds, `r1` included. Default: 3.

A missing `doc` or `requirement`: return `stopped`, with the reason. When `log` holds
rounds for this `doc` after its last `review-result`, continue from them; otherwise start
at `r1`, below any earlier entries.

## Review

1. **Panel.** Run
   `python3 <abs path of ../../scripts/select-panel.py> --phase spec --spec-file <doc>`,
   adding `--agents-dir <lenses>` when given. The panel is every `core` lens, plus the
   `optional` lenses you judge relevant. An empty panel: return `stopped`, reason
   `empty panel`.
2. **Rounds.** Run them per review-round.md, logging to `log`:
   - doc fields: `spec_doc=<doc>`; with `repo`, the prompt's `worktree=` is `repo` and
     `base_ref=` its HEAD;
   - freeze line: `review panel: core=[…] +optional=[…] transport=Workflow`;
   - re-review set: the full panel, on the whole document.
3. **Fix** the document between rounds per review-round.md (The fix), changing only what
   a blocker needs. A blocker only the author can settle is not yours to guess: return
   `needs-author`, with it in `questions`, worded so the author can answer without
   reading code. Settle any other genuine fork with the council
   ([`../council/SKILL.md`](../council/SKILL.md)).

## Result

End every path with one fenced `review-result` block, also appended to `log`:

```review-result
{ "status": "passed", "doc": "<path>", "rounds": 2, "log": "<path>", "blockers": [], "questions": [], "reason": "" }
```

| `status` | When |
| --- | --- |
| `passed` | every lens passed |
| `capped` | the cap hit with a lens failing; `blockers` holds the open blocking items in full |
| `needs-author` | an open blocker needs the author's choice; `questions` holds it |
| `stopped` | a missing input or an empty panel; `reason` says which |

The review ends here; the caller decides what open blockers and questions mean.
