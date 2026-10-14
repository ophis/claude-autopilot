#!/usr/bin/env python3
"""Tests for the Claude Autopilot helper scripts (stdlib unittest, no deps).

Run:  python3 tests/test_scripts.py [-v]
  or: python3 -m unittest discover -s tests

The scripts are exercised as CLIs via subprocess (they have hyphenated names,
so they aren't importable as modules, and the CLI is the real contract anyway).
Fixtures are synthetic agent files + a throwaway git repo, so the tests don't
depend on the live roster.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
SELECT_PANEL = os.path.join(REPO, "skills", "build", "scripts", "select-panel.py")
CHECK_SPEC = os.path.join(REPO, "skills", "build", "scripts", "check-spec.py")
CI_VERDICT = os.path.join(REPO, "skills", "build", "scripts", "ci-verdict.py")
RESOLVE_BRANCH = os.path.join(REPO, "skills", "build", "scripts", "resolve-branch.py")
PR_SCRIPT = os.path.join(REPO, "skills", "build", "scripts", "pr.py")
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

    def test_bundled_selector_finds_live_roster_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as cwd:
            proc = subprocess.run([sys.executable, SELECT_PANEL, "--phase", "spec"],
                                  cwd=cwd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        selected = {entry["agent"]: entry for entry in json.loads(proc.stdout)["selected"]}
        self.assertIn("spec-fitness-reviewer", selected)
        self.assertEqual(selected["spec-fitness-reviewer"]["tier"], "core")
        self.assertNotIn("verification-reviewer", selected)

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

    def test_unknown_base_fails_instead_of_a_core_only_panel(self):
        repo, _ = make_git_repo(["src/auth.py"])
        proc = run_select("--phase", "work", "--worktree", repo, "--base", "deadbeef",
                          "--agents-dir", self.agents)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(proc.stdout, "")
        self.assertIn("git diff against deadbeef failed", proc.stderr)

    def test_bad_agents_dir_errors(self):
        proc = run_select("--phase", "spec", "--agents-dir",
                          os.path.join(self.agents, "does-not-exist"))
        self.assertNotEqual(proc.returncode, 0)

    def test_live_verification_reviewer_is_core_for_work_only(self):
        repo, base = make_git_repo(["README.md"])
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

    def test_verification_reviewer_must_be_work_only_core(self):
        with open(os.path.join(REPO, "agents", "verification-reviewer.md"),
                  encoding="utf-8") as fh:
            verifier = fh.read()
        for old, new in (("tier: core", "tier: optional"),
                         ('applies_to: ["**"]', 'applies_to: ["*.py"]')):
            self._reviewer("verification-reviewer", reviewer=verifier.replace(old, new))
            proc = run_lint(self.agents)
            self.assertNotEqual(proc.returncode, 0, new)
            self.assertIn("work-only core", proc.stdout)

    def test_verification_reviewer_has_ci_mode(self):
        with open(os.path.join(REPO, "agents", "verification-reviewer.md"),
                  encoding="utf-8") as fh:
            verifier = flat(fh.read())
        for token in ("**CI mode.**", "`verification=ci`", "<ci_script>",
                      "Exit 4 means checks are still running", "first NON-BLOCKING item",
                      "return its verdict and run nothing else, with the re-review lines below on a re-review",
                      "On exit 5 (the PR conflicts with its base) or 6 (CI missed its deadline), emit `VERDICT: FAIL` with the script's line as the only BLOCKING item, prefixed `VERIFICATION_UNAVAILABLE: ` on exit 6, and run nothing else",
                      "--sha <reviewed_sha> --plan-doc <plan_doc>",
                      "Run each check unpiped", "`set -o pipefail`",
                      "tests run and failed", "including a test command that ran 0 tests, goes in BLOCKING"):
            self.assertIn(token, verifier)

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
        ).replace("phase: work", "phase: both")
        self._reviewer("r1", reviewer=reviewer)
        proc = run_lint(self.agents)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OK r1", proc.stdout)

    def test_lint_rejects_what_the_selector_would_drop(self):
        repo, base = make_git_repo(["src/auth.py"])
        for old, new in (('applies_to: ["**"]', "applies_to: [auth, *.py]"),
                         ('applies_to: ["**"]', 'applies_to: ["*.py",]'),
                         ("phase: work\ntier: core", 'phase: work\ntier: {"both": "core"}'),
                         ("phase: work\ntier: core", 'phase: both\ntier: {"spec": "core"}'),
                         ("phase: work\ntier: core", 'phase: work\ntier: {"spec": "core", "work": "core"}')):
            with self.subTest(new=new):
                reviewer = GOOD_REVIEWER.format(name="r1").replace(old, new)
                self.assertNotEqual(reviewer, GOOD_REVIEWER.format(name="r1"))
                self._reviewer("r1", reviewer=reviewer)
                work = run_select("--phase", "work", "--worktree", repo, "--base", base,
                                  "--agents-dir", self.agents)
                spec = run_select("--phase", "spec", "--agents-dir", self.agents)
                picked = [e["agent"] for out in (work, spec)
                          for e in json.loads(out.stdout)["selected"]]
                proc = run_lint(self.agents)
                self.assertNotEqual(proc.returncode, 0, new + " passed lint; selector picked %s" % picked)

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


def skill_text(skill):
    """SKILL.md plus every plugin reference file it points to."""
    with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
        text = fh.read()
    parts = [text]
    for ref in sorted(set(re.findall(r"\.\./\.\./(references/[\w.-]+\.md)", text))):
        with open(os.path.join(REPO, ref), encoding="utf-8") as fh:
            parts.append(fh.read())
    return "\n".join(parts)


def flat(text):
    return " ".join(text.split())


def step(text, n):
    """The body of pipeline step S<n>, up to the next step or heading."""
    m = re.search(rf"(?m)^(?:#+ |- \*\*)S{n}\b", text)
    rest = text[m.end():]
    nxt = re.search(r"(?m)^(?:#+ |- \*\*S\d)", rest)
    return rest[:nxt.start()] if nxt else rest


class SkillContractTests(unittest.TestCase):
    """Both skills keep their pipeline shape and the exact tokens a run must use."""
    SKILL_STEPS = {"build": [1, 2, 3, 4, 5, 6, 7], "light-build": [1, 4, 5, 6, 7]}

    def test_pipeline_steps_in_order(self):
        for skill, steps in self.SKILL_STEPS.items():
            with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                text = fh.read()
            found = [int(n) for n in re.findall(r"(?m)^(?:#+ |- \*\*)S(\d)\b", text)]
            self.assertEqual(sorted(set(found)), steps, skill)
            self.assertEqual(found, sorted(found), skill)

    def test_skills_point_to_the_shared_reference(self):
        pointer = "../../references/autopilot-common.md"
        for skill in self.SKILL_STEPS:
            with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                self.assertIn(pointer, fh.read(), skill)
        with open(os.path.join(REPO, "references", "autopilot-common.md"), encoding="utf-8") as fh:
            common = fh.read()
        self.assertFalse(common.startswith("---"), "shared reference must not look like a skill")

    def test_common_pointers_name_real_headings(self):
        with open(os.path.join(REPO, "references", "autopilot-common.md"), encoding="utf-8") as fh:
            headings = set(re.findall(r"(?m)^## (.+)$", fh.read()))
        for skill in self.SKILL_STEPS:
            with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                text = flat(fh.read())
            rests = [text[m.end():m.end() + 60] for m in re.finditer(r"common: ", text)]
            self.assertTrue(rests, skill)
            for rest in rests:
                with self.subTest(skill=skill, pointer=rest[:30]):
                    self.assertTrue(any(rest.startswith(h) and rest[len(h):len(h) + 1] in ").," for h in headings), rest)

    def test_exact_tokens_survive(self):
        tokens = (
            "EnterWorktree({path: <worktree>})", "`autopilot:<name>`", "Agent tool",
            'Workflow({name: "autopilot:autopilot-review-round"', "resumeFromRunId", "synthetic",
            "force-push", "write outside the worktree", "history rewrite beyond this branch",
            "rm/reset of uncommitted work", "Auto Mode",
            "branch --show-current", "never a default branch",
            "git worktree add <worktree> <branch>", "git worktree add <worktree> -b <branch> HEAD",
            "resolve-branch.py", "--input-file <file>", "never through the", "input_sha=<sha>",
            "write `.autopilot/.gitignore` (`*`)", "with `resume_line` as its", "--body-file <file>",
            "RESUME as the second line", "Single-quote every value taken from the requirement",
            "git -C <worktree> status --porcelain", "git -C <worktree> rev-parse HEAD",
            "reviewed_sha", "One task is one commit", "fix(r<N>): <item IDs>",
            "git merge --squash",
            "git -C <worktree> diff <pre-fix HEAD>..HEAD",
            "VERIFICATION_UNAVAILABLE:", "autopilot:verification-reviewer",
            "exit code", "<lens>#<n>",
            "autopilot-result", "converged", "capped-without-pass", "stopped",
            "oscillation", "unfixable", "requirements-conflict",
            "root-contradiction", "phase-failure", "destructive-op",
            "spawn_agent", "ci-verdict.py", "## Publish",
            
            '"pr": ""', "no planning skill", "### Task N",
            "git -C <worktree> log --oneline <base_ref>..HEAD", "Notes", ".autopilot/",
            "Fix causes, not symptoms", "<slug>-plan.md",
            "or at `phase=done`, is an earlier run's", "set RESUME `phase=done` before the result block",
            "every lens passing means the phase converged: advance",
            "If HEAD moved, take safety stop 3",
            
            
            "never a local full-suite run",
            
            
            
            
            
            "`CONFLICT:` means merge the base and re-run the round (Publish)",
            "`git -C <worktree> merge origin/<base>` (never rebase)",
            "Set RESUME `base_ref` to `git -C <worktree> merge-base HEAD origin/<base>`",
            "re-run the round like an interrupted one", "**Targeted checks.**", "safety stop 3 naming the conflicting files",
            "**Real exit codes.**", "`set -o pipefail`", "`CI checks: [<names>]`",
            "`CI checks: []` if none runs them",
            
            "tests first, run red (each new test fails because the behavior is missing, not because the test is broken)",
            "red=<tests failing before the code, or none>", "tests=12, failures=0",
            "3 rounds",
            
            "the run stays on it", "uncommitted changes there are the user's",
            "matched by RESUME `input_sha`",
            "never dirties the worktree", "**Review items.**",

        )
        for skill in self.SKILL_STEPS:
            text = flat(skill_text(skill))
            for token in tokens:
                with self.subTest(skill=skill, token=token):
                    self.assertIn(token, text)

    def test_common_bundled_paths_exist(self):
        refs = os.path.join(REPO, "references")
        with open(os.path.join(refs, "autopilot-common.md"), encoding="utf-8") as fh:
            paths = set(re.findall(r"\.\./[\w./-]+\.(?:py|md)", fh.read()))
        self.assertIn("../skills/build/scripts/ci-verdict.py", paths)
        for rel in paths:
            self.assertTrue(os.path.exists(os.path.join(refs, rel)), rel)

    def test_publish_steps_go_through_pr_py(self):
        text = flat(skill_text("light-build"))
        for token in ("`python3 <abs path of ../skills/build/scripts/pr.py>`",
                      "RESUME. Then run `pr.py start` (Publish).",
                      "run `pr.py push --task` (Publish)", "Run `pr.py push` (Publish).",
                      "`pr.py spec --plan-doc <plan_doc> --spec-doc <spec doc>` at S4",
                      "`pr.py finish --plan-doc <plan_doc> --report-file <file>`",
                      "Run `pr.py status --plan-doc <plan_doc>`",
                      "`verification=ci` when `pr.py` reports `publish` other than `none`",
                      "exit 3 is safety stop 3 with that reason"):
            self.assertIn(token, text)
        self.assertNotIn("gh pr ", text)
        self.assertLess(text.index("Then run `pr.py start`"), text.index("## Task list (S4)"))

    def test_plan_doc_names_never_collide(self):
        text = flat(skill_text("build"))
        self.assertIn("created at S1 where the resolver names it", text)

    def test_resume_line_has_one_source(self):
        common = flat(skill_text("build")).split("# Autopilot common rules", 1)[1]
        self.assertIn("RESUME: phase=<step|done> worktree=<path> branch=<name> base_ref=<sha> review_round=<n> input_sha=<sha>", common)
        for skill in self.SKILL_STEPS:
            with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                self.assertNotIn("RESUME: phase=", fh.read(), skill)

    def test_s5_has_no_per_task_review(self):
        with open(os.path.join(REPO, "references", "autopilot-common.md"), encoding="utf-8") as fh:
            common = fh.read()
        produce = common[common.index("## Produce (S5)"):]
        produce = produce[:produce.index("\n## ", 1)]
        self.assertIn("### Task N", produce)
        self.assertNotIn("review", produce.lower())
        for skill in self.SKILL_STEPS:
            with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                s5 = step(fh.read(), 5)
            self.assertIn("Produce (S5)", s5, skill)
            self.assertNotIn("review", s5.lower(), skill)
        for doc in ("skills/build/SKILL.md", "README.md", "CLAUDE.md"):
            with open(os.path.join(REPO, doc), encoding="utf-8") as fh:
                self.assertNotIn("subagent-driven", fh.read(), doc)

    def test_orchestrator_authors_and_reviewers_judge(self):
        with open(os.path.join(REPO, "references", "autopilot-common.md"), encoding="utf-8") as fh:
            common = fh.read()
        def section(title):
            body = common[common.index(title):]
            return body[:body.index("\n## ", 1)]
        produce = section("## Produce (S5)")
        self.assertIn("Implement it yourself", produce)
        self.assertNotIn("never edit the work product", common)
        self.assertIn("FORK:", produce)
        fixes = section("## S6 fixes")
        self.assertIn("yourself", fixes)
        self.assertNotIn("SendMessage", fixes)
        self.assertNotIn("thin orchestrator", common.lower())
        self.assertIn("### Re-hydrate after compaction", common)
        self.assertIn("Never act as your own reviewer or verifier", common)

    def test_build_specifics(self):
        with open(os.path.join(SKILLS, "build", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("[spec.md](spec.md)", step(text, 2))
        tracked = subprocess.run(["git", "-C", REPO, "ls-files", "skills/build/spec.md"],
                                 capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(tracked, ["skills/build/spec.md"])
        self.assertIn("select-panel.py", text)
        self.assertIn("spec_file=", text)
        self.assertIn("every core lens", flat(text))
        self.assertIn("only with a logged `decision(panel)` line", flat(text))
        self.assertNotIn("## Preflight", text)
        self.assertNotIn("Load config", text)

    def test_light_build_specifics(self):
        with open(os.path.join(SKILLS, "light-build", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("data shape", text)
        self.assertIn("correctness after a verifier FAIL", flat(text))
        for lens in ("correctness", "requirement-fidelity", "doc"):
            self.assertIn(f"autopilot:{lens}-reviewer", text, lens)
        self.assertNotIn("select-panel", text)

    def test_retired_shapes_stay_gone(self):
        for skill in self.SKILL_STEPS:
            text = skill_text(skill)
            self.assertFalse("S6 — verify" in text, skill)
            self.assertFalse("S8" in text, skill)
            self.assertNotIn("squash to one commit", text.lower(), skill)
            self.assertFalse("clone" in text.lower(), skill)
        with open(os.path.join(REPO, "README.md"), encoding="utf-8") as fh:
            self.assertNotIn("S6 — Verify", fh.read())

    def test_plugin_never_mentions_superpowers(self):
        files = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True,
                               text=True, check=True).stdout.split()
        for f in files:
            if f.startswith("tests/"):
                continue
            with open(os.path.join(REPO, f), encoding="utf-8", errors="ignore") as fh:
                self.assertNotIn("superpowers", fh.read().lower(), f)

    def test_ordinary_reviewers_copy_the_template_verbatim(self):
        def sections(path):
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            parts = re.split(r"(?m)^(?=## )", body)
            heads = [p.splitlines()[0] for p in parts if p.startswith("## ")]
            self.assertEqual(len(heads), len(set(heads)), path)
            return {p.splitlines()[0]: p.rstrip() for p in parts if p.startswith("## ")}
        template = sections(os.path.join(REPO, "agents", "reviewer-contract.md"))
        shared = ("## Contract", "## Verdict grammar (strict)")
        for path in sorted(glob.glob(os.path.join(REPO, "agents", "*-reviewer.md"))):
            name = os.path.basename(path)
            if name == "verification-reviewer.md":
                continue
            mine = sections(path)
            for title in shared:
                with self.subTest(reviewer=name, section=title):
                    self.assertEqual(mine.get(title), template[title])

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

GOOD_SPEC = """# Spec: TASK-1 add wordcount
Requirement: quoted below; it overrides any other input.

