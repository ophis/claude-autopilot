#!/usr/bin/env python3
"""Tests for the Claude Autopilot helper scripts (stdlib unittest, no deps).

Run:  python3 tests/test_scripts.py [-v]
  or: python3 -m unittest discover -s tests

The scripts are exercised as CLIs via subprocess (they have hyphenated names,
so they aren't importable as modules, and the CLI is the real contract anyway).
Fixtures are synthetic agent files + a throwaway git repo, so the tests don't
depend on the live roster.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
SELECT_PANEL = os.path.join(SCRIPTS, "select-panel.py")
CONFIG = os.path.join(SCRIPTS, "autopilot-config.py")
LINT_ROSTER = os.path.join(SCRIPTS, "lint-roster.py")
REVIEW_ROUND = os.path.join(SCRIPTS, "review-round.js")
REVIEW_LOOP = os.path.join(SCRIPTS, "review-loop.js")
SKILLS = os.path.join(REPO, "skills")

AGENT_TEMPLATE = """\
---
name: {name}
description: synthetic test agent
tools: Read, Grep, Glob, Bash
model: sonnet
phase: {phase}
tier: {tier}
applies_to: {applies_to}
---
body of {name}
"""


def write_agent(dirpath, name, phase, tier, applies_to):
    with open(os.path.join(dirpath, name + ".md"), "w", encoding="utf-8") as fh:
        fh.write(
            AGENT_TEMPLATE.format(
                name=name, phase=phase, tier=tier, applies_to=json.dumps(applies_to)
            )
        )


def write_raw(dirpath, filename, text):
    with open(os.path.join(dirpath, filename), "w", encoding="utf-8") as fh:
        fh.write(text)


def run_select(*args):
    return subprocess.run(
        [sys.executable, SELECT_PANEL, *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _write_nested(repo, rel, content):
    """Write a file under `repo`, creating parent dirs for nested paths."""
    if os.path.dirname(rel):
        os.makedirs(os.path.join(repo, os.path.dirname(rel)), exist_ok=True)
    write_raw(repo, rel, content)


def _git_repo(base_files=()):
    """Temp git repo with a base commit (`BASE` plus optional `base_files`, each
    a (relpath, content) pair). Returns (repo_dir, git_fn, base_sha)."""
    d = tempfile.mkdtemp()
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

    def git(*a):
        subprocess.run(["git", "-C", d, *a], check=True, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    git("init", "-q")
    write_raw(d, "BASE", "base\n")
    for rel, content in base_files:
        _write_nested(d, rel, content)
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"],
                          stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    return d, git, base


def make_git_repo(changed_files):
    """Temp git repo; `changed_files` added in HEAD (status A). select-panel
    --phase work --base <base_sha> then sees exactly `changed_files` in
    `base...HEAD`. Returns (repo_dir, base_sha)."""
    d, git, base = _git_repo()
    for rel in changed_files:
        _write_nested(d, rel, "x\n")
    if changed_files:
        git("add", "-A")
        git("commit", "-q", "-m", "change")
    return d, base


def make_git_repo_modify():
    """Temp git repo whose `base...HEAD` diff is modify-only (status M) — no
    A/D/R/C topology change, i.e. `@structural`'s negative case. Returns
    (repo_dir, base_sha)."""
    d, git, base = _git_repo(base_files=[("src/app.py", "v1\n")])
    _write_nested(d, "src/app.py", "v2\n")           # edit in place -> status M
    git("add", "-A")
    git("commit", "-q", "-m", "modify")
    return d, base


class SelectPanelTests(unittest.TestCase):
    def setUp(self):
        self.agents = tempfile.mkdtemp()
        a = self.agents
        write_agent(a, "core-spec", "spec", "core", ["**"])
        write_agent(a, "core-both", "both", "core", ["**"])
        write_agent(a, "core-work", "work", "core", ["**"])
        write_agent(a, "opt-code", "work", "optional", ["*.py", "*.js"])
        write_agent(a, "opt-kw", "both", "optional", ["auth", "token"])
        write_agent(a, "no-tier", "work", "", ["**"])          # unknown tier -> skipped
        # Map tier (core in spec, @structural-gated optional in work).
        write_agent(a, "arch", "both",
                    '{"spec": "core", "work": "optional"}', ["@structural"])
        write_raw(a, "contract.md",                            # no phase -> skipped
                  "---\nname: contract\ndescription: template\n---\nbody\n")

    def names(self, proc):
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [e["agent"] for e in json.loads(proc.stdout)["selected"]]

    def test_spec_phase_core_only_without_specfile(self):
        names = self.names(run_select("--phase", "spec", "--agents-dir", self.agents))
        # arch's map tier resolves to core in spec; optionals/work-only/no-tier excluded.
        self.assertEqual(names, ["arch", "core-both", "core-spec"])

    def test_spec_phase_keyword_selects_optional(self):
        spec = os.path.join(self.agents, "..", "spec.txt")
        write_raw(os.path.dirname(spec), os.path.basename(spec),
                  "this design needs auth and login flows\n")
        proc = run_select("--phase", "spec", "--agents-dir", self.agents,
                          "--spec-file", spec)
        sel = {e["agent"]: e for e in json.loads(proc.stdout)["selected"]}
        self.assertIn("opt-kw", sel)
        self.assertIn("auth", sel["opt-kw"]["matched"])
        self.assertEqual(sel["opt-kw"]["tier"], "optional")

    def test_work_phase_glob_match(self):
        repo, base = make_git_repo(["src/app.py"])
        names = self.names(run_select("--phase", "work", "--agents-dir", self.agents,
                                      "--worktree", repo, "--base", base))
        self.assertIn("opt-code", names)                  # *.py glob
        self.assertIn("core-both", names)
        self.assertIn("core-work", names)
        self.assertNotIn("opt-kw", names)                 # no auth/token in path
        self.assertNotIn("core-spec", names)              # spec-only phase

    def test_work_phase_keyword_in_path(self):
        repo, base = make_git_repo(["src/auth/login.py"])
        sel = {e["agent"]: e for e in
               json.loads(run_select("--phase", "work", "--agents-dir", self.agents,
                                     "--worktree", repo, "--base", base).stdout)["selected"]}
        self.assertIn("opt-code", sel)                    # *.py glob
        self.assertIn("opt-kw", sel)                      # 'auth' substring in path
        self.assertIn("auth", sel["opt-kw"]["matched"])

    def test_work_phase_empty_diff_core_only(self):
        repo, base = make_git_repo([])                    # base == HEAD, empty diff
        names = self.names(run_select("--phase", "work", "--agents-dir", self.agents,
                                      "--worktree", repo, "--base", base))
        self.assertEqual(names, ["core-both", "core-work"])

    def test_output_shape_and_subagent_type(self):
        entries = json.loads(
            run_select("--phase", "spec", "--agents-dir", self.agents).stdout)["selected"]
        for e in entries:
            self.assertEqual(set(e), {"agent", "subagent_type", "tier", "matched"})
            self.assertEqual(e["subagent_type"], "autopilot:" + e["agent"])
            self.assertEqual(e["matched"], "core")        # all spec selections are core here

    def test_core_sorted_before_optional(self):
        repo, base = make_git_repo(["src/auth/login.py"])
        tiers = [e["tier"] for e in
                 json.loads(run_select("--phase", "work", "--agents-dir", self.agents,
                                       "--worktree", repo, "--base", base).stdout)["selected"]]
        self.assertEqual(tiers, sorted(tiers, key=lambda t: 0 if t == "core" else 1))

    def test_per_phase_tier_core_in_spec(self):
        sel = {e["agent"]: e for e in json.loads(
            run_select("--phase", "spec", "--agents-dir", self.agents).stdout
        )["selected"]}
        self.assertIn("arch", sel)
        self.assertEqual(sel["arch"]["tier"], "core")     # map resolved to scalar
        self.assertEqual(sel["arch"]["matched"], "core")

    def test_work_structural_resolves_map_and_scalar_tiers(self):
        # File-added (status A) is a structural diff, so @structural-gated arch selects.
        repo, base = make_git_repo(["src/new.py"])
        sel = {e["agent"]: e for e in json.loads(
            run_select("--phase", "work", "--agents-dir", self.agents,
                       "--worktree", repo, "--base", base).stdout
        )["selected"]}
        self.assertEqual(sel["arch"]["tier"], "optional")   # map resolved to scalar
        self.assertIn("@structural", sel["arch"]["matched"])
        self.assertEqual(sel["core-work"]["tier"], "core")  # scalar back-compat
        self.assertEqual(sel["core-work"]["matched"], "core")

    def test_modify_only_diff_omits_arch(self):
        # Modify-only (status M) is not structural, so @structural-gated arch is omitted.
        repo, base = make_git_repo_modify()
        names = self.names(run_select("--phase", "work", "--agents-dir", self.agents,
                                      "--worktree", repo, "--base", base))
        self.assertNotIn("arch", names)

    def test_work_phase_requires_worktree_and_base(self):
        proc = run_select("--phase", "work", "--agents-dir", self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("worktree", proc.stderr.lower())

    def test_bad_agents_dir_errors(self):
        proc = run_select("--phase", "spec", "--agents-dir",
                          os.path.join(self.agents, "does-not-exist"))
        self.assertNotEqual(proc.returncode, 0)


class AutopilotConfigTests(unittest.TestCase):
    DEFAULTS = {"ralphLoop": {"maxIterations": {"spec-phase": 3, "implementation-phase": 3}}}

    def run_config(self, data_dir):
        return subprocess.run(
            [sys.executable, CONFIG],
            env=dict(os.environ, CLAUDE_PLUGIN_DATA=data_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def test_fresh_writes_defaults(self):
        d = tempfile.mkdtemp()
        proc = self.run_config(d)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), self.DEFAULTS)
        cfg = os.path.join(d, "config.json")
        self.assertTrue(os.path.exists(cfg))
        with open(cfg) as fh:
            self.assertEqual(json.load(fh), self.DEFAULTS)

    def test_partial_override_is_deep_merged(self):
        d = tempfile.mkdtemp()
        # Deprecated "enabled" toggle (gone from DEFAULTS) still merges through.
        write_raw(d, "config.json", json.dumps({"ralphLoop": {"enabled": True}}))
        eff = json.loads(self.run_config(d).stdout)
        self.assertTrue(eff["ralphLoop"]["enabled"])
        self.assertEqual(eff["ralphLoop"]["maxIterations"],
                         {"spec-phase": 3, "implementation-phase": 3})

    def test_nested_partial_override(self):
        d = tempfile.mkdtemp()
        write_raw(d, "config.json",
                  json.dumps({"ralphLoop": {"maxIterations": {"spec-phase": 5}}}))
        eff = json.loads(self.run_config(d).stdout)
        self.assertEqual(eff["ralphLoop"]["maxIterations"]["spec-phase"], 5)
        self.assertEqual(eff["ralphLoop"]["maxIterations"]["implementation-phase"], 3)
        self.assertNotIn("enabled", eff["ralphLoop"])

    def test_unparseable_config_falls_back_without_overwrite(self):
        d = tempfile.mkdtemp()
        write_raw(d, "config.json", "{ not valid json")
        proc = self.run_config(d)
        self.assertEqual(json.loads(proc.stdout), self.DEFAULTS)
        with open(os.path.join(d, "config.json")) as fh:
            self.assertEqual(fh.read(), "{ not valid json")            # bad file left intact

    def test_fallback_dir_when_env_unset(self):
        # Env unset must fall back to the real {id} dir, not the old ".../autopilot" path.
        home = tempfile.mkdtemp()
        env = dict(os.environ, HOME=home)
        env.pop("CLAUDE_PLUGIN_DATA", None)
        proc = subprocess.run(
            [sys.executable, CONFIG],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), self.DEFAULTS)
        good = os.path.join(home, ".claude", "plugins", "data",
                            "autopilot-claude-autopilot", "config.json")
        bad = os.path.join(home, ".claude", "plugins", "data",
                           "autopilot", "config.json")
        self.assertTrue(os.path.exists(good), "fallback config.json not at {id} dir")
        with open(good) as fh:
            self.assertEqual(json.load(fh), self.DEFAULTS)
        self.assertFalse(os.path.exists(bad), "config.json written to old wrong path")


# A valid reviewer body: inlines the four contract markers and ends with the
# verdict-grammar section as the last "## " heading.
GOOD_BODY = """\
# {name}

