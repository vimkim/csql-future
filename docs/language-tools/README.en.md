# Shared CUBRID language tools: implementation packet

[한국어](README.md) | **English**

> Historical planning archive: the independent [cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools) project supersedes this original monorepo plan. These are preserved records, not the current implementation dispatch instructions.

Status: planning deliverables, 2026-10-28. The editor tools and lint commands described here do not exist yet.

Start with the [specification](spec.en.md), [contracts](contracts.en.md), and [ticket graph](tickets/README.en.md).
The [parser research](parser-research.en.md) explains the selected approach.
The [feasibility report](feasibility.en.md) records the experiment and its limits.
The [execution rules](execution.en.md) preserve integration and agent constraints.
The [verification record](verification.en.md) includes the initial test failure and successful reruns.

The selected design shares the existing Python completion implementation across the terminal and a language server.
A separate, version-pinned native parser worker supplies offline syntax diagnostics.
Neovim and VS Code use the same language server.
Initial highlighting uses Vim syntax rules and TextMate rules respectively.
Tree-sitter remains a later improvement.

The user selected **CUBRID 11.5 first**.
The initial qualification target is build `11.5.0.2704-cc94778`, matching the successful experiment.
That experiment proves a database-free parsing route on this host.
It does not establish complete 11.5 syntax coverage or production packaging.
Other 11.5 builds and CUBRID 11.4 require separate qualification.

## Repository snapshot

| Item | Value |
| --- | --- |
| Planning baseline | `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f` |
| Original task branch | `planning/language-tools` |
| Original task checkout | `/home/vimkim/gh/csql-future-project` |
| Merge destination | `main` in `/home/vimkim/gh/csql-future` |
| Canonical packet location | `/home/vimkim/gh/csql-future/docs/language-tools` after integration |
| Work record | `work-tracker show 569` |
| Completion integration observed | Work 568 completed in main commit `99d49e13698b609ff4885a418578f7f50485e82f` |

The primary checkout contained unrelated untracked legacy-package bytecode at inspection.
Other sessions own their worktrees and may advance independently.
The future coordinator must inspect live state before extracting completion code.
The user approved this planning packet's rebase, main integration, and main push.
The task branch was rebased onto completion integration commit `99d49e1` before combined verification.
Ticket 01 must include the integrated completion commit in its actual dispatch baseline.

## Delivery boundary

This packet selects eleven bounded implementation tickets.
Each ticket requires one new agent context and a separate worktree.
No implementation ticket was executed in this planning session.
Local planning commits are authorized.
Approval covers this planning packet's integration only.
Implementation integration requires its own concrete result and applicable approval.
Publishing extensions, packages, issues, PRs, or deployment requires separate authorization.
