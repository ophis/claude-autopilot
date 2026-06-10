#!/usr/bin/env python3
"""Select the Claude Autopilot review panel for a given phase (SPEC §8.6).

The build/fix commands run this once per review phase to compute *which* roster
reviewers to dispatch. It is a (mostly) pure function of:

  * the requested **phase** (``spec`` or ``work``),
  * the **roster** (the ``agents/*.md`` files and their YAML frontmatter), and
  * the **signals** for that phase:
      - *spec phase:* keyword text gathered from ``--spec-file``,
      - *work phase:* the changed paths from
        ``git -C <worktree> diff --name-only <base>...HEAD``.

Selection logic (per SPEC §8.6):
  1. Glob ``agents/*.md`` and parse each file's YAML frontmatter (the block
     between the first two ``---`` lines). Skip any file with no ``phase``
     (e.g. ``reviewer-contract.md`` — it is selector-inert).
  2. Keep agents whose ``phase`` is the requested phase or ``both``.
  3. ``tier: core``     -> always select (matched = ``"core"``).
  4. ``tier: optional`` -> select iff any ``applies_to`` entry matches a signal;
     matched = the list of matching entries.
  5. Matching: an ``applies_to`` entry is a GLOB if it contains any of
     ``* ? [ /`` else a KEYWORD.
       - *work phase:* glob -> ``fnmatch`` against each changed path AND its
         basename; keyword -> case-insensitive substring in any changed path.
       - *spec phase:* glob -> ignored (no paths); keyword -> case-insensitive
         substring in the spec text.

Output (stdout): JSON
  {"phase": "...",
   "selected": [{"agent","subagent_type","tier","matched"}, ...]}
where ``subagent_type`` = ``"autopilot:" + name`` (the native dispatch handle).
Order: core first then optional, then by name. There is intentionally no
"skipped" list.

Stdlib only (no deps; matches autopilot-config.py). Exits non-zero only on bad
args or an unreadable agents dir; a normal run (even with an empty diff or no
spec file) exits 0.
"""
import argparse
import fnmatch
import glob
import json
import os
import subprocess
import sys

from _frontmatter import iter_kv, split_frontmatter

# Characters that make an applies_to entry a glob pattern rather than a keyword.
_GLOB_CHARS = set("*?[/")


def _is_glob(entry):
    """An applies_to entry is a glob if it contains any glob metacharacter."""
    return any(ch in _GLOB_CHARS for ch in entry)


def parse_frontmatter(path):
    """Parse the YAML frontmatter block of an agent markdown file.

    Fence-finding and ``key: value`` scanning live in the shared
    ``_frontmatter`` module (one reader for this script and lint-roster.py).
    This wrapper keeps only the selector's typing: the keys we care about
    (``name``, ``phase``, ``tier``, ``applies_to``), with ``applies_to`` as a
    JSON-style array on a single line. Missing keys are simply absent; a file
    without a proper frontmatter block yields ``{}``.

    Tolerant by design: unknown keys are ignored, an unparseable ``applies_to``
    falls back to an empty list, and malformed files never raise.
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
        if key not in ("name", "phase", "tier", "applies_to"):
            continue
        if key == "applies_to":
            try:
                parsed = json.loads(value)
                fm[key] = parsed if isinstance(parsed, list) else []
            except (ValueError, TypeError):
                fm[key] = []
        else:
            fm[key] = value
    return fm


def changed_paths(worktree, base):
    """Return the list of changed paths from a git diff, or [] on failure.

    Uses ``git -C <worktree> diff --name-only <base>...HEAD``. A git error
    (e.g. unknown ref) yields an empty list rather than raising — an empty diff
    is a normal, non-error outcome.
    """
    try:
        out = subprocess.run(
            ["git", "-C", worktree, "diff", "--name-only", "%s...HEAD" % base],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return []
    if out.returncode != 0:
        return []
    text = out.stdout.decode("utf-8", "replace")
    return [line for line in text.splitlines() if line.strip()]


def match_optional(applies_to, phase, paths, spec_text):
    """Return the list of applies_to entries that match the phase's signals.

    work phase: glob entries fnmatch against each changed path and its
    basename; keyword entries match as a case-insensitive substring of any
    changed path.

    spec phase: glob entries are ignored (no paths); keyword entries match as a
    case-insensitive substring of the (already-lowercased) spec text.
    """
    matched = []
    for entry in applies_to:
        if not isinstance(entry, str) or not entry:
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
        else:  # spec phase
            if is_glob:
                hit = False  # no paths in spec phase -> globs cannot match
            else:
                hit = entry.lower() in spec_text
        if hit:
            matched.append(entry)
    return matched


def select(agents_dir, phase, paths, spec_text):
    """Compute the selected panel for the phase. Returns a list of entry dicts.

    Sorted core-first then optional, each group name-sorted.
    """
    pattern = os.path.join(agents_dir, "*.md")
    selected = []
    for path in sorted(glob.glob(pattern)):
        fm = parse_frontmatter(path)
        agent_phase = fm.get("phase")
        if not agent_phase:
            continue  # selector-inert (e.g. reviewer-contract.md)
        if agent_phase not in (phase, "both"):
            continue
        name = fm.get("name") or os.path.splitext(os.path.basename(path))[0]
        tier = fm.get("tier")
        applies_to = fm.get("applies_to") or []

        if tier == "core":
            matched = "core"
        elif tier == "optional":
            matched = match_optional(applies_to, phase, paths, spec_text)
            if not matched:
                continue  # no signal matched -> not selected (no skipped list)
        else:
            # Unknown/absent tier: not a recognized selectable reviewer.
            continue

        selected.append(
            {
                "agent": name,
                "subagent_type": "autopilot:" + name,
                "tier": tier,
                "matched": matched,
            }
        )

    # Deterministic order: core before optional, then by agent name.
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
    default_agents = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "agents"
    )
    parser.add_argument(
        "--agents-dir", default=default_agents,
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

    if args.phase == "work":
        # Work phase needs the diff inputs; without them there is no signal to
        # select optionals against, so fail clearly rather than silently.
        if not args.worktree or not args.base:
            parser.error("--phase work requires both --worktree and --base")
        paths = changed_paths(args.worktree, args.base)
    else:  # spec phase
        # Spec-file is optional: without it the keyword text is empty (core
        # agents are still returned; keyword-only optionals simply won't match).
        if args.spec_file:
            try:
                with open(args.spec_file, "r", encoding="utf-8") as fh:
                    spec_text = fh.read().lower()
            except OSError as exc:
                parser.error("could not read --spec-file: %s" % exc)

    selected = select(agents_dir, args.phase, paths, spec_text)
    json.dump({"phase": args.phase, "selected": selected}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
