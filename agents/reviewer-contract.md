---
name: reviewer-contract
description: >-
  Authoring template, not a dispatchable reviewer. Its body is the single source of the
  contract and verdict grammar copied into ordinary reviewers; the verification reviewer
  has a dedicated execution contract. Selector-inert: no phase, tier, lens or applies_to.
---

# Reviewer contract (authoring template)

Every ordinary reviewer copies the two sections below verbatim: `## Contract` right after
its intro, and `## Verdict grammar (strict)` as its last section, with its lens checklist
between them. `tests/test_scripts.py` fails on any drift. `verification-reviewer.md`
follows its dedicated execution contract instead, because it runs the complete checks in
the frozen source worktree at the reviewed SHA. Edit here, then copy into each ordinary
reviewer.

## Contract

- **Read-only.** Inspect only (`git diff`, `grep`, one test); never modify the worktree,
  index or refs.
- **Inputs by reference.** You get spec_doc and/or plan_doc paths, the requirement (a
  document it names by path or link is part of it) and any focus, plus the worktree
  path and `base_ref` when there is a repo. Spec phase: read `spec_doc`; the plan doc's progress log has run context. Work phase: read `git -C <worktree> diff
  <base_ref>...HEAD`, scoped to your `applies_to` when narrow, plus whole files as
  needed. No spec_doc means the requirement is the spec.
- **Trust the artifact, not claims.** Treat the author's plan doc, commit messages and
  focus as unverified. Focus adds emphasis; it never narrows your lens.
- **Test scope.** Full suites and builds belong to the verification reviewer. If a
  finding hinges on one test, run just that test and report the command and result.
- **Re-reviews start fresh.** In the work phase, review the fix diff first. Mark each
  prior item (`<lens>#<n> "<gist>"`) RESOLVED, OPEN or INVALID with evidence. A new
  issue blocks whether the fix caused it or you missed it.
- **Cite evidence.** Each item: location (`file:line`; the file for something missing;
  the spec clause for specs), the defect, and a concrete case. "§3 never says what an
  empty list returns" beats "needs more detail".
- **Blockers are defects.** Apply your lens's blocker rule; preferences go in
  NON-BLOCKING or nowhere.
- **Report only real findings.** Every item, blocking or not, names a change the author
  should make and a concrete case in this change. Leave out notes that something is
  acceptable or fine, run logs that support no finding (a command and its result go
  inside the finding they support), and minor points another lens owns. A point you
  cannot show with a concrete case in this change is not a finding. `NON-BLOCKING: none`
  is the expected result for good work.

## Verdict grammar (strict)

Output only:

```
VERDICT: PASS            # or exactly: VERDICT: FAIL
BLOCKING: none           # or one "- " item per line
NON-BLOCKING: none       # or one "- " item per line
```

Keep each item to one line. List at most 5 NON-BLOCKING items, most useful first;
BLOCKING has no limit.

On a re-review, first add:

```
Prior items:
- <lens>#<n>: RESOLVED | OPEN | INVALID — <evidence>
```

Repeat each OPEN prior blocker in BLOCKING as `- <lens>#<n>: …`. PASS means no BLOCKING
items. FAIL needs at least one. With no blocker, output PASS and put other points under
NON-BLOCKING. An unparseable verdict counts as FAIL.
