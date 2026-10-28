# Execution rules for the implementation packet

[한국어](execution.md) | **English**

These rules preserve the user-provided AGENTS instructions from the planning session.
Read them before dispatching any ticket.
Read `/home/vimkim/my-cubrid/CUBRID.md` before CUBRID-specific work.
Its personal policies override conflicting repository guidance.

## Scope and source of truth

The [spec](spec.en.md) and [contracts](contracts.en.md) define required behavior.
The [ticket files](tickets/README.en.md) define the selected implementation graph.
The [machine-readable graph](tickets/graph.json) repeats ticket IDs, files, and blocking edges for validation.
If they disagree, stop dispatch and reconcile them before implementation.
Local files are the issue tracker for this packet.
Do not create or update GitHub/JIRA issues without separate authorization.

The [starter corpus](corpus.json) contains requirements, not release qualification results.
The [probe evidence](evidence/native-probe.json) contains observed results on one 11.5 build.
Keep those evidence categories separate.
Do not copy historical completion-plan checkmarks into new acceptance reports.

## Checkout and integration

1. Inspect branches, worktrees, remotes, and dirty files.
2. Preserve unrelated work and other sessions' worktrees.
3. From `main`, `develop`, or `feature/*`, create a sibling task worktree and topic branch.
4. Record the starting branch as the merge destination.
5. Use the current checkout for another named task branch unless its agreed integration destination requires isolation.
6. Commit scoped changes after focused checks and diff review.
7. Stage only task files.
8. Ask once before rebasing onto the current local destination and merging.

After approval, check a clean destination on the expected branch.
Rebase onto its current tip.
Resolve conflicts, inspect the diff, and run proportionate checks.
Merge with `git merge --ff-only <rebased-task-commit>`.
Repeat under the same approval if the destination advances.
Use a squash merge only when rebase and fast-forward are impractical.
Abort any active rebase before the squash fallback.

The user's merge approval authorizes pushing `main` through its configured remote.
Other branch pushes need separate explicit authorization.
Extension/package publication and deployment also need separate authorization.
Before task cleanup, check that the destination retains its changes.
Remove only this task's linked worktree and local branch, without force.
Run worktree removal from outside that worktree.
Preserve valuable ignored/uncommitted files and report cleanup obstacles.
Never remove remote branches without explicit authorization.

The future implementation coordinator must obtain approval before integrating ticket branches into its integration destination.
It can request one approval for the concrete committed ticket results available for review.
Do not infer integration approval from this planning packet or an upstream skill's automatic-merge step.

## External completion dependency E01

Work 568 completed during planning.
Main includes its integration commit `99d49e13698b609ff4885a418578f7f50485e82f`.
Its owner removed the completion worktree and branch after integration.
Ticket 01 must check that its dispatch baseline includes that result or a verified successor.
Preserve the expanded command contexts, vocabulary, catalog fields, and regression coverage.
The planning packet was rebased onto `99d49e1` under the user's integration approval.
Use independent ticket 02 if ticket 01's integration baseline remains unresolved.
Record the checked baseline in the dispatch record.

## Fresh-agent contract

Use one new clean-context agent for each ticket.
In this harness, set `fork_turns="none"`.
Do not reuse an agent for a different ticket.
Give every agent a separate task branch and worktree.
Create them from the current verified integration tip.

Before dispatch, record the following exact values in a persistent assignment:

- Ticket ID and its file.
- Specification, contracts, execution rules, and applicable research pointers.
- Checkout, branch, and full baseline commit.
- Verified blocker commits and external dependency state.
- Permitted files and exclusive shared files.
- Acceptance commands and required observable outcomes.
- Existing authorization and remaining merge/publication gates.

The ticket's planning baseline is a context reference.
It is not a command to reset a later integration branch.
Never dispatch an assignment with an unresolved baseline commit.

An agent returns a scoped commit and an acceptance-to-evidence report.
The coordinator checks the combined result before releasing dependents.
An agent's completion message alone does not satisfy a blocker.
Use TDD for new behavior at public interfaces.
Do not add tests that merely repeat internal helper logic.
Retain external-process and PTY regressions for terminal changes.

Run independent ready tickets concurrently only after their shared interfaces are stable.
Serialize changes to packaging, task recipes, coverage aggregation, or other shared files.
The coordinator owns each integration and the durable state record.
Every ticket names its file ownership.
New ownership requires recording the reason and checking active assignments first.

## Tracking and verification

Planning work is item 569.
Do not mark the full ecosystem implemented when only this planning packet is complete.
The next implementation session should create a distinct substantive build item linked to 569.
Check the existing record before creating a duplicate.
Keep status, blockers, commits, and next actions in `work-tracker` notes and local ticket reports.

Rediscover the current `justfile` before running project checks.
At the planning baseline, `just test` runs Python unit and PTY tests.
`just build` creates Python source/wheel distributions.
New ticket acceptance recipes are requirements to add, not existing commands.
Keep missing mandatory native/editor test prerequisites visible.
A skipped native check cannot satisfy release qualification.

Use the `cubrid-build` skill for any native source setup/build.
Use the documented work environment workflow if an isolated database test is necessary.
No ticket may execute submitted lint text as a reference check.
Use reviewed fixed fixtures in an isolated database only for the existing catalog adapter.
Do not start CUBRID daemons for parser-only checks.

This host uses slow X11 forwarding.
Never start a visible GUI or auto-open a browser.
Use headless editor automation, terminal output, paths, and viewing URLs.

For ordinary next-step questions, review this session goal first.
After completion, say “We’re done” and run `work-tracker list --here` from the project directory.
Use an unscoped list only when the user asks what to do next today.