## Goal
Count words.

## Scope
In: wordcount. Out: none.

## Acceptance criteria
`AC1`: `wordcount("a b")` is 2.
`AC2`: `wordcount("")` is 0.
`AC3`: punctuation-only tokens don't count.

## Design
### textkit/core.py
`wordcount(text) -> int`.

## Verification
| AC | Test or check |
| --- | --- |
| AC1–AC2 | tests/test_core.py::test_wordcount |
| AC3 | tests/test_core.py::test_punctuation |

## Decisions
`D1`: whitespace means `str.split()`.
"""


class CheckSpecTests(unittest.TestCase):
    """check-spec.py enforces spec.md's header, required sections and AC coverage."""

    def run_check(self, text, encoding="utf-8"):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding=encoding) as fh:
            fh.write(text)
        self.addCleanup(os.unlink, fh.name)
        return subprocess.run([sys.executable, CHECK_SPEC, fh.name], capture_output=True,
                              text=True, timeout=30)

    def assertProblems(self, proc, *lines):
        self.assertEqual(proc.returncode, 1, proc.stdout)
        for line in lines:
            self.assertIn(line, proc.stdout.splitlines())

    def test_good_spec_passes(self):
        proc = self.run_check(GOOD_SPEC)
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "OK"))

    def test_every_range_form_covers_its_criteria(self):
        for span in ("AC1–AC3", "AC1-AC3", "AC1 — AC3", "`AC1`–`AC3`", "AC1..AC3", "AC1 to AC3",
                     "AC1 through AC3", "AC1-3"):
            with self.subTest(span=span):
                spec = GOOD_SPEC.replace("| AC1–AC2 |", f"| {span} |").replace(
                    "| AC3 | tests/test_core.py::test_punctuation |\n", "")
                proc = self.run_check(spec)
                self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "OK"))

    def test_dash_after_an_id_in_criteria_is_not_a_range(self):
        spec = GOOD_SPEC.replace("`AC2`: `wordcount(\"\")` is 0.", "`AC2` — 0 for empty input; AC3 - 404 never.")
        proc = self.run_check(spec)
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "OK"))

    def test_bullet_list_ids_are_not_a_range(self):
        spec = GOOD_SPEC.replace("| AC1–AC2 | tests/test_core.py::test_wordcount |\n", "- AC1\n").replace(
            "| AC3 | tests/test_core.py::test_punctuation |\n", "- AC3\n")
        self.assertProblems(self.run_check(spec), "AC2: no Verification row")

    def test_reversed_range_covers_its_criteria(self):
        spec = GOOD_SPEC.replace("| AC1–AC2 |", "| AC3–AC1 |").replace("| AC3 | tests/test_core.py::test_punctuation |\n", "")
        proc = self.run_check(spec)
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "OK"))

    def test_huge_range_is_capped(self):
        proc = self.run_check(GOOD_SPEC.replace("| AC3 |", "| AC3–AC1000000000 |"))
        self.assertProblems(proc, "AC1000000000: cited in Verification but not defined")
        self.assertLess(len(proc.stdout.splitlines()), 5)

    def test_uncovered_criterion_fails(self):
        proc = self.run_check(GOOD_SPEC.replace("| AC3 | tests/test_core.py::test_punctuation |\n", ""))
        self.assertProblems(proc, "AC3: no Verification row")

    def test_undefined_criterion_in_verification_fails(self):
        proc = self.run_check(GOOD_SPEC.replace("| AC3 |", "| AC3, AC4 |"))
        self.assertProblems(proc, "AC4: cited in Verification but not defined")

    def test_headings_inside_fences_are_ignored(self):
        spec = GOOD_SPEC.replace("| --- | --- |\n", "| --- | --- |\n```\n## note\n```\n").replace(
            "### textkit/core.py\n", "### textkit/core.py\n```\n## Verification\n| AC9 | x |\n```\n")
        proc = self.run_check(spec)
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "OK"))

    def test_bad_header_fails(self):
        proc = self.run_check(GOOD_SPEC.replace("# Spec: TASK-1", "# TASK-1"))
        self.assertProblems(proc, "header: first line must be '# Spec: <ticket or slug> <one-line outcome>'")

    def test_missing_section_fails(self):
        proc = self.run_check(GOOD_SPEC.replace("## Decisions", "## Notes"))
        self.assertProblems(proc, "missing section: ## Decisions")

    def test_missing_criteria_section_skips_coverage(self):
        proc = self.run_check(GOOD_SPEC.replace("## Acceptance criteria", "## Requirements"))
        self.assertProblems(proc, "missing section: ## Acceptance criteria")
        self.assertNotIn("cited in Verification", proc.stdout)

    def test_heading_case_and_suffix_are_tolerated_and_bom_ok(self):
        spec = "﻿" + GOOD_SPEC.replace("## Acceptance criteria", "## Acceptance Criteria (AC)")
        proc = self.run_check(spec)
        self.assertEqual((proc.returncode, proc.stdout.strip()), (0, "OK"))

    def test_criteria_without_ids_fail(self):
        proc = self.run_check(GOOD_SPEC.replace("`AC1`:", "-").replace("`AC2`:", "-").replace("`AC3`:", "-"))
        self.assertProblems(proc, "Acceptance criteria: no line starts with an AC1, AC2, ... id")

    def test_usage_and_read_errors_exit_2(self):
        for args in ([], ["a.md", "b.md"], ["/nonexistent/spec.md"]):
            with self.subTest(args=args):
                proc = subprocess.run([sys.executable, CHECK_SPEC, *args], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 2)
                self.assertNotIn("Traceback", proc.stderr)

    def test_spec_guide_points_to_the_checker(self):
        with open(os.path.join(SKILLS, "build", "spec.md"), encoding="utf-8") as fh:
            guide = fh.read()
        self.assertIn("scripts/check-spec.py", guide)
        self.assertIn("data shape", guide)
        for name in ("Goal", "Scope", "Acceptance criteria", "Design", "Verification", "Decisions"):
            self.assertIn(f"## {name}", guide)