## Contract

- **Read-only.** Tools allowlist is Read, Grep, Glob, Bash.
- **Inputs by reference.** The orchestrator passes you the worktree path.
- **Cite evidence.** Anchor every finding to file:line.
- **Load no superpowers skills.**

## Verdict grammar (strict, machine-parseable)

When a `StructuredOutput` tool is offered, the verdict is that call.

VERDICT: PASS
BLOCKING: none
NON-BLOCKING: none
"""

# A complete, valid reviewer frontmatter + body. Callers override individual
# lines (or the body) to construct each failure-mode fixture.
GOOD_REVIEWER = """\
---
name: {name}
description: >-
  synthetic test reviewer body that folds over a couple of lines so the block
  scalar path is exercised.
tools: Read, Grep, Glob, Bash
model: opus
effort: high
maxTurns: 30
lens: synthetic lens for testing
phase: work
tier: core
applies_to: ["**"]
---
""" + GOOD_BODY

# A valid selector-inert contract template (no phase/tier/lens/applies_to).
GOOD_TEMPLATE = """\
---
name: reviewer-contract
description: >-
  Authoring-time template; selector-inert by design.
---

# Reviewer contract (authoring template)

Body with Read-only, Inputs by reference, Cite evidence, and
Load no superpowers skills — but no selector metadata.
"""


def run_lint(agents_dir):
    return subprocess.run(
        [sys.executable, LINT_ROSTER, "--agents-dir", agents_dir],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


class LintRosterTests(unittest.TestCase):
    def setUp(self):
        self.agents = tempfile.mkdtemp()

    def _reviewer(self, name="r1", reviewer=None, body=None):
        """Write a reviewer file; `reviewer`/`body` override the defaults."""
        if reviewer is None:
            reviewer = GOOD_REVIEWER.format(name=name)
        if body is not None:
            # Keep frontmatter, swap everything after the closing fence.
            head = reviewer.split("\n---\n", 1)[0] + "\n---\n"
            reviewer = head + body
        write_raw(self.agents, name + ".md", reviewer)

    def _template(self, name="reviewer-contract", text=None):
        write_raw(self.agents, name + ".md", text if text is not None else GOOD_TEMPLATE)

    def test_all_valid_roster_passes(self):
        self._reviewer("r1")
        self._template()
        proc = run_lint(self.agents)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OK r1", proc.stdout)
        self.assertIn("OK reviewer-contract", proc.stdout)

    def test_no_agents_found_fails(self):
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no agent files", (proc.stdout + proc.stderr).lower())

    def test_missing_max_turns(self):
        reviewer = GOOD_REVIEWER.format(name="r1").replace("maxTurns: 30\n", "")
        self._reviewer("r1", reviewer=reviewer)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("maxTurns", proc.stdout)

    def test_tools_includes_write(self):
        reviewer = GOOD_REVIEWER.format(name="r1").replace(
            "tools: Read, Grep, Glob, Bash", "tools: Read, Grep, Glob, Bash, Write"
        )
        self._reviewer("r1", reviewer=reviewer)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("tools", proc.stdout)
        self.assertIn("Write", proc.stdout)

    def test_bad_tier(self):
        reviewer = GOOD_REVIEWER.format(name="r1").replace(
            "tier: core", "tier: cor"
        )
        self._reviewer("r1", reviewer=reviewer)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("tier", proc.stdout)

    def test_bad_phase(self):
        reviewer = GOOD_REVIEWER.format(name="r1").replace(
            "phase: work", "phase: bogus"
        )
        self._reviewer("r1", reviewer=reviewer)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("phase", proc.stdout)

    def test_tools_missing_member(self):
        reviewer = GOOD_REVIEWER.format(name="r1").replace(
            "tools: Read, Grep, Glob, Bash", "tools: Read, Grep, Glob"
        )
        self._reviewer("r1", reviewer=reviewer)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("tools", proc.stdout)
        self.assertIn("Bash", proc.stdout)

    def test_broken_reviewer_has_tier_lens_no_phase(self):
        # tier+lens but no phase => classified as template, fails selector-inert
        # (this is how a dropped phase surfaces).
        reviewer = GOOD_REVIEWER.format(name="r1").replace("phase: work\n", "")
        self._reviewer("r1", reviewer=reviewer)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("selector-inert", proc.stdout)

    def test_missing_verdict_block(self):
        body = """\
