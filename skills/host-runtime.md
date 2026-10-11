# Host runtime

Both skills use these mappings for all dispatch, paths, config, and approvals.
Resolve the host from the current session's exposed tools; record it and the review
transport in the run note. Required capability missing → Safety stop 3 after one
retry, with the missing capability and exact next step; never substitute your own
work for a required producer or reviewer.

## Startup and paths

- **Input:** Claude Code substitutes `$ARGUMENTS`; Codex uses the invoking user's
  requirement or explicit caller input. Treat an unexpanded placeholder as absent;
  apply the skill's empty-input rule. In either host, this resolved `input` is the
  single source of intent, including build's existing-spec-file mode.
- **Plugin files:** resolve absolute `skill_dir` from the invoked SKILL.md's location
  and `plugin_root` from its enclosing plugin (`skills/<surface>/../..`). Claude's
  substituted `${CLAUDE_SKILL_DIR}` / `${CLAUDE_PLUGIN_ROOT}` may supply these paths;
  Codex uses the skill catalog's actual path. Read referenced files there and run
  helpers by absolute path; keep this root separate from the target worktree.
- **Repository guidance:** read applicable `AGENTS.md` and `CLAUDE.md` in the target
  repo/worktree and obey the host's instruction precedence. Pass their paths to
  workers, including the verifier's required checks.
- **Config:** build runs `python3 <plugin_root>/scripts/autopilot-config.py --host
  <claude|codex>`; forward Claude's substituted plugin data path with `--data-dir`
  when available. Codex defaults to `${CODEX_HOME:-~/.codex}/plugins/data/autopilot-claude-autopilot`;
  Claude retains its existing plugin data default. An explicitly configured data
  directory overrides either default; quote all resolved paths. light-build keeps
  its pinned cap of 1 and needs no config load. Never change host settings files.
- **Worktree:** follow S1 reuse/base rules. Claude retains
  `.claude/worktrees/<prefix>-<slug>`, branch `<prefix>-<slug>` and `EnterWorktree`; Codex prefers an exposed managed worktree tool when it can honor
  S1's exact base/branch, otherwise use absolute `git worktree` paths. Use the repo's
  worktree convention (fallback `.codex/worktrees` on Codex, gitignored), and its
  branch convention (fallback `codex/<prefix>-<slug>` on Codex). Without a cwd-switch
  tool, pass the absolute working directory to every command and worker.

## Agents and review rounds

| Operation | Claude Code | Codex |
|---|---|---|
| Fresh producer / council member | `Task` | Exposed `spawn_agent` equivalent |
| Continue fixer with a new task | `SendMessage` | `followup_task` or exposed continuation tool that starts an idle agent |
| Collect completed output | Native Task/Workflow completion | Exposed agent wait/result tools; a status notification alone is not a verdict |
| Reviewer | Named `autopilot:<name>` | Generic fresh agent with canonical instructions, below |

Use only exposed APIs and their documented arguments. Codex inherits the host model
by default, unless the user explicitly configures a supported override; Claude
retains each named agent's model, effort and tools. For Claude generic dispatch,
preserve those settings through supported options; unavailable required settings
require registration/reload or a missing-capability stop. For a generic reviewer on either
host, pass `<plugin_root>/agents/<name>.md` as an absolute must-read reference before
any work, plus the skill's run-input prompt. The worker must load the complete file,
including lens, read-only/test scope, isolated verification contract where applicable,
and strict verdict grammar. Map declared tools to available host tools while preserving those boundaries; Claude model names are not
Codex model IDs. A producer or council member uses its task/persona brief.

Request a fresh context for each new agent when supported (e.g. Codex
`fork_turns="none"`), supplying its brief and applicable inherited constraints;
omit model overrides to inherit the host model.

Dispatch independent members up to exposed concurrency capacity, queue the rest, and
collect every member of the frozen round before judging or fixing. Preserve S3/S6
re-review membership and caps. Re-reviewers are fresh; retain the fixer ID for
continuation (unusable ID → fresh fixer with its brief and current blockers).

**Review transport:** use `Workflow({name: "autopilot:autopilot-review-round", args:
{phase, members: [{agent, subagent_type, prompt}]}})` when exposed; output is
`{phase, verdicts: [{agent, VERDICT, BLOCKING, NON_BLOCKING, synthetic}]}` in member
order. Never pass `resumeFromRunId`. Re-dispatch a `synthetic: true` member once through
native dispatch; still no verdict → FAIL. If Workflow is absent or fails, use native
dispatch for the same members/prompts and keep it for that phase. Record the actual
transport (`Workflow`, `Task`, or Codex native tool name), including any fallback.
PASS requires no BLOCKING; missing/unparseable verdict → FAIL. The skill's committed
source, fixed SHA/tree and verification evidence gates still apply on either host.

## Approvals

Use the current host's sandbox and approval rules. Existing user authorization
persists. For a destructive operation requiring approval that is not authorized,
use Safety stop 1; report a host-denied action and its reason. Ordinary writes in
the pinned worktree, verification's temporary checkout, and plugin config follow
the host's normal permission mechanism.