# A fake `gh` driven by scenario.json: each check-runs poll serves the next frame,
# `run rerun` is logged, and a run's attempt counts its reruns.
FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_GH_DIR"]
with open(os.path.join(d, "scenario.json")) as fh:
    sc = json.load(fh)
sp = os.path.join(d, "state.json")
st = {"polls": 0, "reruns": [], "calls": []}
if os.path.exists(sp):
    with open(sp) as fh:
        st = json.load(fh)
args = sys.argv[1:]
st["calls"].append(args)
def done(code=0):
    with open(sp, "w") as fh:
        json.dump(st, fh)
    sys.exit(code)
if sc.get("fail"):
    print("HTTP 401: Bad credentials", file=sys.stderr)
    done(1)
if sc.get("garbage"):
    print("<html>rate limited</html>")
    done()
if args[:2] == ["run", "rerun"]:
    st["reruns"].append(args[2])
    done()
if args[:2] == ["pr", "view"]:
    if sc.get("no_pr"):
        print("no pull requests found for branch", file=sys.stderr)
        done(1)
    seq = sc.get("mergeable", ["MERGEABLE"])
    st["views"] = st.get("views", 0) + 1
    print(json.dumps({"url": "https://github.com/o/r/pull/7", "baseRefName": "main",
                      "mergeable": seq[min(st["views"] - 1, len(seq) - 1)]}))
    done()