# r1

## Contract

- **Read-only.** Inputs by reference. Cite evidence.
- **Load no superpowers skills.**
"""
        self._reviewer("r1", body=body)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("verdict", proc.stdout.lower())

    def test_verdict_block_not_last(self):
        body = """\
# r1

## Contract

- **Read-only.** Inputs by reference. Cite evidence.
- **Load no superpowers skills.**

## Verdict grammar

When a `StructuredOutput` tool is offered, the verdict is that call.

VERDICT: PASS
BLOCKING: none
NON-BLOCKING: none

## Appendix

Some trailing section that wrongly follows the verdict block.
"""
        self._reviewer("r1", body=body)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("last", proc.stdout.lower())

    def test_missing_load_no_superpowers_marker(self):
        body = """\
# r1

## Contract

- **Read-only.** Inputs by reference. Cite evidence.

## Verdict grammar

VERDICT: PASS
BLOCKING: none
NON-BLOCKING: none
"""
        self._reviewer("r1", body=body)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Load no superpowers skills", proc.stdout)

    def test_name_mismatch(self):
        # name in frontmatter is "r1" but the file is "other.md".
        self._reviewer("other", reviewer=GOOD_REVIEWER.format(name="r1"))
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("name", proc.stdout)

    def test_map_form_tier_accepted(self):
        reviewer = GOOD_REVIEWER.format(name="r1").replace(
            "tier: core", 'tier: {"spec": "core", "work": "optional"}'
        )
        self._reviewer("r1", reviewer=reviewer)
        proc = run_lint(self.agents)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OK r1", proc.stdout)

    def test_map_form_tier_bad_value_rejected(self):
        reviewer = GOOD_REVIEWER.format(name="r1").replace(
            "tier: core", 'tier: {"spec": "core", "work": "bogus"}'
        )
        self._reviewer("r1", reviewer=reviewer)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("tier", proc.stdout)

    def test_map_form_tier_bad_phase_rejected(self):
        reviewer = GOOD_REVIEWER.format(name="r1").replace(
            "tier: core", 'tier: {"bogus": "core", "work": "optional"}'
        )
        self._reviewer("r1", reviewer=reviewer)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("tier", proc.stdout)

    def test_template_carrying_phase_tier_fails(self):
        text = """\
