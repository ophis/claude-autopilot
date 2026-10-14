#!/usr/bin/env python3
"""Resolve where an autopilot run works (common: Worktree (S1)).

Reads the requirement from --input-file (written with a file tool, so it never
passes through a shell) and prints one JSON object:
  {mode, branch, worktree, base_ref, plan_doc, spec_doc, input_sha, slug, ci_workflows,
   resume_line, reason}
mode is one of:
  resume  this input's unfinished plan doc exists; continue it
  stay    on a non-default branch with a clean tree; work in this checkout
  reuse   the branch exists without another run's plan doc; enter its worktree
  create  add a worktree for a new branch at local HEAD
  stop    uncommitted changes on a non-default branch (safety stop 3)
ci_workflows lists HEAD's workflow files that run on pull requests.
Nothing is changed, except that `git remote set-head origin -a` may record
origin's default branch when it is unknown.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

DEFAULT_NAMES = ("main", "master")
SAFE = {
    "prefix": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
    "slug": re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$"),
    "branch_prefix": re.compile(r"^[A-Za-z0-9._/-]*$"),
    "worktree_root": re.compile(r"^[A-Za-z0-9._/~-]+$"),
}
SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._/-]+$")
PR_TRIGGER = re.compile(r"""^\s*['"]?on['"]?\s*:.*\bpull_request(_target)?\b"""
                        r"""|^\s+(-\s*)?['"]?pull_request(_target)?['"]?\s*(:|$)""", re.M)


