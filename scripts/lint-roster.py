#!/usr/bin/env python3
"""Lint the Claude Autopilot review roster: validate every ``agents/*.md``
so a malformed reviewer fails loudly at authoring/CI time instead of mis-routing
the selector. CLI: ``python3 scripts/lint-roster.py [--agents-dir DIR]``,
non-zero exit on any failure. Stdlib only.
"""
import argparse
import glob
import os
import re
import sys

from _frontmatter import PHASES_OF, iter_kv, parse_applies_to, parse_tier, split_frontmatter

REQUIRED_KEYS = (
    "name",
    "description",
    "tools",
    "model",
    "effort",
    "maxTurns",
    "lens",
    "phase",
    "tier",
    "applies_to",
)
VALID_PHASES = set(PHASES_OF)
VALID_TIERS = {"core", "optional"}
READONLY_TOOLS = {"Read", "Grep", "Glob", "Bash"}
# Contract markers each reviewer inlines. tests/test_scripts.py also checks the
# real roster copies agents/reviewer-contract.md's sections verbatim.
CONTRACT_MARKERS = (
    "Read-only",
    "Inputs by reference",
    "Cite evidence",
    "Test scope",
)
VERIFICATION_REVIEWER = "verification-reviewer"
VERIFICATION_MARKERS = (
    "Frozen worktree",
    "Command evidence",
    "VERIFICATION_UNAVAILABLE:",
)
VERDICT_MARKERS = ("VERDICT:", "BLOCKING:", "NON-BLOCKING:")
SELECTOR_KEYS = ("phase", "tier", "lens", "applies_to")


