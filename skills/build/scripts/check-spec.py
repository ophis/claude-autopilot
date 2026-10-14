#!/usr/bin/env python3
"""Check a build S2 spec against spec.md's structure.

CLI: ``python3 check-spec.py <spec-file>``. Prints one line per problem and exits 1,
prints ``OK`` and exits 0, or exits 2 on a usage or read error. Stdlib only.
"""
import re
import sys

REQUIRED = ("Goal", "Scope", "Acceptance criteria", "Design", "Verification", "Decisions")
MAX_RANGE = 100
# A criterion is defined where its id starts a line: "AC1:", "- **AC1**", "1. `AC1`".
AC_DEFINED = re.compile(r"(?m)^[\s>*\-+|]*(?:\d+[.)]\s*)?[`*_]*AC(\d+)\b")
AC_SPAN = re.compile(r"`?AC(\d+)`?[ \t]*(?:[-–—]|\.\.|to|through)[ \t]*`?AC(\d+)\b|\bAC(\d+)[-–](\d+)\b")
AC_ONE = re.compile(r"\bAC(\d+)\b")


def sections(text):
    found, title, body, fence = {}, None, [], None
    for line in text.splitlines():
        marker = re.match(r"\s*(```|~~~)", line)
        if marker:
            fence = None if fence == marker.group(1) else fence or marker.group(1)
        if fence is None and line.startswith("## "):
            if title is not None:
                found.setdefault(title, "\n".join(body))
            title, body = line[3:].strip(), []
        elif title is not None:
            body.append(line)
    if title is not None:
        found.setdefault(title, "\n".join(body))
    return found


def section(found, name):
    return next((body for title, body in found.items() if title.lower().startswith(name.lower())), None)


def cited(body):
    ids = set()
    for a, b, c, d in AC_SPAN.findall(body):
        lo, hi = sorted((int(a or c), int(b or d)))
        ids.update(range(lo, hi + 1) if 0 <= hi - lo <= MAX_RANGE else (lo, hi))
    ids.update(int(n) for n in AC_ONE.findall(AC_SPAN.sub(" ", body)))
    return ids


def check(text):
    problems = []
    if not re.match(r"\s*# Spec: \S", text):
        problems.append("header: first line must be '# Spec: <ticket or slug> <one-line outcome>'")
    found = sections(text)
    problems += [f"missing section: ## {name}" for name in REQUIRED if section(found, name) is None]
    criteria, verification = section(found, "Acceptance criteria"), section(found, "Verification")
    if criteria is None or verification is None:
        return problems
    defined = {int(n) for n in AC_DEFINED.findall(criteria)}
    if not defined:
        return problems + ["Acceptance criteria: no line starts with an AC1, AC2, ... id"]
    covered = cited(verification)
    problems += [f"AC{n}: no Verification row" for n in sorted(defined - covered)]
    problems += [f"AC{n}: cited in Verification but not defined" for n in sorted(covered - defined)]
    return problems


def main(argv):
    if len(argv) != 2:
        print("usage: check-spec.py <spec-file>", file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8-sig") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as err:
        print(f"cannot read {argv[1]}: {err}", file=sys.stderr)
        return 2
    problems = check(text)
    print("\n".join(problems) if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