---
name: reviewer-contract
description: >-
  Template that wrongly carries selector metadata.
phase: work
tier: core
---

Body with Read-only, Inputs by reference, Cite evidence,
Load no superpowers skills.
"""
        # Declares phase => classified as a reviewer, fails on missing keys.
        self._template(text=text)
        self._reviewer("r1")  # a passing file so the run isn't the empty-roster case
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("FAIL reviewer-contract", proc.stdout)

    def test_template_carrying_tier_lens_no_phase_fails(self):
        # Selector metadata without phase => template branch, fails selector-inert.
        text = """\
---
name: reviewer-contract
description: >-
  Template that wrongly carries tier/lens.
tier: core
lens: should not be here
---

Body.
"""
        self._template(text=text)
        self._reviewer("r1")
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("selector-inert", proc.stdout)
        self.assertIn("tier", proc.stdout)


class ReviewRoundScriptTests(unittest.TestCase):
    """Static contract + syntax gate for scripts/review-round.js (spec D1/D4).

    The script runs only inside the Dynamic Workflows runtime, so there is no
    behavioral harness here; these tests pin the *contract surface* the commands
    and the orchestrator depend on, and the no-ambient-authority posture.
    """

    @classmethod
    def setUpClass(cls):
        with open(REVIEW_ROUND, encoding="utf-8") as fh:
            cls.text = fh.read()

    def test_contract_markers_present(self):
        """The markers the commands/orchestrator rely on all appear verbatim."""
        for marker in (
            "export const meta",
            "autopilot-review-round",
            "agentType",
            "schema",
            "no verdict returned (skip/terminal error)",
            "synthetic",
            "verdicts",
            "return {",
            # Schema field names + verdict values: renaming any silently breaks judging.
            "required: ['VERDICT', 'BLOCKING', 'NON_BLOCKING'],",
            "enum: ['PASS', 'FAIL']",
        ):
            self.assertIn(marker, self.text, marker)

    def test_no_ambient_authority(self):
        """No imports/FS/env/network/clock — args is the script's only input."""
        for banned in (
            "require(",
            "import ",
            "import(",  # dynamic import — "import " alone would miss it
            "process.",
            "fs.",
            "fetch(",
            "Date.now",
            "Math.random",
        ):
            self.assertNotIn(banned, self.text, banned)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_node_syntax_check(self):
        """node --check accepts the script under the runtime's execution model:
        the Workflows runtime hoists the `export const meta` and runs the body
        inside an async function (so top-level `await` and `return` are legal).
        Emulate that: demote the export, wrap the body, check as ESM (.mjs)."""
        wrapped = "async function _wf() {\n%s\n}\n" % self.text.replace(
            "export const meta", "const meta", 1
        )
        with tempfile.TemporaryDirectory() as td:
            mjs = os.path.join(td, "review-round.mjs")
            with open(mjs, "w", encoding="utf-8") as fh:
                fh.write(wrapped)
            proc = subprocess.run(
                ["node", "--check", mjs],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode())