path = next(a for a in args if a.startswith("repos/"))
frames = sc["frames"]
if "/check-runs" in path:
    frame = frames[min(st["polls"], len(frames) - 1)]
    st["polls"] += 1
    for page in frame.get("check_pages", [frame.get("check_runs", [])]):
        print(json.dumps({"total_count": len(page), "check_runs": page}, indent=2))
elif "/status" in path:
    frame = frames[min(st["polls"] - 1, len(frames) - 1)]
    print(json.dumps({"state": "pending", "statuses": frame.get("statuses", [])}))
elif "/actions/runs/" in path:
    rid = path.rsplit("/", 1)[1]
    print(json.dumps({"id": int(rid), "status": sc.get("run_status", "completed"),
                      "run_attempt": 1 + st["reruns"].count(rid)}))
done()
"""

SHA = "abc1234def5678"


def check_run(name, conclusion=None, status="completed", run=None,
              started="2999-01-01T00:00:00Z"):
    url = ("https://github.com/o/r/actions/runs/%s/job/%s0" % (run, run) if run
           else "https://ci.example/" + name)
    return {"name": name, "status": status, "conclusion": conclusion, "details_url": url,
            "started_at": started, "output": {"title": name + " title"}}


def commit_status(context, state, created="2999-01-01T00:00:00Z"):
    return {"context": context, "state": state, "target_url": "https://ci.example/" + context,
            "description": context + " said " + state, "created_at": created}


class CiVerdictTests(unittest.TestCase):
    def run_ci(self, frames, *extra, **scenario):
        d = self.last_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        if "first_call" in scenario:
            with open(os.path.join(d, "ci-%s.json" % SHA[:12]), "w") as fh:
                json.dump({"sha": SHA, "first_call": scenario.pop("first_call")}, fh)
        bindir = os.path.join(d, "bin")
        os.mkdir(bindir)
        fake = os.path.join(bindir, "gh")
        with open(fake, "w") as fh:
            fh.write(FAKE_GH)
        os.chmod(fake, 0o755)
        plan_doc = os.path.join(d, "plan.md")
        with open(plan_doc, "w") as fh:
            fh.write(scenario.pop("plan", "Verify: make test\nCI checks: %s\n" % json.dumps(scenario.pop("required", ["*"]))))
        with open(os.path.join(d, "scenario.json"), "w") as fh:
            json.dump(dict(scenario, frames=frames), fh)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"], FAKE_GH_DIR=d)
        proc = subprocess.run(
            [sys.executable, CI_VERDICT, "--sha", SHA, "--worktree", d, "--plan-doc", plan_doc,
             "--interval", "0", "--appear", "0", "--wait", "0", *extra],
            capture_output=True, text=True, env=env)
        state = {"polls": 0, "reruns": [], "calls": []}
        if os.path.exists(os.path.join(d, "state.json")):
            with open(os.path.join(d, "state.json")) as fh:
                state = json.load(fh)
        return proc, state

    def test_all_green_passes_with_evidence(self):
        proc, _ = self.run_ci([{"check_runs": [check_run("unit", "success", run=7),
                                               check_run("lint", "skipped", run=7)],
                                "statuses": [commit_status("ext", "success")]}])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.splitlines()[:2], ["VERDICT: PASS", "BLOCKING: none"])
        self.assertIn("unit (success)", proc.stdout)
        self.assertIn("ext (success)", proc.stdout)

    def test_failure_blocks_with_log_command(self):
        proc, _ = self.run_ci([{"check_runs": [check_run("unit", "failure", run=7),
                                               check_run("lint", "success", run=8)]}])
        self.assertEqual(proc.returncode, 1, proc.stdout)
        lines = proc.stdout.splitlines()
        self.assertEqual(lines[:2], ["VERDICT: FAIL", "BLOCKING:"])
        self.assertTrue(lines[2].startswith('- CI "unit" failure at abc1234: unit title'), lines[2])
        self.assertIn("log: gh run view --job 70 --log-failed", lines[2])
        self.assertNotIn("lint", "\n".join(lines[:3]))
        self.assertIn("NON-BLOCKING:", proc.stdout)

    def test_commit_status_failure_blocks(self):
        proc, _ = self.run_ci([{"statuses": [commit_status("buildkite", "failure")]}])
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn('- CI "buildkite" failure at abc1234: buildkite said failure', proc.stdout)

    def test_running_checks_report_pending(self):
        proc, _ = self.run_ci([{"check_runs": [check_run("unit", status="in_progress", run=7)]}])
        self.assertEqual(proc.returncode, 4, proc.stdout)
        self.assertEqual(proc.stdout.strip(), "PENDING: 1 of 1 checks running at abc1234")

    def test_polls_until_checks_finish(self):
        proc, state = self.run_ci([{"check_runs": [check_run("unit", status="queued", run=7)]},
                                   {"check_runs": [check_run("unit", "success", run=7)]}],
                                  "--wait", "30")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(state["polls"], 3)

    def test_reads_every_page(self):
        proc, _ = self.run_ci([{"check_pages": [[check_run("a", "success", run=1)],
                                                [check_run("b", "failure", run=2)]]}])
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn('CI "b" failure', proc.stdout)

    def test_conflicting_pr_exits_5_without_polling(self):
        green = [{"check_runs": [check_run("unit", "success", run=7)]}]
        proc, state = self.run_ci(green, "--appear", "5", "--wait", "5", mergeable=["UNKNOWN", "CONFLICTING"])
        self.assertEqual(proc.returncode, 5, proc.stdout)
        self.assertEqual(proc.stdout.strip(),
                         "CONFLICT: https://github.com/o/r/pull/7 conflicts with main; CI will not run")
        self.assertEqual((state["views"], state["polls"]), (2, 0))

    def test_mergeable_or_no_pr_goes_on_to_poll(self):
        green = [{"check_runs": [check_run("unit", "success", run=7)]}]
        for scenario in ({"mergeable": ["UNKNOWN", "MERGEABLE"]}, {"mergeable": ["UNKNOWN"]}, {"no_pr": True}):
            with self.subTest(**scenario):
                proc, state = self.run_ci(green, **scenario)
                self.assertEqual(proc.returncode, 0, proc.stdout)
                self.assertEqual(state["polls"], 2)

    def test_no_checks_means_no_ci(self):
        proc, _ = self.run_ci([{}])
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertTrue(proc.stdout.startswith("NO_CI: no CI check reported for abc1234"), proc.stdout)

    def test_all_skipped_means_no_ci(self):
        proc, _ = self.run_ci([{"check_runs": [check_run("unit", "skipped", run=7)]}])
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertIn("ran none of *", proc.stdout)

    def test_green_ci_without_the_named_checks_means_no_ci(self):
        proc, _ = self.run_ci([{"check_runs": [check_run("lint", "success", run=7)],
                                "statuses": [commit_status("cla", "success")]}], required=["unit*"])
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertEqual(proc.stdout.strip(), "NO_CI: CI at abc1234 ran none of unit*, so it did not run "
                         "the verify command; ran: lint (success), cla (success)")

    def test_named_check_skipped_means_no_ci(self):
        proc, _ = self.run_ci([{"check_runs": [check_run("unit", "skipped", run=7),
                                               check_run("lint", "success", run=7)]}], required=["unit"])
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertIn("ran none of unit,", proc.stdout)

    def test_glob_covers_matrix_jobs_and_every_name_must_pass(self):
        frame = {"check_runs": [check_run("test (3.12)", "success", run=7),
                                check_run("lint", "success", run=7)]}
        proc, _ = self.run_ci([frame], required=["test*", "lint"])
        self.assertEqual(proc.returncode, 0, proc.stdout)
        proc, _ = self.run_ci([frame], required=["test*", "build"])
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertIn("ran none of build,", proc.stdout)

    def test_a_failing_unnamed_check_still_fails(self):
        proc, _ = self.run_ci([{"check_runs": [check_run("unit", "success", run=7),
                                               check_run("lint", "failure", run=8)]}], required=["unit"])
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn('CI "lint" failure', proc.stdout)

    def test_plan_doc_without_named_checks_means_no_ci(self):
        green = [{"check_runs": [check_run("unit", "success", run=7)]}]
        for plan, reason in (("Verify: make test\n", "has no `CI checks:` line"),
                             ("CI checks: []\n", "`CI checks: []` names no check"),
                             ("CI checks: unit, lint\n", "`CI checks: unit, lint` names no check")):
            with self.subTest(plan=plan):
                proc, state = self.run_ci(green, plan=plan)
                self.assertEqual(proc.returncode, 3, proc.stdout)
                self.assertIn(reason, proc.stdout)
                self.assertEqual(state["polls"], 0)

    def test_cancelled_run_is_rerun_once_then_passes(self):
        cancelled = {"check_runs": [check_run("unit", "cancelled", run=7)]}
        proc, state = self.run_ci([cancelled, cancelled,
                                   {"check_runs": [check_run("unit", "success", run=7)]}],
                                  "--wait", "30")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(state["reruns"], ["7"])

    def test_infra_failure_after_rerun_means_no_ci(self):
        proc, state = self.run_ci([{"check_runs": [check_run("unit", "cancelled", run=7)]}],
                                  "--wait", "30")
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertEqual(state["reruns"], ["7"])
        self.assertIn("CI unavailable at abc1234: unit (cancelled)", proc.stdout)

    def test_rerun_in_flight_is_pending(self):
        proc, state = self.run_ci([{"check_runs": [check_run("unit", "cancelled", run=7)]}],
                                  run_status="in_progress")
        self.assertEqual(proc.returncode, 4, proc.stdout)
        self.assertEqual(state["reruns"], [])

    def test_rerun_of_an_old_check_keeps_waiting(self):
        old = {"check_runs": [check_run("unit", "cancelled", run=7,
                                        started="2000-01-01T00:00:00Z")]}
        proc, state = self.run_ci([old, old], "--wait", "0")
        self.assertEqual(state["reruns"], ["7"])
        self.assertEqual(proc.returncode, 4, proc.stdout)

    def test_external_error_status_is_not_rerun(self):
        proc, state = self.run_ci([{"statuses": [commit_status("ext", "error")]}])
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertEqual(state["reruns"], [])

    def test_failure_waits_for_running_checks(self):
        frames = [{"check_runs": [check_run("unit", "failure", run=7),
                                  check_run("e2e", status="in_progress", run=8)]},
                  {"check_runs": [check_run("unit", "failure", run=7),
                                  check_run("e2e", "failure", run=8)]}]
        proc, _ = self.run_ci(frames)
        self.assertEqual(proc.returncode, 4, proc.stdout)
        proc, state = self.run_ci(frames, "--wait", "30")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertEqual(state["polls"], 3)
        self.assertIn('CI "e2e" failure', proc.stdout)

    def test_check_created_after_first_finish_is_counted(self):
        proc, state = self.run_ci([{"check_runs": [check_run("unit", "success", run=7)]},
                                   {"check_runs": [check_run("unit", "success", run=7)],
                                    "statuses": [commit_status("codecov", "failure")]}])
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn('CI "codecov" failure', proc.stdout)

    def test_unreadable_gh_output_means_no_ci(self):
        proc, _ = self.run_ci([{}], garbage=True)
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertTrue(proc.stdout.startswith("NO_CI: could not read CI"), proc.stdout)

    def test_real_failure_wins_over_infra(self):
        proc, state = self.run_ci([{"check_runs": [check_run("unit", "failure", run=7),
                                                   check_run("e2e", "cancelled", run=8)]}])
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertEqual(state["reruns"], [])
        self.assertIn("unavailable: e2e (cancelled)", proc.stdout)

    def test_unknown_conclusion_never_passes(self):
        proc, _ = self.run_ci([{"check_runs": [check_run("unit", "brand_new", status="completed")]}])
        self.assertEqual(proc.returncode, 3, proc.stdout)

    def test_queued_forever_hits_the_deadline_across_calls(self):
        queued = [{"check_runs": [check_run("unit", status="queued", run=7, started=None)]}]
        proc, _ = self.run_ci(queued)
        self.assertEqual(proc.returncode, 4, proc.stdout)
        with open(os.path.join(self.last_dir, "ci-%s.json" % SHA[:12])) as fh:
            self.assertLess(abs(time.time() - json.load(fh)["first_call"]), 60)
        proc, state = self.run_ci(queued, first_call=time.time() - 3601)
        self.assertEqual(proc.returncode, 6, proc.stdout)
        self.assertEqual(proc.stdout.strip(), "TIMEOUT: CI did not finish within 3600s: unit (queued)")
        self.assertEqual(state["polls"], 1)

    def test_deadline_covers_reruns_but_not_finished_ci(self):
        cancelled = {"check_runs": [check_run("unit", "cancelled", run=7)]}
        proc, _ = self.run_ci([cancelled, cancelled], first_call=time.time() - 3601)
        self.assertEqual(proc.returncode, 6, proc.stdout)
        proc, _ = self.run_ci([{"check_runs": [check_run("unit", "success", run=7)]}],
                              first_call=time.time() - 3601)
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_gh_failure_means_no_ci(self):
        proc, _ = self.run_ci([{}], fail=True)
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertIn("Bad credentials", proc.stdout)

    def test_queries_are_bound_to_the_sha(self):
        _, state = self.run_ci([{"check_runs": [check_run("unit", "success", run=7)]}])
        paths = [a for call in state["calls"] for a in call if a.startswith("repos/")]
        self.assertIn("repos/{owner}/{repo}/commits/%s/check-runs?per_page=100" % SHA, paths)
        self.assertIn("repos/{owner}/{repo}/commits/%s/status?per_page=100" % SHA, paths)


REQ = "Add a `wordcount(text)` function to textkit; tokens made only of punctuation don't count."
REQ_SLUG = "add-a-wordcount-text-function-to-textkit"


FAKE_GH_PR = r"""#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_GH_DIR"]
sp = os.path.join(d, "gh.json")
st = json.load(open(sp)) if os.path.exists(sp) else {"prs": [], "calls": [], "comments": []}
args = sys.argv[1:]
st["calls"].append(args)
def opt(flag):
    return args[args.index(flag) + 1] if flag in args else None
