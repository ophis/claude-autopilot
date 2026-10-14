# Writing the spec (build S2)

Guidance, not a form: write tersely, with exact names and values, each fact once. Fill
each section from the requirement and the affected code. Required: Goal, Scope,
Acceptance criteria, Design, Verification, Decisions. Use a table only for two or more
rows.

**Header:** `# Spec: <ticket or slug> <one-line outcome>`, then a line naming the
requirement source (path or quote) and stating that it overrides any other input.

## Goal
The outcome, why, and what exists today, in a few sentences.

## Scope
`In | Out` table; for each Out item, the requirement ask it defers (if any) and the later
work it belongs to. Then constraints (e.g. no version change, files that must not
change).

## Terms (optional)
Each recurring idea named once, in bold, with its definition; reuse the name after.

## Acceptance criteria
`AC1`, `AC2`, …: each an input or action and its exact result, naming the requirement ask
it serves. Cover the edge, failure and absence cases the requirement implies: empty
input, errors, limits, what must not happen.

## Design
When the change adds or reshapes state, start with the data shape: the types or records,
and the structure that holds them (a state machine, table or typed model in place of
scattered conditionals). Keep the plain shape when it is clear and local; add no structure
that removes no branches or invalid states. Then only what a builder can't infer from the
code. One `### <path>` per file or component:
names, exact signatures and behaviour, error messages and exit codes. Docs changes per
file, one home per fact. For non-code work, one `### <artifact>` per deliverable with
its exact content or structure.

## Verification
Tests come first. An `AC | Test or check` table names the test (file and name) or check
for every criterion. Tests are hermetic (no real HOME or user env), with integration
tests where real processes matter. Add a live check only when the repo asks for one:
what runs end to end and what it must show. End with: every suite the repo names passes.

## Decisions
`D1`, `D2`, …: where the spec departs from or settles the requirement, each with its
reason. Name what is left to the implementer.

**Check.** Run `python3 scripts/check-spec.py <spec doc>` and fix every line it prints. It
checks the header, the required sections, and that every `AC` has a Verification row.
