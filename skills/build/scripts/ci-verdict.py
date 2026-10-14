#!/usr/bin/env python3
"""Read the CI checks GitHub reports for one commit and print a verification verdict.

Run from the repo (or pass --worktree); `gh` must be authenticated. PASS needs each check
named by the plan doc's `CI checks:` (JSON array of names or globs) to succeed. Exit codes:
0 PASS and 1 FAIL (the verdict is on stdout), 4 checks still running (call again),
3 no usable CI result (run the local checks instead; the reason is on stdout).
"""

import argparse
import fnmatch
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

PASS, FAIL, PENDING, INFRA = "pass", "fail", "pending", "infra"

# Unlisted conclusions count as INFRA: never PASS, never sent to the fix loop.
RUN_CONCLUSIONS = {
    "success": PASS, "neutral": PASS, "skipped": PASS,
    "failure": FAIL, "timed_out": FAIL,
    "cancelled": INFRA, "stale": INFRA, "startup_failure": INFRA, "action_required": INFRA,
}
STATUS_STATES = {"success": PASS, "pending": PENDING, "failure": FAIL, "error": INFRA}
ACTIONS_URL = re.compile(r"/actions/runs/(\d+)(?:/job/(\d+))?")


class NoCI(Exception):
    pass


def required_checks(plan_doc):
    with open(plan_doc, encoding="utf-8") as fh:
        found = re.search(r"^CI checks: (.*)$", fh.read(), re.M)
    if not found:
        raise NoCI("the plan doc has no `CI checks:` line")
    try:
        required = json.loads(found.group(1))
    except ValueError:
        required = None
    if not (isinstance(required, list) and required and all(isinstance(n, str) and n for n in required)):
        raise NoCI("the plan doc's `CI checks: %s` names no check" % found.group(1).strip())
    return required


def gh(args, cwd):
    proc = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        lines = (proc.stderr or proc.stdout).strip().splitlines()
        raise NoCI("gh %s failed: %s" % (" ".join(args[:2]), lines[0] if lines else proc.returncode))
    return proc.stdout


def decode_all(text):
    """Parse `gh api --paginate` output: one JSON value per page, concatenated."""
    decoder, values, i, text = json.JSONDecoder(), [], 0, text.strip()
    while i < len(text):
        value, i = decoder.raw_decode(text, i)
        values.append(value)
        while i < len(text) and text[i].isspace():
            i += 1
    return values


def commit_items(sha, endpoint, key, cwd):
    out = gh(["api", "--paginate", "repos/{owner}/{repo}/commits/%s/%s?per_page=100" % (sha, endpoint)], cwd)
    return [item for page in decode_all(out) for item in page.get(key, [])]


def fetch_checks(sha, cwd):
    checks = []
    for run in commit_items(sha, "check-runs", "check_runs", cwd):
        completed = run.get("status") == "completed"
        url = run.get("details_url") or run.get("html_url") or ""
        m = ACTIONS_URL.search(url)
        checks.append({
            "name": run.get("name"),
            "state": RUN_CONCLUSIONS.get(run.get("conclusion"), INFRA) if completed else PENDING,
            "outcome": run.get("conclusion") if completed else run.get("status"),
            "url": url,
            "run_id": m.group(1) if m else None,
            "job_id": m.group(2) if m else None,
            "started": run.get("started_at"),
            "detail": (run.get("output") or {}).get("title") or "",
        })
    for status in commit_items(sha, "status", "statuses", cwd):
        checks.append({
            "name": status.get("context"),
            "state": STATUS_STATES.get(status.get("state"), INFRA),
            "outcome": status.get("state"),
            "url": status.get("target_url") or "",
            "run_id": None,
            "job_id": None,
            "started": status.get("created_at"),
            "detail": status.get("description") or "",
        })
    return checks


def age_seconds(stamp):
    try:
        started = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return 0
    return (datetime.now(timezone.utc) - started).total_seconds()


def names(checks):
    return ", ".join("%s (%s)" % (c["name"], c["outcome"]) for c in checks)


def blocking_item(check, sha):
    item = 'CI "%s" %s at %s' % (check["name"], check["outcome"], sha[:7])
    if check["detail"]:
        item += ": " + " ".join(check["detail"].split())
    if check["url"]:
        item += " (%s)" % check["url"]
    if check["job_id"]:
        item += "; log: gh run view --job %s --log-failed" % check["job_id"]
    return item