class SkillLockstepTests(unittest.TestCase):
    """skills/build/SKILL.md and skills/fix/SKILL.md must carry a byte-identical
    workflow-transport block (spec A2). Until now this was enforced only by
    review; prose drift between the two skills now fails here instead.
    """

    @staticmethod
    def _transport_block(skill):
        path = os.path.join(SKILLS, skill, "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        start = next(
            (i for i, l in enumerate(lines) if "Workflow transport (preferred" in l),
            None,
        )
        end = next(
            (i for i, l in enumerate(lines) if "not a separate log line" in l),
            None,
        )
        if start is None or end is None or end < start:
            raise AssertionError("transport block not found in %s" % skill)
        return "\n".join(lines[start : end + 1])

    @staticmethod
    def _progress_log_format_block(skill):
        path = os.path.join(SKILLS, skill, "SKILL.md")
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        start = next(
            (i for i, l in enumerate(lines) if "progress-log-format:start" in l),
            None,
        )
        end = next(
            (i for i, l in enumerate(lines) if "progress-log-format:end" in l),
            None,
        )
        if start is None or end is None or end < start:
            raise AssertionError("progress-log-format block not found in %s" % skill)
        return "\n".join(lines[start : end + 1])

    def test_transport_block_identical(self):
        """The block from 'Workflow transport (preferred' through the
        transport-record sentence is the shared dispatch contract — byte-identical
        or bust."""
        self.assertEqual(
            self._transport_block("build"), self._transport_block("fix")
        )

    def test_progress_log_format_block_identical(self):
        """The progress-log-format block (between the HTML markers) is mirrored
        byte-for-byte across both skills — byte-identical or bust."""
        self.assertEqual(
            self._progress_log_format_block("build"),
            self._progress_log_format_block("fix"),
        )


