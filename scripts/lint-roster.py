#!/usr/bin/env python3
"""Lint the Claude Autopilot review roster (A3): validate every ``agents/*.md``
so a malformed reviewer fails loudly at authoring/CI time instead of mis-routing
the selector. CLI: ``python3 scripts/lint-roster.py [--agents-dir DIR]``,
non-zero exit on any failure. Stdlib only.
"""
import argparse
import glob
import json
import os
import re
import sys

from _frontmatter import iter_kv, split_frontmatter

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
VALID_PHASES = {"spec", "work", "both"}
VALID_TIERS = {"core", "optional"}
READONLY_TOOLS = {"Read", "Grep", "Glob", "Bash"}
# Contract markers each reviewer inlines; presence check, not byte-equality
# (reviewers trim the contract). See agents/reviewer-contract.md.
CONTRACT_MARKERS = (
    "Read-only",
    "Inputs by reference",
    "Cite evidence",
    "Load no superpowers skills",
)
VERDICT_MARKERS = ("StructuredOutput", "VERDICT:", "BLOCKING:", "NON-BLOCKING:")
SELECTOR_KEYS = ("phase", "tier", "lens", "applies_to")


def parse_agent(path):
    """Read an agent markdown file into (frontmatter dict, body str), or
    ``(None, "")`` if it has no well-formed frontmatter block.

    Unlike the selector, the lint captures EVERY key with its own typing:
      * simple ``key: value``                                   -> string;
      * comma/flow list (``tools``, ``applies_to``)             -> list;
      * flow map (polymorphic ``tier``; scalar ``tier`` stays a string) -> dict;
      * block scalar (``description: >-``)                      -> "" (presence only).
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
        if key in ("applies_to", "tools"):
            fm[key] = _parse_list(value)
        elif key == "tier" and value.strip().startswith("{"):
            fm[key] = _parse_map(value)
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


def _parse_map(value):
    """Parse a single-line JSON flow-map (the polymorphic ``tier``) into a dict.

    Returns the raw string on parse failure / non-dict so the validator rejects
    it loudly instead of treating it as a malformed scalar.
    """
    try:
        parsed = json.loads(value.strip())
    except (ValueError, TypeError):
        return value.strip()
    return parsed if isinstance(parsed, dict) else value.strip()


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
            bad_phases = [p for p in tier if p not in VALID_PHASES]
            bad_tiers = [t for t in tier.values() if t not in VALID_TIERS]
            if not tier:
                reasons.append("tier map must not be empty")
            if bad_phases:
                reasons.append(
                    "tier map phase(s) %s not in {spec, work, both}"
                    % ", ".join(map(str, bad_phases))
                )
            if bad_tiers:
                reasons.append(
                    "tier map value(s) %s not in {core, optional}"
                    % ", ".join(map(str, bad_tiers))
                )
        elif tier not in VALID_TIERS:
            reasons.append("tier '%s' not in {core, optional}" % tier)

    if "maxTurns" in fm:
        mt = fm.get("maxTurns")
        try:
            mt_int = int(mt)
            if mt_int <= 0:
                reasons.append("maxTurns must be a positive int, got '%s'" % mt)
        except (TypeError, ValueError):
            reasons.append("maxTurns must be a positive int, got '%s'" % mt)

    if "applies_to" in fm:
        applies_to = fm["applies_to"]
        if not isinstance(applies_to, list) or not applies_to:
            reasons.append("applies_to must be a non-empty list")

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

    missing_markers = [m for m in CONTRACT_MARKERS if m not in body]
    if missing_markers:
        reasons.append(
            "body missing contract marker(s): " + ", ".join(missing_markers)
        )

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
        description="Lint the Claude Autopilot review roster (A3)."
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
