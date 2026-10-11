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
REVIEW_ROUND = os.path.join(REPO, "workflows", "review-round.js")
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

    def test_live_verification_reviewer_is_mandatory_for_work_only(self):
        repo, base = make_git_repo([])
        work = run_select("--phase", "work", "--worktree", repo,
                          "--base", base)
        self.assertEqual(work.returncode, 0, work.stderr)
        selected = {e["agent"]: e for e in json.loads(work.stdout)["selected"]}
        self.assertEqual(selected["verification-reviewer"], {
            "agent": "verification-reviewer",
            "subagent_type": "autopilot:verification-reviewer",
            "tier": "core",
            "matched": "core",
        })
        spec = run_select("--phase", "spec")
        self.assertEqual(spec.returncode, 0, spec.stderr)
        self.assertNotIn("verification-reviewer",
                         {e["agent"] for e in json.loads(spec.stdout)["selected"]})


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

    def run_host_config(self, home, *args, **environment):
        env = dict(os.environ, HOME=home)
        for name in ("CLAUDE_PLUGIN_DATA", "CODEX_HOME"):
            env.pop(name, None)
        env.update(environment)
        return subprocess.run(
            [sys.executable, CONFIG, *args], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def test_codex_default_is_separate_from_claude_data(self):
        with tempfile.TemporaryDirectory() as home:
            claude_data = os.path.join(home, "claude-data")
            proc = self.run_host_config(home, "--host", "codex",
                                        CLAUDE_PLUGIN_DATA=claude_data)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout), self.DEFAULTS)
            path = os.path.join(home, ".codex", "plugins", "data",
                                "autopilot-claude-autopilot", "config.json")
            self.assertTrue(os.path.exists(path))
            self.assertFalse(os.path.exists(claude_data))

    def test_codex_home_selects_config_and_deep_merges(self):
        with tempfile.TemporaryDirectory() as home:
            codex_home = os.path.join(home, "custom-codex")
            data = os.path.join(codex_home, "plugins", "data",
                                "autopilot-claude-autopilot")
            os.makedirs(data)
            write_raw(data, "config.json", json.dumps(
                {"ralphLoop": {"maxIterations": {"spec-phase": 7}}}))
            proc = self.run_host_config(home, "--host", "codex", CODEX_HOME=codex_home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["ralphLoop"]["maxIterations"],
                             {"spec-phase": 7, "implementation-phase": 3})
            self.assertFalse(os.path.exists(os.path.join(home, ".codex")))

    def test_explicit_data_dir_overrides_both_host_defaults(self):
        for host in ("claude", "codex"):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as home:
                data = os.path.join(home, "explicit data")
                proc = self.run_host_config(
                    home, "--host", host, "--data-dir", data,
                    CODEX_HOME=os.path.join(home, "codex"),
                    CLAUDE_PLUGIN_DATA=os.path.join(home, "claude"))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue(os.path.exists(os.path.join(data, "config.json")))
                self.assertFalse(os.path.exists(os.path.join(home, host)))

    def test_explicit_claude_host_preserves_environment_override(self):
        with tempfile.TemporaryDirectory() as home:
            data = os.path.join(home, "claude-data")
            proc = self.run_host_config(home, "--host", "claude", CLAUDE_PLUGIN_DATA=data)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.exists(os.path.join(data, "config.json")))


