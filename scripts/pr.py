#!/usr/bin/env python3
"""Publish an autopilot run's branch as a draft pull request (common: Publish).

State lives in <plan doc stem>-pr.json beside the plan doc. Every subcommand prints it
as JSON: {publish, branch, base, pr, drafted, spec_posted, reason}. Exit 0, or 3 for a
safety stop (the reason is in the JSON).

  start --plan-doc P --worktree W --body-file F [--requested] [--base B]
        publish=pr when --requested, ci when the repo has a pull_request workflow and gh
        is authenticated for origin's host, else none. Adopts the branch's open PR and
        turns a ready one into a draft. F: first line is the title, the rest the body.
  push [--task]   push the branch (with --task only when publish=pr), then find or open
                  the draft PR. A refused push stops with pr and turns ci into none.
  spec --spec-doc S   with pr, post S as one PR comment, once (on the first push if no
                  PR exists yet).
  finish --report-file R   on convergence. pr: append R headed with HEAD's SHA, once,
                  and mark the PR ready. ci: mark it ready only if start drafted it.
  status
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

PR_TRIGGER = re.compile(r"""^\s*['"]?on['"]?\s*:.*\bpull_request(_target)?\b"""
                        r"""|^\s+(-\s*)?['"]?pull_request(_target)?['"]?\s*(:|$)""", re.M)
SAFE_BASE = re.compile(r"^[A-Za-z0-9._/-]+$")
HOST = re.compile(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^:/]+)[:/]")


class Stop(Exception):
    pass


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def gh(state, *args):
    proc = run(["gh", *args], state["worktree"])
    if proc.returncode != 0:
        lines = (proc.stderr or proc.stdout).strip().splitlines()
        raise Stop("gh %s failed: %s" % (" ".join(args[:2]), lines[-1] if lines else proc.returncode))
    return proc.stdout.strip()


def git(worktree, *args):
    proc = run(["git", "-C", worktree, *args], worktree)
    return proc.stdout.strip() if proc.returncode == 0 else None


def ci_workflows(worktree):
    listed = git(worktree, "ls-tree", "--name-only", "HEAD", ".github/workflows/") or ""
    return [path for path in listed.splitlines() if path.endswith((".yml", ".yaml"))
            and PR_TRIGGER.search(git(worktree, "show", "HEAD:" + path) or "")]


def state_path(plan_doc):
    return re.sub(r"(-plan)?\.md$", "", os.path.abspath(plan_doc)) + "-pr.json"


def save(state):
    with open(state["path"], "w", encoding="utf-8") as fh:
        json.dump({k: v for k, v in state.items() if k != "path"}, fh, indent=1)


def adopt(state):
    found = json.loads(gh(state, "pr", "list", "--head", state["branch"], "--state", "open",
                          "--json", "url,isDraft") or "[]")
    if found:
        state["pr"] = found[0]["url"]
        if not found[0]["isDraft"]:
            gh(state, "pr", "ready", "--undo", state["pr"])
            state["drafted"] = True


def body_file(text):
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def post_spec(state):
    if state["publish"] == "pr" and state["pr"] and state["spec_doc"] and not state["spec_posted"]:
        gh(state, "pr", "comment", state["pr"], "--body-file", state["spec_doc"])
        state["spec_posted"] = True


def start(args):
    worktree = os.path.abspath(args.worktree)
    with open(args.body_file, encoding="utf-8") as fh:
        title, _, body = fh.read().strip().partition("\n")
    state = {"path": state_path(args.plan_doc), "worktree": worktree,
             "branch": git(worktree, "branch", "--show-current") or "", "base": "", "pr": "",
             "drafted": False, "title": title.lstrip("# ").strip(), "body": body.strip(),
             "spec_doc": "", "spec_posted": False, "reason": ""}
    origin = git(worktree, "config", "--get", "remote.origin.url") or ""
    host = HOST.match(origin)
    authed = bool(host) and run(["gh", "auth", "status", "--hostname", host.group(1)], worktree).returncode == 0
    if args.requested and not authed:
        raise Stop("a pull request was asked for, but gh is not authenticated for origin %r" % origin)
    state["publish"] = "pr" if args.requested else "ci" if authed and ci_workflows(worktree) else "none"
    if state["publish"] != "none":
        if args.base and not SAFE_BASE.match(args.base):
            raise Stop("base %r has characters autopilot will not pass on" % args.base)
        state["base"] = args.base or gh(state, "repo", "view", "--json", "defaultBranchRef",
                                        "--jq", ".defaultBranchRef.name")
        adopt(state)
    return state