def git(repo, *args, check=True, strip=True):
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise SystemExit("resolve-branch: git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() if strip else proc.stdout


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")
    return slug or "run"


def default_branches(repo):
    names = set(DEFAULT_NAMES)
    ref = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    if ref is None and git(repo, "remote", "get-url", "origin", check=False) is not None:
        git(repo, "remote", "set-head", "origin", "-a", check=False)
        ref = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    if ref and ref.startswith("origin/"):
        names.add(ref[len("origin/"):])
    return names


def worktrees(repo):
    """(path, branch or None when detached) for every worktree of the repo."""
    out = []
    for line in (git(repo, "worktree", "list", "--porcelain") or "").splitlines():
        if line.startswith("worktree "):
            out.append([line[len("worktree "):], None])
        elif line.startswith("branch refs/heads/") and out:
            out[-1][1] = line[len("branch refs/heads/"):]
    return [tuple(entry) for entry in out if os.path.isdir(entry[0])]


def plan_docs(worktree):
    """(path, RESUME fields) for each plan doc in a worktree's .autopilot/. RESUME is the
    plan doc's second line, so the first match is it, never a quote further down."""
    docs = []
    for path in sorted(glob.glob(os.path.join(worktree, ".autopilot", "*plan.md"))):
        with open(path, encoding="utf-8", errors="replace") as fh:
            found = re.findall(r"^RESUME:(.*)$", fh.read(), re.M)
        if found:
            docs.append((path, dict(re.findall(r"(\w+)=(\S+)", found[0]))))
    return docs


def ci_workflows(repo):
    listed = git(repo, "ls-tree", "--name-only", "HEAD", ".github/workflows/", check=False) or ""
    return [path for path in listed.splitlines() if path.endswith((".yml", ".yaml"))
            and PR_TRIGGER.search(git(repo, "show", "HEAD:" + path, check=False) or "")]


def free_docs(worktree, slug):
    """Plan and spec doc paths sharing the first stem neither of whose names is taken."""
    taken = {os.path.basename(p) for p in glob.glob(os.path.join(worktree, ".autopilot", "*"))}
    stem, n = slug, 1
    while "%s-plan.md" % stem in taken or "%s-spec.md" % stem in taken:
        n += 1
        stem = "%s-%d" % (slug, n)
    return {"plan_doc": os.path.join(worktree, ".autopilot", "%s-plan.md" % stem),
            "spec_doc": os.path.join(worktree, ".autopilot", "%s-spec.md" % stem)}


def resolve(repo, text, prefix, slug, host, worktree_root, branch_prefix):
    input_sha = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:12]
    slug = slug or slugify(text)
    base = {"input_sha": input_sha, "slug": slug, "ci_workflows": ci_workflows(repo), "reason": ""}
    trees = worktrees(repo)
    for tree, _ in trees:
        for path, fields in plan_docs(tree):
            if fields.get("input_sha") == input_sha and fields.get("phase") != "done":
                return dict(base, mode="resume", branch=fields.get("branch"), worktree=tree,
                            base_ref=fields.get("base_ref"), plan_doc=path,
                            spec_doc=path[:-len("plan.md")] + "spec.md")

    top = git(repo, "rev-parse", "--show-toplevel")
    current = git(repo, "branch", "--show-current")
    if current and current not in default_branches(repo):
        if not SAFE_BRANCH.match(current):
            return dict(base, mode="stop", branch=current, worktree=top, base_ref=None, plan_doc=None,
                        spec_doc=None, reason="branch %r has characters autopilot will not pass to a shell" % current)
        dirty = git(top, "status", "--porcelain", "--", ".", ":(exclude).autopilot", strip=False)
        if dirty.strip():
            files = ", ".join(line[3:] for line in dirty.splitlines() if line.strip())
            return dict(base, mode="stop", branch=current, worktree=top, base_ref=None, plan_doc=None,
                        spec_doc=None, reason="uncommitted changes on %s are the user's: %s" % (current, files))
        return dict(base, mode="stay", branch=current, worktree=top,
                    base_ref=git(repo, "rev-parse", "HEAD"), **free_docs(top, slug))

    common = os.path.dirname(os.path.abspath(os.path.join(top, git(repo, "rev-parse", "--git-common-dir"))))
    root = os.path.normpath(os.path.join(common, os.path.expanduser(worktree_root or os.path.join("." + host, "worktrees"))))
    branch_prefix = ("codex/" if host == "codex" else "") if branch_prefix is None else branch_prefix
    head = git(repo, "rev-parse", "HEAD")
    n = 1
    while True:
        suffix = "" if n == 1 else "-%d" % n
        leaf = "%s-%s%s" % (prefix, slug, suffix)
        branch = branch_prefix + leaf
        path = os.path.join(root, leaf)
        exists = git(repo, "show-ref", "--verify", "--quiet", "refs/heads/" + branch, check=False) is not None
        tree = next((t for t, b in trees if b == branch), None)
        if exists:
            at_head = git(repo, "rev-parse", branch) == head
            if at_head and not (tree and plan_docs(tree)):
                where = tree or path
                return dict(base, mode="reuse", branch=branch, worktree=where,
                            base_ref=git(repo, "merge-base", "HEAD", branch), **free_docs(where, slug))
        elif not os.path.exists(path):
            return dict(base, mode="create", branch=branch, worktree=path, base_ref=head, **free_docs(path, slug))
        n += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input-file", required=True, help="file holding the requirement verbatim")
    parser.add_argument("--repo", default=".", help="the checkout the run starts in")
    parser.add_argument("--host", choices=("claude", "codex"), default="claude")
    parser.add_argument("--prefix", default="autopilot", help="a ticket ID when the work is for one ticket")
    parser.add_argument("--slug", help="lowercase-hyphenated name to use instead of the requirement's")
    parser.add_argument("--worktree-root", help="where the repo keeps worktrees, relative to its root")
    parser.add_argument("--branch-prefix", help="the repo's branch namespace (default codex/ on Codex)")
    args = parser.parse_args()
    for key in SAFE:
        value = getattr(args, key)
        if value is not None and not SAFE[key].match(value) or key == "slug" and value and len(value) > 40:
            parser.error("--%s %r: use only %s" % (key.replace("_", "-"), value, SAFE[key].pattern))
    with open(args.input_file, encoding="utf-8") as fh:
        text = fh.read()
    if not text.strip():
        raise SystemExit("resolve-branch: the requirement in %s is empty" % args.input_file)
    out = resolve(os.path.abspath(args.repo), text, args.prefix, args.slug, args.host,
                  args.worktree_root, args.branch_prefix)
    if out["mode"] in ("stay", "reuse", "create"):
        out["resume_line"] = "RESUME: phase=S1 worktree=%s branch=%s base_ref=%s review_round=0 input_sha=%s" % (
            out["worktree"], out["branch"], out["base_ref"], out["input_sha"])
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