def print_verdict(verdict, blocking, non_blocking):
    print("VERDICT: " + verdict)
    for title, items in (("BLOCKING", blocking), ("NON-BLOCKING", non_blocking)):
        print(title + (":" if items else ": none"))
        for item in items:
            print("- " + item)


def rerun_or_pending(infra, cwd):
    """Rerun each first-attempt Actions run once. True while any rerun is in flight."""
    in_flight = False
    for run_id in sorted({c["run_id"] for c in infra if c["run_id"]}):
        run = json.loads(gh(["api", "repos/{owner}/{repo}/actions/runs/%s" % run_id], cwd))
        if run.get("status") != "completed":
            in_flight = True
        elif run.get("run_attempt", 1) == 1:
            gh(["run", "rerun", run_id, "--failed"], cwd)
            in_flight = True
    return in_flight


def settle(checks, args):
    """Exit code once every check has finished, or None while a rerun is in flight."""
    fails = [c for c in checks if c["state"] == FAIL]
    infra = [c for c in checks if c["state"] == INFRA]
    passed = [c for c in checks if c["state"] == PASS]
    sha = args.sha[:7]
    if fails:
        notes = ["CI at %s passed: %s" % (sha, names(passed))] if passed else []
        if infra:
            notes.append("CI at %s unavailable: %s" % (sha, names(infra)))
        print_verdict("FAIL", [blocking_item(c, args.sha) for c in fails], notes)
        return 1
    if infra:
        if rerun_or_pending(infra, args.worktree):
            return None
        raise NoCI("CI unavailable at %s: %s" % (sha, names(infra)))
    missing = [p for p in args.required
               if not any(c["outcome"] == "success" and fnmatch.fnmatchcase(c["name"] or "", p) for c in passed)]
    if missing:
        raise NoCI("CI at %s ran none of %s, so it did not run the verify command; ran: %s"
                   % (sha, ", ".join(missing), names(passed) or "nothing"))
    print_verdict("PASS", [], ["CI at %s passed: %s" % (sha, names(passed))])
    return 0


def verdict(args):
    now = time.monotonic()
    deadline, appear_deadline = now + args.wait, now + args.appear
    finished = None
    while True:
        checks = fetch_checks(args.sha, args.worktree)
        if not checks:
            if time.monotonic() >= min(deadline, appear_deadline):
                raise NoCI("no CI check reported for %s within %ss" % (args.sha[:7], args.appear))
        else:
            waiting = [c for c in checks if c["state"] == PENDING]
            rerunning = False
            if not waiting:
                # Settle on the second identical all-done poll: a finished workflow can
                # still trigger another (workflow_run) or a status posted after it.
                snapshot = sorted((c["name"] or "", c["outcome"] or "") for c in checks)
                if snapshot != finished:
                    finished = snapshot
                    time.sleep(args.interval)
                    continue
                code = settle(checks, args)
                if code is not None:
                    return code
                waiting = [c for c in checks if c["state"] == INFRA]
                rerunning = True  # their stamps are the first attempt's, so age says nothing
            if not rerunning and max(age_seconds(c["started"]) for c in waiting) > args.max_age:
                raise NoCI("CI still running after %ss: %s" % (args.max_age, names(waiting)))
            if time.monotonic() >= deadline:
                print("PENDING: %d of %d checks running at %s" % (len(waiting), len(checks), args.sha[:7]))
                return 4
        time.sleep(args.interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sha", required=True, help="the reviewed commit")
    parser.add_argument("--worktree", default=".", help="repo checkout to run gh in")
    parser.add_argument("--plan-doc", required=True, help="the run's plan doc, holding `CI checks:`")
    parser.add_argument("--wait", type=float, default=540, help="seconds to wait in this call")
    parser.add_argument("--appear", type=float, default=180, help="seconds to wait for a first check")
    parser.add_argument("--interval", type=float, default=20, help="seconds between polls")
    parser.add_argument("--max-age", type=float, default=3600, help="give up on checks running longer")
    args = parser.parse_args()
    try:
        args.required = required_checks(args.plan_doc)
        return verdict(args)
    except NoCI as exc:
        print("NO_CI: %s" % exc)
    except Exception as exc:  # exit 1 must only ever mean a real CI failure
        print("NO_CI: could not read CI: %r" % exc)
    return 3


if __name__ == "__main__":
    sys.exit(main())