def parse_agent(path):
    """Read an agent markdown file into (frontmatter dict, body str), or
    ``(None, "")`` if it has no well-formed frontmatter block.

    Every key is captured. ``applies_to`` and ``tier`` go through the parsers the
    selector uses (``None`` when they reject the value); ``tools`` is a comma or
    flow list; a block scalar (``description: >-``) reads as present-but-empty.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None, ""

    fm_lines, body = split_frontmatter(text)
    if fm_lines is None:
        return None, ""

    fm = {}
    for key, value in iter_kv(fm_lines):
        if key == "applies_to":
            fm[key] = parse_applies_to(value)
        elif key == "tier":
            fm[key] = parse_tier(value)
        elif key == "tools":
            fm[key] = _parse_list(value)
        else:
            # Block-scalar indicator reads as present-but-empty, not literal ">-".
            if value in (">-", ">", "|", ">+", "|-", "|+"):
                value = ""
            fm[key] = value

    return fm, body


def _parse_list(value):
    """Parse a frontmatter list value into a list of strings.

    Accepts a JSON-style flow list (``["**", "*.py"]``) or a bare comma list
    (``Read, Grep, Glob, Bash``). An empty value yields ``[]``.
    """
    value = value.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        items = []
        for part in inner.split(","):
            part = part.strip().strip('"').strip("'").strip()
            if part:
                items.append(part)
        return items
    return [p.strip() for p in value.split(",") if p.strip()]


def lint_reviewer(stem, fm, body):
    """Return a list of failure reasons for a reviewer file (empty = OK)."""
    reasons = []

    missing = [k for k in REQUIRED_KEYS if k not in fm]
    if missing:
        reasons.append("missing required key(s): " + ", ".join(missing))

    phase = fm.get("phase")
    if phase is not None and phase not in VALID_PHASES:
        reasons.append(
            "phase '%s' not in {spec, work, both}" % phase
        )

    if "tier" in fm:
        tier = fm["tier"]
        if isinstance(tier, dict):
            bad_tiers = [t for t in tier.values() if t not in VALID_TIERS]
            if bad_tiers:
                reasons.append(
                    "tier map value(s) %s not in {core, optional}"
                    % ", ".join(map(str, bad_tiers))
                )
            if phase in PHASES_OF and set(tier) != set(PHASES_OF[phase]):
                reasons.append(
                    "tier map keys %s must be exactly the phases this lens runs in: %s"
                    % (sorted(map(str, tier)), ", ".join(PHASES_OF[phase]))
                )
        elif tier not in VALID_TIERS:
            reasons.append("tier must be core, optional or a JSON object of phase -> tier, got '%s'" % tier)

    if "maxTurns" in fm:
        mt = fm.get("maxTurns")
        try:
            mt_int = int(mt)
            if mt_int <= 0:
                reasons.append("maxTurns must be a positive int, got '%s'" % mt)
        except (TypeError, ValueError):
            reasons.append("maxTurns must be a positive int, got '%s'" % mt)

    if "applies_to" in fm and fm["applies_to"] is None:
        reasons.append('applies_to must be a JSON array of non-empty strings, e.g. ["*.py"]')

    if "name" in fm and fm.get("name") != stem:
        reasons.append(
            "name '%s' does not match filename stem '%s'" % (fm.get("name"), stem)
        )

    if "tools" in fm:
        tools = set(fm.get("tools") or [])
        if tools != READONLY_TOOLS:
            extra = sorted(tools - READONLY_TOOLS)
            missing_tools = sorted(READONLY_TOOLS - tools)
            detail = []
            if extra:
                detail.append("disallowed " + ", ".join(extra))
            if missing_tools:
                detail.append("missing " + ", ".join(missing_tools))
            reasons.append(
                "tools must be exactly {Read, Grep, Glob, Bash} (%s)"
                % "; ".join(detail)
            )

    markers = ("Inputs by reference", *VERIFICATION_MARKERS) if stem == VERIFICATION_REVIEWER else CONTRACT_MARKERS
    missing_markers = [m for m in markers if m not in body]
    if missing_markers:
        reasons.append(
            "body missing contract marker(s): " + ", ".join(missing_markers)
        )

    if stem == VERIFICATION_REVIEWER:
        if phase != "work" or fm.get("tier") != "core" or fm.get("applies_to") != ["**"]:
            reasons.append("verification-reviewer must be work-only core with applies_to [\"**\"]")

    missing_verdict = [m for m in VERDICT_MARKERS if m not in body]
    if missing_verdict:
        reasons.append(
            "body missing verdict marker(s): " + ", ".join(missing_verdict)
        )
    else:
        if not _verdict_is_last_section(body):
            reasons.append(
                "verdict-grammar '## ' heading is not the last '## ' heading"
            )

    return reasons


def _verdict_is_last_section(body):
    """True iff all three verdict markers appear under the LAST ``## `` heading
    (the contract places the verdict grammar as the file's final section).
    """
    headings = [m.start() for m in re.finditer(r"(?m)^## ", body)]
    if not headings:
        return False
    last_section = body[headings[-1] :]
    return all(m in last_section for m in VERDICT_MARKERS)


def lint_template(fm):
    """Return a list of failure reasons for the contract template (empty = OK)."""
    reasons = []
    declared = [k for k in SELECTOR_KEYS if k in fm]
    if declared:
        reasons.append(
            "template must be selector-inert but declares: " + ", ".join(declared)
        )
    return reasons


def lint_file(path):
    """Classify and lint one agent file. Returns a list of reasons (empty = OK)."""
    stem = os.path.splitext(os.path.basename(path))[0]
    fm, body = parse_agent(path)
    if fm is None:
        return ["no well-formed '---' frontmatter block"]
    # Reviewer iff frontmatter declares a phase (mirrors select-panel.py).
    if "phase" in fm:
        return lint_reviewer(stem, fm, body)
    return lint_template(fm)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Lint the Claude Autopilot review roster."
    )
    default_agents = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "agents"
    )
    parser.add_argument(
        "--agents-dir",
        default=default_agents,
        help="directory of agent *.md files (default: <script_dir>/../agents)",
    )
    args = parser.parse_args(argv)

    agents_dir = os.path.abspath(args.agents_dir)
    if not os.path.isdir(agents_dir):
        parser.error("agents dir not found or not a directory: %s" % agents_dir)

    paths = sorted(glob.glob(os.path.join(agents_dir, "*.md")))
    if not paths:
        sys.stderr.write("FAIL: no agent files found in %s\n" % agents_dir)
        return 1

    failed = 0
    for path in paths:
        name = os.path.splitext(os.path.basename(path))[0]
        reasons = lint_file(path)
        if reasons:
            failed += 1
            print("FAIL %s: %s" % (name, "; ".join(reasons)))
        else:
            print("OK %s" % name)

    total = len(paths)
    print(
        "\n%d file(s) checked, %d OK, %d FAIL" % (total, total - failed, failed)
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