# A valid reviewer body: inlines the four contract markers and ends with the
# verdict-grammar section as the last "## " heading.
GOOD_BODY = """\
# {name}

## Contract

- **Read-only.** Tools allowlist is Read, Grep, Glob, Bash.
- **Inputs by reference.** The orchestrator passes you the worktree path.
- **Cite evidence.** Anchor every finding to file:line.
- **Test scope:** Leave full suites, builds, and verification to the verification
  reviewer; if a finding hinges on one test, read and run only that test and
  report its command and result in your verdict.

## Verdict grammar (strict)

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

Body with Read-only, Inputs by reference, and Cite evidence — but no selector metadata.
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

    def test_ordinary_reviewer_must_forbid_full_suite(self):
        self._reviewer("r1", body=GOOD_BODY.format(name="r1").replace(
            "- **Test scope:** Leave full suites, builds, and verification to the verification\n"
            "  reviewer; if a finding hinges on one test, read and run only that test and\n"
            "  report its command and result in your verdict.\n", ""))
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Test scope", proc.stdout)

    def test_verification_reviewer_uses_distinct_execution_contract(self):
        with open(os.path.join(REPO, "agents", "verification-reviewer.md"),
                  encoding="utf-8") as fh:
            verifier = fh.read()
        self._reviewer("verification-reviewer", reviewer=verifier)
        proc = run_lint(self.agents)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for marker in ("Frozen worktree", "Command evidence",
                       "VERIFICATION_UNAVAILABLE:"):
            self._reviewer("verification-reviewer", reviewer=verifier.replace(marker, ""))
            proc = run_lint(self.agents)
            self.assertNotEqual(proc.returncode, 0, marker + "\n" + proc.stdout)
            self.assertIn(marker, proc.stdout)

    def test_verification_reviewer_runs_in_frozen_worktree_without_clone(self):
        with open(os.path.join(REPO, "agents", "verification-reviewer.md"),
                  encoding="utf-8") as fh:
            verifier = fh.read()
        self.assertNotIn("clone", verifier.lower())
        for banned in ("mktemp", 'rm -rf "$('):
            self.assertNotIn(banned, verifier)
        for required in ("rev-parse HEAD", "status --porcelain"):
            self.assertIn(required, verifier)

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

## Verdict grammar

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

    def test_missing_contract_marker(self):
        body = """\
# r1

## Contract

- **Read-only.** Inputs by reference.

## Verdict grammar

