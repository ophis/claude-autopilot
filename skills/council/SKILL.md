---
name: council
description: "Use at a genuine fork, a choice between viable options with materially different trade-offs or one costly to reverse, to get independent picks: 2–4 fresh subagents get one neutral brief (the question and options, the author's own words and the documents they name, read-only code) and each returns a pick. You log your pick first, then decide on the tally. Pass the question and its options."
argument-hint: "requirement=<text|path> <question and options>"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, Task, ToolSearch
---

# Autopilot: council

Tool names in parentheses are Claude Code forms. On another host, use the session's
exposed equivalent.

## Input

From the arguments, or from the skill that sends you here:

- **Questions**: one or more forks, each with its options. Required.
- **Requirement**: the author's own words, verbatim: text, or the file holding them.
  Required. A rewrite or summary of them is not the requirement. A document these words
  name by path or link goes with them; documents that document names do not.
- **Repo**: the checkout the work is in, read-only, when there is one.
- **Log**: where your fork and decision lines go. With none, put them in your reply.

A missing question or requirement: stop and say which.

## Steps

1. **Test what you can.** A question a quick run can answer (behavior, timing, output) is
   no fork: run it, log `checked(<topic>): <command> -> <result>`, and drop it. If no
   question remains, stop.
2. **Commit first.** Before convening, log each question with your own pick and the
   criteria you will decide on:
   `fork(<topic>): options=[<A>, <B>, …]; criteria=[<c1>, <c2>, …]; prior=<your pick>`.
3. **Convene** 2–4 fresh subagents in one parallel batch (`Task`). Each gets the same
   brief and nothing else:
   - the questions and their options, worded without a lean: options in alphabetical
     order of their short names, each with one pro line and one con line in the same
     form;
   - the requirement verbatim, and any document it names by path or link;
   - the absolute repo path, read-only, with `.autopilot/` off-limits, when there is a
     repo;
   - the ask: for every question, check its claims against the code when there is a
     repo, add an option nobody listed if one fits, return one pick with rationale and
     trade-offs, say whether only the requirement's author can decide it, and why, and
     say whether the brief leans toward an option.

   No other document (spec, plan or notes) beyond the requirement and the documents it
   names, no persona, and not your pick or criteria.
4. **Wait** for every answer. A question with fewer than two picks: decide it solo,
   with no tally.
5. **Decide** each question and log it:
   `decision(<topic>): chose X over Y - <short reason>; dissent: <one phrase | none>; tally=<X:2 Y:1>`.
   The tally counts members' picks only; your prior is not a vote. When another option
   has more than half the picks, add `; against majority: <reason>`. When no option has
   more than half, decide on your logged criteria and add `; criterion: <c>`.
   Adopt a member's addition that widens scope only by quoting the requirement clause
   that asks for it: `; adopted: <addition> per "<quote>"`. Without a quote, leave it out,
   log `omitted(<topic>): <addition>`, and show it to the author.
   A question most members flag as the author's call goes back to the author instead:
   log `decision(<topic>): author's call - <why>` and return the question. With fewer
   flags, decide it and show the author the question.
   A caller that decides everything itself shows and returns nothing to the author during
   the run; its final report lists the `omitted` lines. Word whatever goes to the author
   so they can answer without reading code.
