# Implementation ticket graph

[한국어](README.md) | **English**

> Historical planning archive: the independent [cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools) project supersedes this original monorepo plan. These are preserved records, not the current implementation dispatch instructions.

Status: eleven local tickets are specified. None is implemented.
No external issues were created.
The [spec](../spec.en.md), [contracts](../contracts.en.md), and [execution rules](../execution.en.md) apply to every ticket.

| ID | Ticket | Blocked by | Observable delivery |
| --- | --- | --- | --- |
| 01 | [Extract reusable completion without terminal regressions](01-completion-core.en.md) | E01 completion reconciliation | Pure completion callers and unchanged terminal behavior |
| 02 | [Qualify the pinned 11.5 native parser worker](02-native-worker.en.md) | None | Database-free parsing through a version-checked process |
| 03 | [Lint paths and stdin through the qualified parser](03-lint-cli.en.md) | 02 | Agent CLI with explicit results, Unicode spans, and exit codes |
| 04 | [Prove completion and syntax diagnostics through LSP](04-lsp-slice.en.md) | 01, 03 | First full worker/core/CLI/LSP vertical slice |
| 05 | [Load offline schema snapshots in editor sessions](05-schema-snapshots.en.md) | 04 | Schema-aware editor completion without a database |
| 06 | [Qualify queries and DML through CLI and LSP](06-query-dml.en.md) | 04 | Query/DML diagnostics with catalog-independent behavior |
| 07 | [Qualify schema and engineer commands](07-schema-engineer.en.md) | 04 | DDL and CUBRID-specific command diagnostics |
| 08 | [Check mixed CSQL boundaries without session effects](08-script-boundaries.en.md) | 04 | Supported session lines and explicit unsupported constructs |
| 09 | [Deliver configurable Neovim integration](09-neovim.en.md) | 05, 08 | Completion, diagnostics, highlighting, indentation, and file associations |
| 10 | [Deliver configurable VS Code extension](10-vscode.en.md) | 05, 08 | Same shared features through a packaged VSIX |
| 11 | [Check installation and the complete delivery matrix](11-delivery.en.md) | 06, 07, 09, 10 | Reproducible local artifacts and end-to-end acceptance |

E01 is the external state described in the execution rules.
It completed in main commit `99d49e1` during planning.
Ticket 01 can proceed when its actual integration baseline contains that result.
Ticket 02 remains independent of the completion baseline.
Ticket 04 must pass before broad syntax work or editor packaging.
Tickets 05–08 can run concurrently with separate ownership after ticket 04.
Tickets 09 and 10 can then run concurrently.

The first two tickets establish necessary seams and qualification evidence.
Later tickets deliver narrow, observable behavior through the existing interfaces.
Native coverage tickets qualify existing grammar families. They do not implement an entire grammar.

## Assignment and completion records

The coordinator records the exact integration baseline before each dispatch.
Use one fresh-context agent and one isolated worktree per ticket.
Write reports under `tickets/reports/<ID>.md` during implementation.
Each report must map every acceptance criterion to a command, observation, and commit.
Update ticket status only after the coordinator verifies integration.

The [JSON graph](graph.json) is the machine-readable dependency snapshot.
Every listed acceptance recipe is a future implementation requirement.
The planning session did not create those recipes.

## Deferred work

Later tickets can add CTE/derived-result completion, live editor catalogs, PL/CSQL, Tree-sitter, semantic/style lint, or other platforms.
Those are not hidden acceptance requirements for these eleven tickets.
Other 11.5 builds and CUBRID 11.4 require separate profiles and corpus runs.