VERDICT: PASS
BLOCKING: none
NON-BLOCKING: none
"""
        self._reviewer("r1", body=body)
        proc = run_lint(self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Cite evidence", proc.stdout)

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

Body with Read-only, Inputs by reference, Cite evidence.
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


class SkillWorktreePinTests(unittest.TestCase):
    """Every orchestrator skill must require worktree-pinned subagent dispatch."""
    def test_all_skills_pin_subagents_to_worktree(self):
        for skill in ("build", "light-build"):
            with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("Worktree-pinned dispatch", text, skill)
            self.assertIn("never** main/master", text, skill)
            self.assertIn("branch --show-current", text, skill)

    def test_s1_reuses_prior_run_worktree_before_creating(self):
        for skill in ("build", "light-build"):
            with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                text = fh.read()
            s1 = text[text.index("- **S1 — worktree.**"):text.index("- **S", text.index("- **S1 — worktree.**") + 1)]
            resolve = s1.index("host-specific `<branch>` before lookup or creation")
            reuse = s1.index("resolved `<branch>` exists from a prior run, reuse it with its commits")
            self.assertLess(resolve, reuse, skill)
            self.assertLess(reuse, s1.index("Else create worktree"), skill)
            self.assertIn("same resolved branch for worktree reuse and resume", s1, skill)
            self.assertIn("Follow repo worktree/branch conventions", s1, skill)
            self.assertNotIn("`<prefix>-<slug>` branch", s1, skill)
            self.assertIn("git worktree add <path> <branch>", s1, skill)
            self.assertIn("collision with another requirement's", s1, skill)

    def test_build_s5_fresh_producer_per_task_without_review(self):
        with open(os.path.join(SKILLS, "build", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        s5 = " ".join(text[text.index("- **S5 — produce.**"):text.index("- **S6 — work review.**")].split())
        self.assertIn("one fresh producer subagent on the task list header and its `### Task N` brief", s5)
        self.assertIn("only the checks its brief names that cover its changed files", s5)
        self.assertIn("never the full verify command or full suite", s5)
        self.assertIn("log the task `done`", s5)
        self.assertNotIn("review", s5)
        for doc in ("skills/build/SKILL.md", "README.md", "CLAUDE.md"):
            with open(os.path.join(REPO, doc), encoding="utf-8") as fh:
                self.assertNotIn("subagent-driven", fh.read(), doc)

    def test_light_build_s5_fresh_producer_per_task_without_review(self):
        with open(os.path.join(SKILLS, "light-build", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        s5 = " ".join(text[text.index("- **S5 — produce.**"):text.index("- **S6 — work review.**")].split())
        self.assertIn("one fresh producer subagent", s5)
        self.assertIn("task list header", s5)
        self.assertIn("`### Task N` brief", s5)
        self.assertIn("only the checks its brief names that cover its changed files", s5)
        self.assertIn("never the full verify command or full suite", s5)
        self.assertIn("log the task `done`", s5)
        self.assertNotIn("review", s5)

    def test_light_build_s4_task_list_in_state_file(self):
        with open(os.path.join(SKILLS, "light-build", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        s4 = " ".join(text[text.index("- **S4 — task list.**"):text.index("- **S5 — produce.**")].split())
        self.assertIn("Global Constraints", s4)
        self.assertIn("### Task N", s4)
        self.assertIn("always materializes the state file", s4)
        self.assertIn("the checks it runs (only those its change affects, never a full suite", s4)

    def test_light_build_pipeline_legend_includes_s4(self):
        with open(os.path.join(SKILLS, "light-build", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("S1 → S4 → S5 → S6 → S7 → S8", text)

    def test_build_has_no_dependency_preflight_and_plans_itself(self):
        with open(os.path.join(SKILLS, "build", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        preflight = text[text.index("## Preflight"):text.index("## Operating disciplines")]
        self.assertEqual(preflight.count("\n- "), 1)
        self.assertIn("autopilot-config.py", preflight)
        self.assertIn("invoke no planning skill", " ".join(text.split()))

    def test_build_s2_follows_its_spec_guide(self):
        with open(os.path.join(SKILLS, "build", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        s2 = text[text.index("- **S2 — spec."):text.index("- **S3 — spec review.")]
        self.assertIn("[spec.md](spec.md)", s2)
        tracked = subprocess.run(["git", "-C", REPO, "ls-files", "skills/build/spec.md"],
                                 capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(tracked, ["skills/build/spec.md"])

    def test_plugin_never_mentions_superpowers(self):
        files = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True,
                               text=True, check=True).stdout.split()
        for f in files:
            if f.startswith("tests/"):
                continue
            with open(os.path.join(REPO, f), encoding="utf-8", errors="ignore") as fh:
                self.assertNotIn("superpowers", fh.read().lower(), f)

    def test_s6_work_review_includes_verification_without_standalone_verify(self):
        for skill in ("build", "light-build"):
            with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                text = fh.read()
            flat = " ".join(text.split())
            self.assertNotIn("- **S6 — verify.**", text, skill)
            self.assertIn("- **S6 — work review.**", text, skill)
            self.assertIn("- **S7 — squash.**", text, skill)
            self.assertIn("- **S8 — finish.**", text, skill)
            self.assertNotIn("- **S9 —", text, skill)
            self.assertIn("autopilot:verification-reviewer", text, skill)
            self.assertIn("reviewed_sha=<HEAD>", text, skill)
            self.assertIn("HEAD still equals", flat, skill)
            self.assertIn("HEAD^{tree}", text, skill)
            self.assertIn("<reviewed_sha>^{tree}", text, skill)
            self.assertIn("Wait for every verdict", text, skill)
            self.assertIn("raw BLOCKING items before adding item IDs", flat, skill)
            self.assertIn("VERIFICATION_UNAVAILABLE:", text, skill)
            self.assertIn("only checks covering the files it changes", flat, skill)
            self.assertIn("never the full verify command or full suite", flat, skill)
            self.assertIn("verify command outside the task-list header", flat, skill)
            self.assertIn("exit code", text, skill)
        with open(os.path.join(SKILLS, "build", "SKILL.md"), encoding="utf-8") as fh:
            build = fh.read()
        with open(os.path.join(SKILLS, "light-build", "SKILL.md"), encoding="utf-8") as fh:
            light = fh.read()
        self.assertIn("every core lens", build)
        self.assertIn("every round, including after a PASS", light)
        self.assertIn("four cores, no optionals", light)
        self.assertIn("progress section", build)
        self.assertIn("above RESUME", light)
        self.assertIn("legacy S1–S9", build + light)
        with open(os.path.join(REPO, "README.md"), encoding="utf-8") as fh:
            self.assertNotIn("S6 — Verify", fh.read())

    def test_s6_dispatch_uses_clean_committed_source_and_fixed_revision(self):
        for skill in ("build", "light-build"):
            with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                text = " ".join(fh.read().split())
            marker = ("Dispatch the whole round together" if skill == "build"
                      else "Dispatch** each round's members together")
            dispatch = text[text.index(marker):text.index("Wait for every verdict")]
            self.assertIn("git -C <worktree> status --porcelain", dispatch, skill)
            self.assertIn("clean committed source worktree", dispatch, skill)
            self.assertIn("ordinary reviewers read source head", dispatch.lower(), skill)
            self.assertIn("verification reviewer runs full checks in the frozen source worktree",
                          dispatch, skill)
            self.assertNotIn("clone", dispatch.lower(), skill)

    def test_s6_fix_commits_and_rechecks_source_before_rereview(self):
        for skill in ("build", "light-build"):
            with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                text = " ".join(fh.read().split())
            s6 = text[text.index("S6 — work review."):text.index("S7 — squash.")]
            self.assertIn("fix producer must commit", s6, skill)
            self.assertIn("before re-review under the dispatch rules above", s6, skill)
            dispatch = text[text.index("- **Dispatch"):text.index("- **Wait for every verdict")]
            self.assertIn("git -C <worktree> status --porcelain", dispatch, skill)
            self.assertIn("git -C <worktree> rev-parse HEAD", dispatch, skill)

    def test_reviewer_template_exempts_verification_contract(self):
        with open(os.path.join(REPO, "agents", "reviewer-contract.md"), encoding="utf-8") as fh:
            template = fh.read()
        with open(os.path.join(REPO, "CLAUDE.md"), encoding="utf-8") as fh:
            guide = fh.read()
        self.assertIn("ordinary reviewers", template)
        self.assertIn("verification-reviewer.md", template)
        self.assertIn("dedicated execution contract", template)
        self.assertIn("ordinary reviewers", guide)
        self.assertIn("verification-reviewer.md", guide)
        self.assertIn("dedicated execution contract", guide)

    def test_readme_limits_shared_contract_to_ordinary_reviewers(self):
        with open(os.path.join(REPO, "README.md"), encoding="utf-8") as fh:
            readme = fh.read()
        self.assertNotIn("inlined into each reviewer", readme)
        self.assertEqual(readme.count("inlined into ordinary reviewers"), 2)
        self.assertIn("dedicated execution contract", readme)

    def test_resume_phase_regexes_cover_only_valid_stages(self):
        with open(os.path.join(SKILLS, "build", "SKILL.md"), encoding="utf-8") as fh:
            build = fh.read()
        with open(os.path.join(SKILLS, "light-build", "SKILL.md"), encoding="utf-8") as fh:
            light = fh.read()
        self.assertIn("RESUME: phase=<S[1-8]>", build)
        self.assertIn("RESUME: phase=<S[14-8]>", light)

class ReviewRoundScriptTests(unittest.TestCase):
    """Static contract + syntax gate for workflows/review-round.js.

    The script runs only inside the Workflows runtime, so there is no behavioral
    harness here; these tests pin its args/return contract and verdict schema
    (README "Plugin workflow"), and the no-ambient-authority posture.
    """

    @classmethod
    def setUpClass(cls):
        with open(REVIEW_ROUND, encoding="utf-8") as fh:
            cls.text = fh.read()

    def test_contract_markers_present(self):
        """The contract markers all appear verbatim."""
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


if __name__ == "__main__":
    unittest.main()
