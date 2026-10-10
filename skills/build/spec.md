# Writing the spec (build S2)

Terse: tables over prose, exact names and values, each fact once. Guidance only; fill
each section from the requirement and the affected code.

**Header line:** `# Spec: <ticket or slug> <one-line outcome>`, then a line naming the
requirement source (path or quote) and its precedence over any other input.

## Goal
The outcome and why, in a few sentences.

## Scope
`In | Out` table; name the later work each Out item belongs to. Then constraints (e.g. no
version change, files that must not change).

## Terms (optional)
Each recurring idea named once, in bold, with its definition; reuse the name after.

## Design
Per file or component, a `### <path>` subsection: its names and exact behaviour as a
`Name | Behaviour` table, with exact error messages and exit codes. Docs changes as a
`File | Change` table, one home per fact.

## Errors (optional)
`Case | <entry point> | …` table: the behaviour of each failure case per entry point.

## Tests
Test first. Per test file, the cases. Hermetic: no real HOME or user env. Integration
tests where real processes matter. End with: every suite the repo names passes.

## Live check (optional: only when the repo asks for one)
What runs end to end and what it must show.

## Acceptance mapping
`Criterion | Covered by` table: each acceptance criterion → the tests, docs or check that
cover it.

## Decisions
Where the spec departs from or settles the requirement, each with its reason. What is
left to the implementer.
