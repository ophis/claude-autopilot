#!/usr/bin/env python3
"""Select the Claude Autopilot review panel for a phase: read the
``agents/`` frontmatter and print, as JSON, the reviewers to dispatch — ``core``
always, ``optional`` when an ``applies_to`` entry matches the phase's signals.
CLI: ``--phase spec|work`` with ``--spec-file`` (spec) or ``--worktree``/
``--base`` (work). Stdlib only.
"""
import argparse
import fnmatch
import glob
import json
import os
import subprocess
import sys

from _frontmatter import PHASES_OF, iter_kv, parse_applies_to, parse_tier, split_frontmatter, tier_for

_GLOB_CHARS = set("*?[/")

# Reserved applies_to token: matches (work phase only) on a file-topology change.
_STRUCTURAL_TOKEN = "@structural"


def _is_glob(entry):
    """An applies_to entry is a glob iff it contains a glob metacharacter."""
    return any(ch in _GLOB_CHARS for ch in entry)


def parse_frontmatter(path):
    """Parse an agent's frontmatter to the selector's keys (``name``, ``phase``,
    ``tier``, ``applies_to``); a file without a frontmatter block yields ``{}``.

    ``applies_to`` and ``tier`` are read by the shared parsers in
    ``_frontmatter.py``; a value they reject leaves the agent unselectable,
    which the roster lint reports. Malformed files never raise.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {}

    fm_lines, _body = split_frontmatter(text)
    if fm_lines is None:
        return {}

    fm = {}
    for key, value in iter_kv(fm_lines):
        if key == "applies_to":
            fm[key] = parse_applies_to(value) or []
        elif key == "tier":
            fm[key] = parse_tier(value)
        elif key in ("name", "phase"):
            fm[key] = value
    return fm


class GitError(Exception):
    pass


def _git_diff(worktree, base, mode):
    try:
        out = subprocess.run(
            ["git", "-C", worktree, "diff", mode, "%s...HEAD" % base],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise GitError(str(exc))
    if out.returncode != 0:
        raise GitError(out.stderr.decode("utf-8", "replace").strip() or "git diff exited %d" % out.returncode)
    return out.stdout.decode("utf-8", "replace").splitlines()


def changed_paths(worktree, base):
    """Changed paths from ``git -C <worktree> diff --name-only <base>...HEAD``."""
    return [line for line in _git_diff(worktree, base, "--name-only") if line.strip()]


def structural_change(worktree, base):
    """True iff the diff changed file topology (any A, D, R or C in
    ``git diff --name-status <base>...HEAD``); a pure in-place edit does not count.
    """
    return any(line.strip()[:1] in ("A", "D", "R", "C") for line in
               _git_diff(worktree, base, "--name-status") if line.strip())


def match_optional(applies_to, phase, paths, spec_text, structural):
    """Return the applies_to entries that match the phase's signals.

    ``@structural`` matches iff ``structural`` (a work-phase-only signal). work
    phase: globs fnmatch each changed path and its basename, keywords match as a
    case-insensitive substring of any path. spec phase: globs are ignored (no
    paths), keywords match as a substring of the already-lowercased spec text.
    """
    matched = []
    for entry in applies_to:
        if not isinstance(entry, str) or not entry:
            continue
        if entry == _STRUCTURAL_TOKEN:
            if structural:
                matched.append(entry)
            continue
        is_glob = _is_glob(entry)
        if phase == "work":
            if is_glob:
                hit = any(
                    fnmatch.fnmatch(p, entry)
                    or fnmatch.fnmatch(os.path.basename(p), entry)
                    for p in paths
                )
            else:
                needle = entry.lower()
                hit = any(needle in p.lower() for p in paths)
        else:
            if is_glob:
                hit = False  # no paths in spec phase -> globs cannot match
            else:
                hit = entry.lower() in spec_text
        if hit:
            matched.append(entry)
    return matched


ROSTER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agents")


def select(agents_dir, phase, paths, spec_text, structural):
    """Compute the selected panel for the phase. Returns a list of entry dicts.

    Sorted core-first then optional, each group name-sorted. Only the bundled
    roster dispatches by name; a lens from another folder runs as a generic agent
    given its ``file``, so it never resolves to a same-named bundled lens.
    """
    own = os.path.realpath(agents_dir) == os.path.realpath(ROSTER)
    pattern = os.path.join(agents_dir, "*.md")
    selected = []
    for path in sorted(glob.glob(pattern)):
        fm = parse_frontmatter(path)
        agent_phase = fm.get("phase")
        if not agent_phase:
            continue  # no phase => selector-inert (e.g. reviewer-contract.md)
        if phase not in PHASES_OF.get(agent_phase, ()):
            continue
        name = fm.get("name") or os.path.splitext(os.path.basename(path))[0]
        tier = fm.get("tier")
        applies_to = fm.get("applies_to") or []

        eff_tier = tier_for(tier, phase)

        if eff_tier == "core":
            matched = "core"
        elif eff_tier == "optional":
            matched = match_optional(applies_to, phase, paths, spec_text, structural)
            if not matched:
                continue
        else:
            continue  # unknown/absent tier: not a selectable reviewer

        selected.append(
            {
                "agent": name,
                "subagent_type": "autopilot:" + name if own else "general-purpose",
                "file": os.path.abspath(path),
                "tier": eff_tier,
                "matched": matched,
            }
        )

    selected.sort(key=lambda e: (0 if e["tier"] == "core" else 1, e["agent"]))
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Select the Claude Autopilot review panel for a phase."
    )
    parser.add_argument(
        "--phase", required=True, choices=["spec", "work"],
        help="review phase to select reviewers for",
    )
    parser.add_argument(
        "--agents-dir", default=ROSTER,
        help="directory of agent *.md files (default: <script_dir>/../agents)",
    )
    parser.add_argument(
        "--spec-file",
        help="spec phase: file whose text supplies keyword signals",
    )
    parser.add_argument(
        "--worktree",
        help="work phase: worktree path for the git diff",
    )
    parser.add_argument(
        "--base",
        help="work phase: base ref for the git diff (REF...HEAD)",
    )
    args = parser.parse_args(argv)

    agents_dir = os.path.abspath(args.agents_dir)
    if not os.path.isdir(agents_dir):
        parser.error("agents dir not found or not a directory: %s" % agents_dir)

    paths = []
    spec_text = ""
    structural = False  # spec phase never has a structural signal

    if args.phase == "work":
        # The diff inputs are the only optional-selection signal, so require them.
        if not args.worktree or not args.base:
            parser.error("--phase work requires both --worktree and --base")
        try:
            paths = changed_paths(args.worktree, args.base)
            structural = structural_change(args.worktree, args.base)
        except GitError as exc:
            sys.stderr.write("select-panel: git diff against %s failed: %s\n" % (args.base, exc))
            return 2
    else:
        # Spec-file optional: without it core still selects, keyword optionals don't.
        if args.spec_file:
            try:
                with open(args.spec_file, "r", encoding="utf-8") as fh:
                    spec_text = fh.read().lower()
            except OSError as exc:
                parser.error("could not read --spec-file: %s" % exc)

    selected = select(agents_dir, args.phase, paths, spec_text, structural)
    json.dump({"phase": args.phase, "selected": selected}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