class ReviewLoopPureTests(unittest.TestCase):
    """Behavioral tests for review-loop.js pure helpers. The PURE block is
    sentinel-delimited and self-contained (no runtime globals), so we slice it
    out, append an export + a tiny assertion driver, and run it under node."""

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_pure_helpers(self):
        with open(REVIEW_LOOP, encoding="utf-8") as fh:
            text = fh.read()
        start = text.index("// ──PURE START")
        end = text.index("// ──PURE END")
        block = text[start:end]
        driver = block + r"""
const assert = (c, m) => { if (!c) { throw new Error(m) } }
assert(normalize({agent:'a'}, null).synthetic === true, 'null->synthetic')
assert(normalize({agent:'a'}, null).VERDICT === 'FAIL', 'null->FAIL')
assert(normalize({agent:'a'}, {VERDICT:'PASS',BLOCKING:[],NON_BLOCKING:[]}).VERDICT === 'PASS', 'pass')
assert(normalize({agent:'a'}, {VERDICT:'PASS',BLOCKING:['x'],NON_BLOCKING:[]}).VERDICT === 'FAIL', 'pass+blocking->FAIL')
assert(normalize({agent:'a'}, {VERDICT:'PASS',BLOCKING:[],NON_BLOCKING:[]}).synthetic === false, 'real not synthetic')
assert(JSON.stringify(dedup(['a','a','b'])) === JSON.stringify(['a','b']), 'dedup')
assert(failedOf([{VERDICT:'PASS'},{VERDICT:'FAIL',agent:'b'}]).length === 1, 'failedOf')
const cf = carryForward([{agent:'a',VERDICT:'FAIL'},{agent:'b',VERDICT:'PASS'}],[{agent:'a',VERDICT:'PASS'}])
assert(cf.find(v=>v.agent==='a').VERDICT === 'PASS', 'cf overrides')
assert(cf.find(v=>v.agent==='b').VERDICT === 'PASS', 'cf keeps prior')
const r = [{VERDICT:'FAIL',BLOCKING:['x']}]
assert(classify([r, r]) === 'oscillation', 'oscillation')
assert(classify([[{VERDICT:'FAIL',BLOCKING:['x']}]]) === 'unfixable', 'single->unfixable')
const mp = memberPrompt({focus:'F'}, {ph:'work',worktree:'/wt',base_ref:'S',spec_doc:null,plan_doc:null,requirement:'R'})
assert(mp.includes('PHASE=work') && mp.includes('/wt') && mp.includes('R') && mp.includes('F'), 'memberPrompt')
assert(subsetFor([{agent:'a'}], [{agent:'a',subagent_type:'x',focus:'y'},{agent:'b',subagent_type:'z',focus:'w'}]).length === 1, 'subsetFor maps to members')
assert(subsetFor([{agent:'a'}], [{agent:'a',subagent_type:'x',focus:'y'}])[0].subagent_type === 'x', 'subsetFor returns members')
console.log('PURE_OK')
"""
        with tempfile.TemporaryDirectory() as td:
            mjs = os.path.join(td, "pure.mjs")
            with open(mjs, "w", encoding="utf-8") as fh:
                fh.write(driver)
            proc = subprocess.run(["node", mjs], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode())
            self.assertIn(b"PURE_OK", proc.stdout)


class ReviewLoopScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(REVIEW_LOOP, encoding="utf-8") as fh:
            cls.text = fh.read()
    def test_contract_markers_present(self):
        for marker in ("export const meta", "autopilot-review-loop", "agentType", "schema",
            "no verdict returned (skip/terminal error)", "synthetic", "converged", "decisions",
            "return {", "required: ['VERDICT', 'BLOCKING', 'NON_BLOCKING'],", "enum: ['PASS', 'FAIL']",
            "// ──PURE START", "// ──PURE END"):
            self.assertIn(marker, self.text, marker)
    def test_no_ambient_authority(self):
        for banned in ("require(", "import ", "import(", "process.", "fs.", "fetch(", "Date.now", "Math.random"):
            self.assertNotIn(banned, self.text, banned)
    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_node_syntax_check(self):
        wrapped = "async function _wf() {\n%s\n}\n" % self.text.replace("export const meta", "const meta", 1)
        with tempfile.TemporaryDirectory() as td:
            mjs = os.path.join(td, "review-loop.mjs")
            with open(mjs, "w", encoding="utf-8") as fh:
                fh.write(wrapped)
            proc = subprocess.run(["node", "--check", mjs], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode())


class SharedFallbackTests(unittest.TestCase):
    def test_review_loop_fallback_present(self):
        path = os.path.join(SKILLS, "_shared", "review-loop.md")
        self.assertTrue(os.path.exists(path), "fallback md missing")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for marker in ("all-PASS", "FAILed", "cap", "oscillation", "unfixable",
                       "requirements-conflict"):
            self.assertIn(marker, text, marker)


class LightBuildCutoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(SKILLS, "light-build", "SKILL.md"), encoding="utf-8") as fh:
            cls.text = fh.read()
    def test_calls_review_loop(self):
        self.assertIn("review-loop.js", self.text)
    def test_has_no_workflow_fallback_pointer(self):
        self.assertIn("_shared/review-loop.md", self.text)
    def test_panel_arg_in_review_loop_call(self):
        # the panel arg now rides the review-loop.js Workflow call (cutover-specific shape)
        self.assertIn("panel:[{agent", self.text)

    def test_no_stale_review_round_dispatch(self):
        # light-build no longer dispatches via review-round.js (it owns no per-round transport now)
        self.assertNotIn("review-round.js", self.text)


class SkillWorktreePinTests(unittest.TestCase):
    """Every orchestrator skill must require worktree-pinned subagent dispatch."""
    def test_all_skills_pin_subagents_to_worktree(self):
        for skill in ("build", "fix", "medium-build", "light-build"):
            with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("Worktree-pinned dispatch", text, skill)
            self.assertIn("never** main/master", text, skill)
            self.assertIn("branch --show-current", text, skill)


if __name__ == "__main__":
    unittest.main()
