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
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
SELECT_PANEL = os.path.join(SCRIPTS, "select-panel.py")
CONFIG = os.path.join(SCRIPTS, "autopilot-config.py")

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


def make_git_repo(changed_files):
    """A temp git repo with an empty base commit, then `changed_files` committed.

    Returns (repo_dir, base_sha). `select-panel --phase work --base <base_sha>`
    will see exactly `changed_files` in `base...HEAD`.
    """
    d = tempfile.mkdtemp()
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

    def git(*a):
        subprocess.run(["git", "-C", d, *a], check=True, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    git("init", "-q")
    write_raw(d, "BASE", "base\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"],
                          stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    for rel in changed_files:
        full = os.path.join(d, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True) if os.path.dirname(rel) else None
        write_raw(d, rel, "x\n")
    if changed_files:
        git("add", "-A")
        git("commit", "-q", "-m", "change")
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
        write_raw(a, "contract.md",                            # no phase -> skipped
                  "---\nname: contract\ndescription: template\n---\nbody\n")

    def names(self, proc):
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return [e["agent"] for e in json.loads(proc.stdout)["selected"]]

    def test_spec_phase_core_only_without_specfile(self):
        names = self.names(run_select("--phase", "spec", "--agents-dir", self.agents))
        # core spec + core both; not work-only, not optionals (no signal), not
        # contract (no phase), not no-tier (unknown tier).
        self.assertEqual(names, ["core-both", "core-spec"])

    def test_spec_phase_keyword_selects_optional(self):
        spec = os.path.join(self.agents, "..", "spec.txt")
        write_raw(os.path.dirname(spec), os.path.basename(spec),
                  "this design needs auth and login flows\n")
        proc = run_select("--phase", "spec", "--agents-dir", self.agents,
                          "--spec-file", spec)
        sel = {e["agent"]: e for e in json.loads(proc.stdout)["selected"]}
        self.assertIn("opt-kw", sel)                      # keyword 'auth' matched
        self.assertIn("auth", sel["opt-kw"]["matched"])
        self.assertEqual(sel["opt-kw"]["tier"], "optional")

    def test_spec_phase_glob_optional_not_matched(self):
        # opt-code is work-only anyway; confirm a glob optional never matches in
        # spec phase even if its phase allowed it: opt-kw has only keywords, so
        # without matching keywords it must be absent.
        names = self.names(run_select("--phase", "spec", "--agents-dir", self.agents))
        self.assertNotIn("opt-kw", names)
        self.assertNotIn("opt-code", names)

    def test_work_phase_glob_match(self):
        repo, base = make_git_repo(["src/app.py"])
        names = self.names(run_select("--phase", "work", "--agents-dir", self.agents,
                                      "--worktree", repo, "--base", base))
        self.assertIn("opt-code", names)                  # *.py matched
        self.assertIn("core-both", names)
        self.assertIn("core-work", names)
        self.assertNotIn("opt-kw", names)                 # no auth/token in path
        self.assertNotIn("core-spec", names)              # spec-only

    def test_work_phase_keyword_in_path(self):
        repo, base = make_git_repo(["src/auth/login.py"])
        sel = {e["agent"]: e for e in
               json.loads(run_select("--phase", "work", "--agents-dir", self.agents,
                                     "--worktree", repo, "--base", base).stdout)["selected"]}
        self.assertIn("opt-code", sel)                    # *.py
        self.assertIn("opt-kw", sel)                      # 'auth' substring in path
        self.assertIn("auth", sel["opt-kw"]["matched"])

    def test_work_phase_empty_diff_core_only(self):
        repo, base = make_git_repo([])                    # base == HEAD, empty diff
        names = self.names(run_select("--phase", "work", "--agents-dir", self.agents,
                                      "--worktree", repo, "--base", base))
        self.assertEqual(names, ["core-both", "core-work"])  # only work-phase core

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
        # every core must precede every optional
        self.assertEqual(tiers, sorted(tiers, key=lambda t: 0 if t == "core" else 1))

    def test_work_phase_requires_worktree_and_base(self):
        proc = run_select("--phase", "work", "--agents-dir", self.agents)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("worktree", proc.stderr.lower())

    def test_bad_agents_dir_errors(self):
        proc = run_select("--phase", "spec", "--agents-dir",
                          os.path.join(self.agents, "does-not-exist"))
        self.assertNotEqual(proc.returncode, 0)


class AutopilotConfigTests(unittest.TestCase):
    DEFAULTS = {"ralphLoop": {"enabled": False,
                              "maxIterations": {"spec-phase": 3, "implementation-phase": 3}}}

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
        self.assertEqual(json.loads(proc.stdout), self.DEFAULTS)        # printed effective
        cfg = os.path.join(d, "config.json")
        self.assertTrue(os.path.exists(cfg))                            # file created
        with open(cfg) as fh:
            self.assertEqual(json.load(fh), self.DEFAULTS)

    def test_partial_override_is_deep_merged(self):
        d = tempfile.mkdtemp()
        write_raw(d, "config.json", json.dumps({"ralphLoop": {"enabled": True}}))
        eff = json.loads(self.run_config(d).stdout)
        self.assertTrue(eff["ralphLoop"]["enabled"])                    # user override wins
        self.assertEqual(eff["ralphLoop"]["maxIterations"],            # defaults preserved
                         {"spec-phase": 3, "implementation-phase": 3})

    def test_nested_partial_override(self):
        d = tempfile.mkdtemp()
        write_raw(d, "config.json",
                  json.dumps({"ralphLoop": {"maxIterations": {"spec-phase": 5}}}))
        eff = json.loads(self.run_config(d).stdout)
        self.assertEqual(eff["ralphLoop"]["maxIterations"]["spec-phase"], 5)
        self.assertEqual(eff["ralphLoop"]["maxIterations"]["implementation-phase"], 3)
        self.assertFalse(eff["ralphLoop"]["enabled"])

    def test_unparseable_config_falls_back_without_overwrite(self):
        d = tempfile.mkdtemp()
        write_raw(d, "config.json", "{ not valid json")
        proc = self.run_config(d)
        self.assertEqual(json.loads(proc.stdout), self.DEFAULTS)        # falls back
        with open(os.path.join(d, "config.json")) as fh:
            self.assertEqual(fh.read(), "{ not valid json")            # left intact

    def test_fallback_dir_when_env_unset(self):
        # When CLAUDE_PLUGIN_DATA is unset, the script must fall back to the real
        # per-plugin {id} dir under HOME, not the old wrong ".../autopilot" path.
        home = tempfile.mkdtemp()
        env = dict(os.environ, HOME=home)
        env.pop("CLAUDE_PLUGIN_DATA", None)
        proc = subprocess.run(
            [sys.executable, CONFIG],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), self.DEFAULTS)        # printed effective
        good = os.path.join(home, ".claude", "plugins", "data",
                            "autopilot-claude-autopilot", "config.json")
        bad = os.path.join(home, ".claude", "plugins", "data",
                           "autopilot", "config.json")
        self.assertTrue(os.path.exists(good), "fallback config.json not at {id} dir")
        with open(good) as fh:
            self.assertEqual(json.load(fh), self.DEFAULTS)
        self.assertFalse(os.path.exists(bad), "config.json written to old wrong path")


if __name__ == "__main__":
    unittest.main()