def done(out="", code=0):
    json.dump(st, open(sp, "w"))
    if out:
        print(out)
    sys.exit(code)
def find(url):
    return next(p for p in st["prs"] if p["url"] == url)
if args[:2] == ["auth", "status"]:
    done(code=0 if os.environ.get("FAKE_GH_AUTH", "1") == "1" else 1)
if args[:2] == ["repo", "view"]:
    done("main")
if args[:2] == ["pr", "list"]:
    done(json.dumps([{"url": p["url"], "isDraft": p["draft"]} for p in st["prs"] if p["head"] == opt("--head")]))
if args[:2] == ["pr", "create"]:
    url = "https://github.com/o/r/pull/%d" % (len(st["prs"]) + 1)
    st["prs"].append({"url": url, "head": opt("--head"), "base": opt("--base"), "draft": "--draft" in args,
                      "title": opt("--title"), "body": open(opt("--body-file")).read()})
    done(url)
if args[:2] == ["pr", "ready"]:
    find(args[-1])["draft"] = "--undo" in args
    done()
if args[:2] == ["pr", "view"]:
    done(json.dumps({"body": find(args[2])["body"]}))
if args[:2] == ["pr", "edit"]:
    find(args[2])["body"] = open(opt("--body-file")).read()
    done()
if args[:2] == ["pr", "comment"]:
    st["comments"].append([args[2], open(opt("--body-file")).read()])
    done()
