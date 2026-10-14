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
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
SELECT_PANEL = os.path.join(REPO, "skills", "build", "scripts", "select-panel.py")
CHECK_SPEC = os.path.join(REPO, "skills", "build", "scripts", "check-spec.py")
CI_VERDICT = os.path.join(REPO, "skills", "build", "scripts", "ci-verdict.py")
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
                      "with the re-review lines below on a re-review"):
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
            "EnterWorktree({path", "`autopilot:<name>`", "Agent tool",
            'Workflow({name: "autopilot:autopilot-review-round"', "resumeFromRunId", "synthetic",
            "force-push", "write outside the worktree", "history rewrite beyond this branch",
            "rm/reset of uncommitted work", "Auto Mode",
            "branch --show-current", "never a default branch", "git remote set-head origin -a",
            "if that fails too, only `main` and `master` count",
            "git worktree add <path> <branch>", "git worktree add <path> -b <branch> HEAD",
            "git merge-base HEAD <branch>",
            "git -C <worktree> status --porcelain", "git -C <worktree> rev-parse HEAD",
            "reviewed_sha", "One task is one commit", "fix(r<N>): <item IDs>",
            "git merge --squash",
            "git -C <worktree> diff <pre-fix HEAD>..HEAD",
            "VERIFICATION_UNAVAILABLE:", "autopilot:verification-reviewer",
            "`verification=local` or `verification=ci`", "exit code", "<lens>#<n>",
            "autopilot-result", "converged", "capped-without-pass", "stopped",
            "oscillation", "unfixable", "requirements-conflict",
            "root-contradiction", "phase-failure", "destructive-op",
            "spawn_agent", ".codex/worktrees/<prefix>-<slug>", "codex/<prefix>-<slug>",
            ".claude/worktrees/<prefix>-<slug>", "ci-verdict.py", "PR mode",
            "`verification=ci` in PR mode, else `verification=local`",
            "git -C <worktree> push -u origin <branch>",
            "gh pr create --draft", "gh pr ready <url>", '"pr": ""', "no planning skill", "### Task N",
            "git -C <worktree> log --oneline <base_ref>..HEAD", "Notes", ".autopilot/",
            "Fix causes, not symptoms", "records this `input`", "<slug>-plan.md",
            "refs/remotes/origin/HEAD", "stay on it", "Uncommitted changes here are the user's",
            "check `.autopilot/` in the current checkout and in a found worktree",
            "Skip steps 2-5 except `<slug>`",
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

    def test_pr_mode_is_checked_at_s1(self):
        text = flat(skill_text("light-build"))
        self.assertIn("**Check at S1.** It needs an authenticated `gh` and a GitHub `origin`", text)
        self.assertIn("name it in the task-list header at S4", text)
        self.assertIn("Once the branch is settled, in PR mode run its S1 check (PR mode).", text)
        self.assertIn("in PR mode the PR a continued branch updates (PR mode)", text)

    def test_reused_pr_goes_back_to_draft(self):
        text = flat(skill_text("light-build"))
        self.assertIn("gh pr ready --undo <url>", text)
        self.assertLess(text.index("gh pr ready --undo <url>"), text.index("gh pr create --draft"))
        self.assertIn("after any earlier run's", text)
        self.assertIn("unless the PR body already holds it", text)
        self.assertIn("A run that continues a branch updates that PR", text)

    def test_plan_doc_names_never_collide(self):
        text = flat(skill_text("build"))
        self.assertIn("adding `-2`, `-3`, … when that name holds another input's plan doc", text)

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
        self.assertIn("RESUME: phase=<S[1-7]>", text)
        self.assertIn("spec_file=", text)
        self.assertIn("every core lens", flat(text))
        self.assertIn("progress section", text)
        self.assertNotIn("## Preflight", text)
        self.assertNotIn("Load config", text)

    def test_light_build_specifics(self):
        with open(os.path.join(SKILLS, "light-build", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("RESUME: phase=<S[14-7]>", text)
        self.assertIn("## Forks", text)
        self.assertIn("data shape", text)
        self.assertIn("above RESUME", text)
        self.assertIn("after a PASS", flat(text))
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
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        bindir = os.path.join(d, "bin")
        os.mkdir(bindir)
        fake = os.path.join(bindir, "gh")
        with open(fake, "w") as fh:
            fh.write(FAKE_GH)
        os.chmod(fake, 0o755)
        with open(os.path.join(d, "scenario.json"), "w") as fh:
            json.dump(dict(scenario, frames=frames), fh)
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"], FAKE_GH_DIR=d)
        proc = subprocess.run(
            [sys.executable, CI_VERDICT, "--sha", SHA, "--worktree", d, "--interval", "0",
             "--appear", "0", "--wait", "0", *extra],
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

    def test_no_checks_means_no_ci(self):
        proc, _ = self.run_ci([{}])
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertTrue(proc.stdout.startswith("NO_CI: no CI check reported for abc1234"), proc.stdout)

    def test_all_skipped_means_no_ci(self):
        proc, _ = self.run_ci([{"check_runs": [check_run("unit", "skipped", run=7)]}])
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertIn("all skipped or neutral", proc.stdout)

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

    def test_rerun_of_an_old_check_is_not_judged_by_its_age(self):
        old = {"check_runs": [check_run("unit", "cancelled", run=7,
                                        started="2000-01-01T00:00:00Z")]}
        proc, state = self.run_ci([old, old], "--max-age", "60", "--wait", "0")
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

    def test_stuck_checks_give_up(self):
        proc, _ = self.run_ci([{"check_runs": [check_run("unit", status="queued", run=7,
                                                         started="2000-01-01T00:00:00Z")]}],
                              "--max-age", "60")
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertIn("CI still running after 60", proc.stdout)

    def test_gh_failure_means_no_ci(self):
        proc, _ = self.run_ci([{}], fail=True)
        self.assertEqual(proc.returncode, 3, proc.stdout)
        self.assertIn("Bad credentials", proc.stdout)

    def test_queries_are_bound_to_the_sha(self):
        _, state = self.run_ci([{"check_runs": [check_run("unit", "success", run=7)]}])
        paths = [a for call in state["calls"] for a in call if a.startswith("repos/")]
        self.assertIn("repos/{owner}/{repo}/commits/%s/check-runs?per_page=100" % SHA, paths)
        self.assertIn("repos/{owner}/{repo}/commits/%s/status?per_page=100" % SHA, paths)


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