def push(state, args):
    if state["publish"] == "none" or (args.task and state["publish"] == "ci"):
        return state
    proc = run(["git", "-C", state["worktree"], "push", "-u", "origin", state["branch"]], state["worktree"])
    if proc.returncode != 0:
        reason = "push refused: %s" % ((proc.stderr.strip().splitlines() or ["exit %d" % proc.returncode])[-1])
        if state["publish"] == "pr":
            raise Stop(reason)
        state.update(publish="none", reason=reason)
        return state
    if not state["pr"]:
        adopt(state)
    if not state["pr"]:
        path = body_file(state["body"])
        try:
            state["pr"] = gh(state, "pr", "create", "--draft", "--base", state["base"], "--head",
                             state["branch"], "--title", state["title"], "--body-file", path).splitlines()[-1]
        finally:
            os.unlink(path)
    post_spec(state)
    return state


def spec(state, args):
    if state["publish"] == "pr":
        state["spec_doc"] = os.path.abspath(args.spec_doc)
        post_spec(state)
    return state


def finish(state, args):
    if state["publish"] == "pr":
        head = git(state["worktree"], "rev-parse", "HEAD")
        marker = "<!-- autopilot-report %s -->" % head
        body = json.loads(gh(state, "pr", "view", state["pr"], "--json", "body"))["body"] or ""
        if marker not in body:
            with open(args.report_file, encoding="utf-8") as fh:
                path = body_file("%s\n\n%s\n%s\n" % (body.rstrip(), marker, fh.read().strip()))
            try:
                gh(state, "pr", "edit", state["pr"], "--body-file", path)
            finally:
                os.unlink(path)
        gh(state, "pr", "ready", state["pr"])
    elif state["publish"] == "ci" and state["drafted"]:
        gh(state, "pr", "ready", state["pr"])
        state["drafted"] = False
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("start", "push", "spec", "finish", "status"):
        p = sub.add_parser(name)
        p.add_argument("--plan-doc", required=True)
        if name == "start":
            p.add_argument("--worktree", required=True)
            p.add_argument("--body-file", required=True, help="title line, then the body")
            p.add_argument("--requested", action="store_true", help="the requirement asks for a PR")
            p.add_argument("--base", help="the base branch the requirement names")
        if name == "push":
            p.add_argument("--task", action="store_true", help="an S5 task commit, not an S6 pin")
        if name == "spec":
            p.add_argument("--spec-doc", required=True)
        if name == "finish":
            p.add_argument("--report-file", required=True)
    args = parser.parse_args()
    state = None
    try:
        if args.cmd == "start":
            state = start(args)
        else:
            path = state_path(args.plan_doc)
            if not os.path.exists(path):
                raise Stop("no %s: run start first" % path)
            with open(path, encoding="utf-8") as fh:
                state = dict(json.load(fh), path=path)
            state = {"push": push, "spec": spec, "finish": finish}.get(args.cmd, lambda s, a: s)(state, args)
        code = 0
    except Stop as exc:
        state = state or {"publish": "none"}
        state["reason"], code = str(exc), 3
    if "path" in state:
        save(state)
    print(json.dumps({k: state.get(k) for k in ("publish", "branch", "base", "pr", "drafted",
                                                 "spec_posted", "reason")}))
    return code


if __name__ == "__main__":
    sys.exit(main())