done("fake gh: unsupported " + " ".join(args), 1)
"""


class PrScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        os.mkdir(os.path.join(self.tmp, "bin"))
        with open(os.path.join(self.tmp, "bin", "gh"), "w") as fh:
            fh.write(FAKE_GH_PR)
        os.chmod(os.path.join(self.tmp, "bin", "gh"), 0o755)
        self.origin = os.path.join(self.tmp, "origin.git")
        self.git(self.tmp, "init", "-q", "--bare", self.origin)
        self.repo = os.path.join(self.tmp, "repo")
        self.git(self.tmp, "init", "-q", "-b", "feat", self.repo)
        self.git(self.repo, "config", "url.%s.insteadOf" % self.origin, "https://github.com/o/r.git")
        self.git(self.repo, "remote", "add", "origin", "https://github.com/o/r.git")
        self.commit("base")
        os.makedirs(os.path.join(self.repo, ".autopilot"))
        self.plan = os.path.join(self.repo, ".autopilot", "wc-plan.md")
        self.body = os.path.join(self.tmp, "body.md")
        with open(self.body, "w") as fh:
            fh.write("# Add wordcount\n\nCounts words.\n")

    def git(self, cwd, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", cwd, *args],
                              capture_output=True, text=True, check=True).stdout.strip()

    def commit(self, msg, workflow=None):
        if workflow:
            wf = os.path.join(self.repo, ".github", "workflows")
            os.makedirs(wf, exist_ok=True)
            with open(os.path.join(wf, "ci.yml"), "w") as fh:
                fh.write(workflow)
            self.git(self.repo, "add", "-A")
        self.git(self.repo, "commit", "-q", "--allow-empty", "-m", msg)

    def pr(self, *args, auth=True):
        env = dict(os.environ, PATH=os.path.join(self.tmp, "bin") + os.pathsep + os.environ["PATH"],
                   FAKE_GH_DIR=self.tmp, FAKE_GH_AUTH="1" if auth else "0")
        proc = subprocess.run([sys.executable, PR_SCRIPT, args[0], "--plan-doc", self.plan, *args[1:]],
                              capture_output=True, text=True, env=env)
        return proc.returncode, json.loads(proc.stdout) if proc.stdout.strip() else proc.stderr

    def start(self, *extra, auth=True):
        return self.pr("start", "--worktree", self.repo, "--body-file", self.body, *extra, auth=auth)

    def gh_state(self):
        with open(os.path.join(self.tmp, "gh.json")) as fh:
            return json.load(fh)

    def pushed(self):
        return subprocess.run(["git", "-C", self.origin, "rev-parse", "--verify", "-q", "refs/heads/feat"],
                              capture_output=True, text=True).stdout.strip()

    def test_publish_follows_the_ask_ci_and_auth(self):
        self.assertEqual(self.start()[1]["publish"], "none")
        self.commit("ci", workflow="on: [push, pull_request]\n")
        self.assertEqual(self.start(auth=False)[1]["publish"], "none")
        self.assertEqual(self.start()[1]["publish"], "ci")
        self.assertEqual(self.start("--requested")[1]["publish"], "pr")
        code, out = self.start("--requested", auth=False)
        self.assertEqual(code, 3)
        self.assertIn("not authenticated", out["reason"])

    def test_pull_request_triggers_are_detected_from_head(self):
        forms = {"on: [push, pull_request]\n": "ci", "on:\n  pull_request:\n    branches: [main]\n": "ci",
                 "on:\n  - push\n  - pull_request\n": "ci", "'on': pull_request_target\n": "ci",
                 "on:\n  push:\njobs:\n  a:\n    if: github.event_name == 'pull_request'\n": "none",
                 "on: [pull_request_review]\n": "none"}
        for text, want in forms.items():
            with self.subTest(text=text):
                self.commit("wf", workflow=text)
                self.assertEqual(self.start()[1]["publish"], want)

    def test_ci_pushes_at_pins_only_and_opens_one_draft(self):
        self.commit("ci", workflow="on: pull_request\n")
        self.start()
        self.commit("task 1")
        self.assertEqual(self.pr("push", "--task")[1]["pr"], "")
        self.assertEqual(self.pushed(), "")
        code, out = self.pr("push")
        self.assertEqual((code, out["pr"]), (0, "https://github.com/o/r/pull/1"))
        self.assertEqual(self.pushed(), self.git(self.repo, "rev-parse", "HEAD"))
        self.pr("push")
        prs = self.gh_state()["prs"]
        self.assertEqual(len(prs), 1)
        self.assertEqual((prs[0]["title"], prs[0]["body"], prs[0]["draft"], prs[0]["base"]),
                         ("Add wordcount", "Counts words.", True, "main"))
        self.pr("finish", "--report-file", self.body)
        self.assertEqual((self.gh_state()["prs"][0]["draft"], self.gh_state()["prs"][0]["body"]), (True, "Counts words."))

    def test_pr_pushes_each_task_and_posts_the_spec_once(self):
        spec = os.path.join(self.repo, ".autopilot", "wc-spec.md")
        with open(spec, "w") as fh:
            fh.write("# Spec\n")
        self.start("--requested", "--base", "release/2")
        self.pr("spec", "--spec-doc", spec)
        self.assertEqual(self.gh_state()["comments"], [])
        self.commit("task 1")
        self.pr("push", "--task")
        self.pr("push", "--task")
        self.pr("spec", "--spec-doc", spec)
        st = self.gh_state()
        self.assertEqual(st["comments"], [["https://github.com/o/r/pull/1", "# Spec\n"]])
        self.assertEqual(st["prs"][0]["base"], "release/2")
        self.assertEqual(self.pushed(), self.git(self.repo, "rev-parse", "HEAD"))

    def test_unsafe_base_stops(self):
        code, out = self.start("--requested", "--base", "main; rm -rf ~")
        self.assertEqual(code, 3)
        self.assertIn("base", out["reason"])

    def test_refused_push_stops_pr_and_drops_ci_to_local(self):
        hook = os.path.join(self.origin, "hooks", "pre-receive")
        with open(hook, "w") as fh:
            fh.write("#!/bin/sh\necho denied >&2\nexit 1\n")
        os.chmod(hook, 0o755)
        self.commit("ci", workflow="on: pull_request\n")
        self.start()
        code, out = self.pr("push")
        self.assertEqual((code, out["publish"], out["pr"]), (0, "none", ""))
        self.assertIn("push refused", out["reason"])
        self.assertEqual(self.pr("status")[1]["publish"], "none")
        self.start("--requested")
        code, out = self.pr("push")
        self.assertEqual(code, 3)
        self.assertIn("push refused", out["reason"])

    def test_a_ready_pr_is_drafted_and_restored_only_where_it_was_drafted(self):
        self.commit("ci", workflow="on: pull_request\n")
        with open(os.path.join(self.tmp, "gh.json"), "w") as fh:
            json.dump({"prs": [{"url": "https://github.com/o/r/pull/9", "head": "feat", "base": "main",
                                "draft": False, "title": "mine", "body": "Mine."}], "calls": [], "comments": []}, fh)
        report = os.path.join(self.tmp, "report.md")
        with open(report, "w") as fh:
            fh.write("All lenses passed.\n")
        out = self.start()[1]
        self.assertEqual((out["pr"], out["drafted"], self.gh_state()["prs"][0]["draft"]),
                         ("https://github.com/o/r/pull/9", True, True))
        self.pr("finish", "--report-file", report)
        pr = self.gh_state()["prs"][0]
        self.assertEqual((pr["draft"], pr["body"]), (False, "Mine."))
        self.pr("finish", "--report-file", report)
        self.assertEqual(sum(c[:2] == ["pr", "ready"] and "--undo" not in c for c in self.gh_state()["calls"]), 1)

    def test_pr_finish_appends_the_report_once_and_marks_ready(self):
        report = os.path.join(self.tmp, "report.md")
        with open(report, "w") as fh:
            fh.write("All lenses passed.\n")
        self.start("--requested")
        self.pr("push")
        self.pr("finish", "--report-file", report)
        self.pr("finish", "--report-file", report)
        pr = self.gh_state()["prs"][0]
        head = self.git(self.repo, "rev-parse", "HEAD")
        self.assertFalse(pr["draft"])
        self.assertEqual(pr["body"].count("<!-- autopilot-report %s -->" % head), 1)
        self.assertTrue(pr["body"].startswith("Counts words."))
        self.assertTrue(pr["body"].rstrip().endswith("All lenses passed."))

    def test_none_touches_nothing(self):
        self.start()
        self.commit("task")
        for args in (("push",), ("push", "--task"), ("finish", "--report-file", self.body)):
            self.assertEqual(self.pr(*args)[0], 0)
        self.assertEqual(self.pushed(), "")
        self.assertEqual([c[:2] for c in self.gh_state()["calls"]], [["auth", "status"]])

    def test_commands_before_start_stop(self):
        code, out = self.pr("push")
        self.assertEqual(code, 3)
        self.assertIn("run start first", out["reason"])


class ResolveBranchTests(unittest.TestCase):
    def setUp(self):
        # git reports resolved paths, and macOS's temp dir sits under the /var -> /private/var link.
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.new_repo("repo")

    def new_repo(self, name, branch="main"):
        path = os.path.join(self.tmp, name)
        self.git(self.tmp, "init", "-q", "-b", branch, path)
        self.git(path, "commit", "-q", "--allow-empty", "-m", "base")
        return path

    def git(self, cwd, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", cwd, *args],
                              capture_output=True, text=True, check=True).stdout.strip()

    def run_resolver(self, cwd, text, *args):
        fd, path = tempfile.mkstemp(dir=self.tmp)
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        return subprocess.run([sys.executable, RESOLVE_BRANCH, "--repo", cwd, "--input-file", path, *args],
                              capture_output=True, text=True)

    def resolve(self, cwd=None, text=REQ, *args):
        proc = self.run_resolver(cwd or self.repo, text, *args)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def plan_doc(self, worktree, name, input_text=REQ, phase="S5", branch="b"):
        out = self.resolve(worktree, input_text)
        os.makedirs(os.path.join(worktree, ".autopilot"), exist_ok=True)
        with open(os.path.join(worktree, ".autopilot", ".gitignore"), "w") as fh:
            fh.write("*\n")
        with open(os.path.join(worktree, ".autopilot", name), "w") as fh:
            fh.write("Rules: x y\nRESUME: phase=%s worktree=%s branch=%s base_ref=abc review_round=0 input_sha=%s\n%s\n"
                     "\n## Notes\n\nRESUME: phase=S1 input_sha=quoted-in-a-note\n"
                     % (phase, worktree, branch, out["input_sha"], input_text))
        return out["input_sha"]

    def test_default_branch_creates_a_worktree_at_head(self):
        out = self.resolve()
        self.assertEqual(out["mode"], "create")
        self.assertEqual(out["branch"], "autopilot-" + REQ_SLUG)
        self.assertEqual(out["worktree"], os.path.join(self.repo, ".claude", "worktrees", "autopilot-" + REQ_SLUG))
        self.assertEqual(out["base_ref"], self.git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(out["plan_doc"], os.path.join(out["worktree"], ".autopilot", REQ_SLUG + "-plan.md"))

    def test_codex_names_and_ticket_prefix(self):
        out = self.resolve(None, REQ, "--host", "codex", "--prefix", "TASK-7", "--slug", "word-count-helper")
        self.assertEqual(out["branch"], "codex/TASK-7-word-count-helper")
        self.assertEqual(out["worktree"], os.path.join(self.repo, ".codex", "worktrees", "TASK-7-word-count-helper"))

    def test_slug_collapses_and_caps(self):
        self.assertEqual(self.resolve(None, "  ***Fix: the `x`---bug!!  ")["slug"], "fix-the-x-bug")
        self.assertEqual(len(self.resolve(None, "word " * 30)["slug"]), 39)
        self.assertEqual(self.resolve(None, "!!!")["slug"], "run")

    def test_feature_branch_stays_in_place(self):
        self.git(self.repo, "checkout", "-q", "-b", "feature/wc")
        out = self.resolve()
        self.assertEqual((out["mode"], out["branch"], out["worktree"]), ("stay", "feature/wc", self.repo))
        self.assertEqual(out["base_ref"], self.git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(out["plan_doc"], os.path.join(self.repo, ".autopilot", REQ_SLUG + "-plan.md"))

    def test_dirty_feature_branch_stops(self):
        self.git(self.repo, "checkout", "-q", "-b", "feature/wc")
        with open(os.path.join(self.repo, "notes.txt"), "w") as fh:
            fh.write("wip\n")
        out = self.resolve()
        self.assertEqual(out["mode"], "stop")
        self.assertIn("notes.txt", out["reason"])

    def test_dirty_check_covers_the_whole_repo(self):
        self.git(self.repo, "checkout", "-q", "-b", "feature/wc")
        os.makedirs(os.path.join(self.repo, "sub"))
        with open(os.path.join(self.repo, "sub", "keep.txt"), "w") as fh:
            fh.write("x\n")
        self.git(self.repo, "add", "-A")
        self.git(self.repo, "commit", "-q", "-m", "sub")
        with open(os.path.join(self.repo, "top.txt"), "w") as fh:
            fh.write("wip\n")
        out = self.resolve(os.path.join(self.repo, "sub"))
        self.assertEqual(out["mode"], "stop")
        self.assertTrue(out["reason"].endswith("are the user's: top.txt"), out["reason"])

    def test_detached_head_creates(self):
        self.git(self.repo, "checkout", "-q", "--detach")
        self.assertEqual(self.resolve()["mode"], "create")

    def test_origin_default_counts_as_default(self):
        origin = self.new_repo("origin", branch="develop")
        clone = os.path.join(self.tmp, "clone")
        self.git(self.tmp, "clone", "-q", origin, clone)
        self.assertEqual(self.git(clone, "branch", "--show-current"), "develop")
        self.assertEqual(self.resolve(clone)["mode"], "create")
        self.git(clone, "remote", "set-head", "origin", "--delete")
        self.assertEqual(self.resolve(clone)["mode"], "create")

    def test_without_origin_only_main_and_master_count(self):
        self.git(self.repo, "checkout", "-q", "-b", "develop")
        self.assertEqual(self.resolve()["mode"], "stay")

    def test_resumes_the_unfinished_run_for_this_input(self):
        wt = os.path.join(self.tmp, "wt")
        self.git(self.repo, "worktree", "add", "-q", "-b", "autopilot-x", wt)
        self.plan_doc(wt, REQ_SLUG + "-plan.md", branch="autopilot-x")
        out = self.resolve()
        self.assertEqual((out["mode"], out["worktree"], out["branch"]), ("resume", wt, "autopilot-x"))
        self.assertEqual(out["plan_doc"], os.path.join(wt, ".autopilot", REQ_SLUG + "-plan.md"))

    def test_finished_run_is_left_alone(self):
        self.git(self.repo, "checkout", "-q", "-b", "feature/wc")
        self.plan_doc(self.repo, REQ_SLUG + "-plan.md", phase="done")
        out = self.resolve()
        self.assertEqual(out["mode"], "stay")
        self.assertEqual(out["plan_doc"], os.path.join(self.repo, ".autopilot", REQ_SLUG + "-2-plan.md"))

    def test_another_inputs_branch_collides(self):
        first = self.resolve()
        self.git(self.repo, "worktree", "add", "-q", "-b", first["branch"], first["worktree"])
        self.plan_doc(first["worktree"], REQ_SLUG + "-plan.md", input_text=REQ + " (older)")
        out = self.resolve()
        self.assertEqual(out["mode"], "create")
        self.assertEqual(out["branch"], first["branch"] + "-2")

    def test_finished_branch_without_its_worktree_is_not_reused(self):
        branch = "autopilot-" + REQ_SLUG
        wt = os.path.join(self.tmp, "old")
        self.git(self.repo, "worktree", "add", "-q", "-b", branch, wt)
        self.git(wt, "commit", "-q", "--allow-empty", "-m", "run1 work")
        self.git(self.repo, "worktree", "remove", wt)
        out = self.resolve()
        self.assertEqual((out["mode"], out["branch"]), ("create", branch + "-2"))

    def test_branch_behind_head_is_not_reused(self):
        branch = "autopilot-" + REQ_SLUG
        self.git(self.repo, "branch", branch)
        self.git(self.repo, "commit", "-q", "--allow-empty", "-m", "main moved on")
        self.assertEqual(self.resolve()["branch"], branch + "-2")

    def test_worktree_deleted_by_hand_counts_as_absent(self):
        branch = "autopilot-" + REQ_SLUG
        gone = os.path.join(self.tmp, "gone")
        self.git(self.repo, "worktree", "add", "-q", "-b", branch, gone)
        shutil.rmtree(gone)
        out = self.resolve()
        self.assertEqual(out["mode"], "reuse")
        self.assertNotEqual(out["worktree"], gone)

    def test_unsafe_current_branch_stops(self):
        self.git(self.repo, "checkout", "-q", "-b", "x$(id)y")
        out = self.resolve()
        self.assertEqual(out["mode"], "stop")
        self.assertIn("will not pass to a shell", out["reason"])

    def test_existing_branch_without_a_plan_doc_is_reused(self):
        branch = "autopilot-" + REQ_SLUG
        self.git(self.repo, "branch", branch)
        out = self.resolve()
        self.assertEqual((out["mode"], out["branch"]), ("reuse", branch))
        self.assertEqual(out["base_ref"], self.git(self.repo, "merge-base", "HEAD", branch))

    def test_requirement_text_never_reaches_a_shell(self):
        marker = os.path.join(self.tmp, "pwned")
        text = "fix login\nAUTOPILOT_INPUT\n$(touch %s) `touch %s`\n" % (marker, marker)
        out = self.resolve(None, text)
        self.assertEqual(out["mode"], "create")
        self.assertFalse(os.path.exists(marker))

    def test_unsafe_flags_are_rejected(self):
        for flag, value in (("--slug", "Fix $(id)"), ("--slug", "a" * 41), ("--prefix", "T;rm"),
                            ("--branch-prefix", "x y/"), ("--worktree-root", "../wt $(id)")):
            with self.subTest(flag=flag):
                proc = self.run_resolver(self.repo, REQ, flag, value)
                self.assertEqual(proc.returncode, 2, proc.stdout)
                self.assertEqual(proc.stdout, "")

    def test_empty_requirement_and_non_repo_fail(self):
        proc = self.run_resolver(self.repo, "  \n")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("is empty", proc.stderr)
        proc = self.run_resolver(self.tmp, REQ)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("resolve-branch: git", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_repo_conventions_shape_the_names(self):
        out = self.resolve(None, REQ, "--worktree-root", "../wt", "--branch-prefix", "frank/")
        self.assertEqual(out["branch"], "frank/autopilot-" + REQ_SLUG)
        self.assertEqual(out["worktree"], os.path.normpath(os.path.join(self.repo, "..", "wt", "autopilot-" + REQ_SLUG)))
        os.makedirs(out["worktree"])
        again = self.resolve(None, REQ, "--worktree-root", "../wt", "--branch-prefix", "frank/")
        self.assertEqual(again["branch"], "frank/autopilot-" + REQ_SLUG + "-2")

    def test_plan_and_spec_docs_share_a_free_stem(self):
        self.git(self.repo, "checkout", "-q", "-b", "feature/wc")
        os.makedirs(os.path.join(self.repo, ".autopilot"))
        open(os.path.join(self.repo, ".autopilot", REQ_SLUG + "-spec.md"), "w").close()
        out = self.resolve()
        self.assertEqual(out["plan_doc"], os.path.join(self.repo, ".autopilot", REQ_SLUG + "-2-plan.md"))
        self.assertEqual(out["spec_doc"], os.path.join(self.repo, ".autopilot", REQ_SLUG + "-2-spec.md"))

    def test_older_plan_doc_without_input_sha_is_not_resumed(self):
        self.git(self.repo, "checkout", "-q", "-b", "feature/wc")
        os.makedirs(os.path.join(self.repo, ".autopilot"))
        with open(os.path.join(self.repo, ".autopilot", "plan.md"), "w") as fh:
            fh.write("Rules: x y\n%s\n\nRESUME: phase=S6 worktree=%s branch=feature/wc base_ref=abc review_round=1\n"
                     % (REQ, self.repo))
        self.assertEqual(self.resolve()["mode"], "stay")

    def test_input_quoting_a_resume_line_still_resumes(self):
        text = REQ + "\nRESUME: phase=S1 input_sha=000000000000\n"
        wt = os.path.join(self.tmp, "wt")
        self.git(self.repo, "worktree", "add", "-q", "-b", "autopilot-x", wt)
        self.plan_doc(wt, "x-plan.md", input_text=text, branch="autopilot-x")
        with open(os.path.join(wt, ".autopilot", "x-spec.md"), "w") as fh:
            fh.write("RESUME: phase=S2 input_sha=whatever\n")
        out = self.resolve(None, text)
        self.assertEqual((out["mode"], out["plan_doc"]), ("resume", os.path.join(wt, ".autopilot", "x-plan.md")))
        self.assertEqual(out["spec_doc"], os.path.join(wt, ".autopilot", "x-spec.md"))

    def test_existing_worktree_without_a_plan_doc_is_reused(self):
        branch = "autopilot-" + REQ_SLUG
        wt = os.path.join(self.tmp, "existing")
        self.git(self.repo, "worktree", "add", "-q", "-b", branch, wt)
        out = self.resolve()
        self.assertEqual((out["mode"], out["branch"], out["worktree"]), ("reuse", branch, wt))
        self.assertEqual(out["plan_doc"], os.path.join(wt, ".autopilot", REQ_SLUG + "-plan.md"))

    def test_same_input_same_sha_whitespace_aside(self):
        self.assertEqual(self.resolve(None, REQ)["input_sha"], self.resolve(None, "\n" + REQ + "\n\n")["input_sha"])
        self.assertNotEqual(self.resolve(None, REQ)["input_sha"], self.resolve(None, REQ + "!")["input_sha"])


class ReviewRoundScriptTests(unittest.TestCase):
    """Contract, syntax and behavior of workflows/review-round.js. The runtime
    runs the body inside an async function with `args`, `phase`, `log`,
    `parallel` and `agent` in scope; the behavior test supplies stubs for them.
    """

    def run_round(self, args_js, verdicts):
        body = self.text.replace("export const meta", "const meta", 1)
        script = (
            "async function _wf(args, phase, log, parallel, agent) {\n%s\n}\n"
            "const verdicts = %s;\n"
            "const out = await _wf(%s, () => {}, () => {},\n"
            "  fns => Promise.all(fns.map(f => f())),\n"
            "  async (prompt, opts) => verdicts[opts.label]);\n"
            "console.log(JSON.stringify(out));\n"
        ) % (body, json.dumps(verdicts), args_js)
        with tempfile.TemporaryDirectory() as td:
            mjs = os.path.join(td, "round.mjs")
            with open(mjs, "w", encoding="utf-8") as fh:
                fh.write(script)
            proc = subprocess.run(["node", mjs], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_round_normalizes_every_verdict(self):
        members = [{"agent": a, "subagent_type": "autopilot:" + a, "prompt": "p"}
                   for a in ("silent", "pass-with-blocker", "clean", "fail")]
        verdicts = {
            "pass-with-blocker": {"VERDICT": "PASS", "BLOCKING": ["x.py:1 off by one"], "NON_BLOCKING": []},
            "clean": {"VERDICT": "PASS", "BLOCKING": [], "NON_BLOCKING": ["nit", 7]},
            "fail": {"VERDICT": "FAIL", "BLOCKING": ["y"], "NON_BLOCKING": []},
        }
        args = {"phase": "work", "members": members}
        for args_js in (json.dumps(args), json.dumps(json.dumps(args))):
            with self.subTest(args_js=args_js[:20]):
                out = self.run_round(args_js, verdicts)
                self.assertEqual(out["phase"], "work")
                got = {v["agent"]: (v["VERDICT"], v["BLOCKING"], v["NON_BLOCKING"], v["synthetic"])
                       for v in out["verdicts"]}
                self.assertEqual([v["agent"] for v in out["verdicts"]], [m["agent"] for m in members])
                self.assertEqual(got["silent"], ("FAIL", ["no verdict returned (skip/terminal error)"], [], True))
                self.assertEqual(got["pass-with-blocker"], ("FAIL", ["x.py:1 off by one"], [], False))
                self.assertEqual(got["clean"], ("PASS", [], ["nit"], False))
                self.assertEqual(got["fail"], ("FAIL", ["y"], [], False))

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_unparseable_args_dispatch_nothing(self):
        out = self.run_round(json.dumps("{not json"), {})
        self.assertEqual(out["verdicts"], [])

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
