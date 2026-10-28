# Shared CUBRID language tools specification

Status: implementation proposal supported by a narrow feasibility experiment.
The [contracts](contracts.md) define exact observable behavior.
The [ticket graph](tickets/README.md) defines implementation scope and order.

## Problem statement

CUBRID engineers already use the terminal wrapper's history and completion.
Editors and AI agents cannot reuse these capabilities through a stable interface.
A generic SQL parser can accept SQL that CUBRID rejects.
Running a script through CSQL also executes it, which cannot serve as default linting.

The project needs one completion implementation, explicit CUBRID syntax coverage, and consistent diagnostics across tools.
The terminal's existing behavior must remain available throughout the change.

## Solution

Keep all packages in this repository.
Extract the existing completion logic into a pure Python module.
Retain terminal menu state and catalog process ownership in terminal adapters.
Add an offline lint command and one language server.
Connect Neovim and VS Code to that server.

Use a native CUBRID parser worker for strict SQL parsing.
Run that worker in a separate process with a pinned source/build profile.
Keep tolerant completion independent of strict parse success.
An unavailable or unqualified parser produces an explicit failure or unsupported result.
It never produces a syntax pass.

The experiment accepted CUBRID serial syntax and rejected a malformed form without connecting to a database.
It also preserved completion for unfinished SQL.
See the [feasibility report](feasibility.md) for exact evidence and limitations.

## User stories

1. As a terminal user, I want existing completion and history behavior to survive extraction, so that my workflow continues.
2. As a library caller, I want text, a cursor, and an optional schema snapshot to produce suggestions without I/O.
3. As an engineer, I want completion for unfinished SQL, so that parser errors do not prevent editing.
4. As an engineer, I want table and alias-qualified column suggestions from an offline schema snapshot.
5. As an engineer, I want existing owner resolution and identifier quoting to remain consistent across clients.
6. As a Neovim user, I want `.csql` files to enable CUBRID support by default.
7. As a Neovim user, I want project-specific `.sql` associations without changing other SQL projects.
8. As a VS Code user, I want a dedicated CUBRID language identifier and configurable file associations.
9. As an editor user, I want highlighting and basic indentation even when the parser is unavailable.
10. As an editor user, I want completion replacement ranges to preserve surrounding SQL.
11. As an editor user, I want stale diagnostics to disappear after document changes or closure.
12. As a Korean-speaking engineer, I want correct locations around Korean text, emoji, multiline SQL, and CRLF.
13. As an AI agent, I want a deterministic stdin/path lint command with structured diagnostics.
14. As an AI agent, I want different exit outcomes for invalid syntax, unsupported coverage, and tool failures.
15. As an engineer, I want syntax checks to work without a database or credentials.
16. As an engineer, I want a missing table to remain distinct from invalid grammar.
17. As an engineer, I want the tool to identify the exact parser build and selected dialect settings.
18. As an engineer, I want unsupported CSQL commands and PL/CSQL bodies reported explicitly.
19. As an engineer, I want mixed script boundaries to preserve original diagnostic offsets.
20. As a maintainer, I want shared positive, negative, and incomplete fixtures across CLI and editor checks.
21. As a maintainer, I want one bounded ticket per fresh agent, so that work remains resumable across sessions.
22. As a user, I want installation instructions to distinguish the terminal package, editor dependencies, and native parser runtime.

## Implementation decisions

### Modules and responsibilities

| Module | Interface responsibility | Hidden implementation |
| --- | --- | --- |
| Completion core | Suggest replacements for document text, cursor, profile, and optional immutable schema | Tolerant tokenization, context, aliases, quoting, ordering |
| Syntax validator | Validate a document under an exact supported profile | Script classification, worker lifecycle, parser results, diagnostic conversion |
| Catalog adapter | Publish immutable schema snapshots | Existing CSQL metadata query, timeout, refresh, standalone lifecycle |
| Language server | Convert document events into core calls and protocol results | Document versions, scheduling, cancellation, client positions |
| Editor adapters | Associate files and start the configured language server | Editor configuration, lexical highlighting, indentation |

Tests call these same interfaces.
The completion core creates no processes and reads no environment variables.
The validator owns native worker failures.
Editor adapters contain no second SQL completion or validation implementation.

### Architecture

The terminal, lint CLI, and language server call the Python language modules.
Completion consumes document text and an optional schema snapshot.
The validator sends parse requests to the native worker.
Neovim and VS Code communicate with the same language server.
Highlighting and indentation use editor-native lexical rules in the first release.
Those rules do not establish syntax validity.

### Runtime and packaging

Retain Python 3.10+ and zero mandatory Python runtime dependencies for the wrapper and completion core.
The lint CLI uses the standard library and the separately installed native worker.
The language server uses an optional `lsp` dependency group with pygls 2.x.
Pin a tested version and its transitive dependencies during implementation.
The inspected pygls manifest requires Python 3.9+ and lists Python 3.10 through 3.14 among its targets.
This supports feasibility, not an untested compatibility promise. [Upstream manifest](https://raw.githubusercontent.com/openlawlibrary/pygls/main/pyproject.toml).

Build the worker against a qualified CUBRID client library and matching source headers.
Keep private native types behind the worker's process interface.
Do not require changes to the user's installed database server.
Do not vendor the full CUBRID repository into this project.
Record runtime library hashes, source commit, native version, settings, notices, and platform in a qualification manifest.

Initial end-to-end support is Linux x86-64.
Neovim uses its built-in client with version 0.11+ as the initial API target.
VS Code uses a desktop or Linux remote extension host with a user-installed Python/server command.
The extension must declare a minimum VS Code version tested against its selected language-client version.
Windows, macOS, browser-hosted VS Code, native ARM builds, and bundled parser downloads require separate qualification.

### CUBRID version and coverage

The user selected CUBRID 11.5 before 11.4.
The first qualification target is development build `11.5.0.2704-cc94778`, source commit `cc947788d3b7dc402f46192d0f3299ddcc8563ba`.
Use profile ID `cubrid-11.5.0.2704-cc94778`.
The experiment establishes narrow feasibility on that build.
Ticket 02 must qualify the production worker before dependent syntax work can complete.
Failure of that experiment blocks syntax delivery and requires revising the decision with evidence.
The experiment alone cannot satisfy the release gate.
Other 11.5 builds and CUBRID 11.4 need new profiles and qualification records.
The current source checkout's newer 11.5 HEAD is not the same parser build.
There is no automatic “closest version” fallback.

Use UTF-8, explicit quote rules, and a fixed string-escape setting in each profile.
The first profile matches `parser_parse_string_with_escapes(..., false)` and explicitly configured native defaults.
Ticket 02 records every syntax-relevant parameter read by the qualified path.
Unknown settings cannot silently inherit machine configuration.

Coverage grows through native statement kinds, conservative feature predicates, and fixtures.
Statement kind alone is insufficient because literal SELECT and complex queries share a native kind.
Before native parsing, admit only forms whose reachable grammar actions were audited.
Unknown forms produce unsupported coverage.
This prefilter controls coverage only and cannot produce a syntax pass without native parsing.
The first vertical slice supports literal SELECT and CREATE SERIAL.
Tickets 06 and 07 qualify the following release scope:

| Scope | Included behavior | Limits |
| --- | --- | --- |
| Queries and DML | SELECT, CTEs/subqueries, joins, expressions, INSERT, UPDATE, DELETE, MERGE | Syntax only; result-column inference for CTE completion remains deferred |
| Schema | CREATE/ALTER/DROP TABLE, VIEW, INDEX, SERIAL | Other object kinds remain unsupported until explicitly qualified |
| Engineer commands | SHOW, DESCRIBE/DESC, EXPLAIN where present in the selected release, EVALUATE, statistics, tracing, transaction/settings statements | Release-valid spellings come from pinned source/manual evidence, not this list alone |
| CSQL script commands | Exact `;help`, `;quit`, and `;autocommit on/off` lines | Validate spelling/arguments only; no session behavior executes |
| Unsupported script constructs | Other CSQL commands, external shell commands, includes, delimiter changes, PL/CSQL routine bodies | Return unsupported coverage; do not skip them and claim a complete pass |

This table selects work, not an assertion that every listed spelling exists in the pinned 11.5 build.
The coverage registry records native kinds, feature predicates, grammar productions, and reachable-action audits.
An unavailable statement in the selected release cannot enter its supported registry.
Every entry requires valid/invalid fixtures and an audit for catalog-dependent or executing grammar actions.
Syntax success certifies parser-stage acceptance within that registry and profile.
It does not certify catalog resolution, privileges, types, data constraints, or execution success.

### Existing terminal behavior and concurrent work

Preserve existing menu navigation, replacement, bypass, history, and catalog lifecycle contracts.
Keep client/server background refresh and sequential standalone snapshot preparation.
The extraction must include any completion extensions integrated by work 568 before implementation begins.
Do not freeze the older SHOW-only behavior as the permanent baseline.
No ticket modifies or integrates the other session's branch on its behalf.

Initial mandatory completion covers the integrated terminal baseline: keywords, relations, owners, quoting, aliases, columns, and supported command contexts.
CTE result-column inference, derived-table columns, correlated outer references, and synonyms remain later completion work.
The strict parser can support these constructs before completion understands their result schemas.

### Catalogs and offline use

Completion works without a schema snapshot and without a native worker.
Syntax validation works without a database and does not request a schema snapshot.
Editor v1 accepts an optional local schema snapshot file.
Its version, configured path, parse errors, stale status, and explicit reload behavior remain visible.
It contains schema metadata only, never credentials.
Live catalog queries remain available through the existing terminal adapter.
Automatic live database connections from editors are deferred.
Missing catalog data never becomes a syntax error.
No semantic lint or style rules are enabled in this release.

### Editor associations

Use a distinct `cubrid` filetype/language identifier.
Associate `.csql` by default.
Allow users to disable that default or add patterns.
Do not claim `.sql` globally.
Use workspace/user `files.associations` in VS Code and configurable filetype patterns in Neovim.
Associate opted-in `.sql` files with the same `cubrid` identifier.
Preserve other SQL projects and existing explicit user associations.

VS Code can start a server implemented in another language, and its settings support per-workspace associations.
Neovim supplies a built-in LSP client.
These are the integration mechanisms selected here. [VS Code server guide](https://code.visualstudio.com/api/language-extensions/language-server-extension-guide), [file associations](https://code.visualstudio.com/docs/languages/overview), [Neovim LSP](https://neovim.io/doc/user/lsp.html).

### Interfaces and failure behavior

Adopt the [contracts](contracts.md) before client implementation.
The core uses immutable input and output values with Unicode code-point offsets.
All source spans are half-open.
Worker and editor position conversions preserve the original document text.

Keep syntax errors, unsupported coverage, and tool failures separate.
Never emit `valid` for a document with unsupported statements or an unavailable parser.
The lint CLI reports all input files and uses a deterministic aggregate exit priority.
The language server uses the same diagnostic codes and converted spans.
Native crashes and timeouts never block completion.

## Testing decisions

Use observable contracts instead of tests that mirror internal helper functions.
Retain the current completion, metadata, external-process, and PTY tests as regression evidence.
Add a shared corpus with release identity, expected status, and diagnostic spans.
Every syntax family includes valid, deliberately invalid, and incomplete examples.

The first vertical slice must show a CUBRID serial diagnostic through the worker, lint CLI, and LSP.
It must also complete unfinished text through both the pure core and LSP.
Do this before broad syntax coverage or editor packaging.

Test offsets around Korean characters, emoji, CRLF, empty lines, EOF, and edits before an existing diagnostic.
Compare CLI/core spans with client ranges for the same fixtures.
Test wrong-version workers, missing runtimes, malformed worker output, crashes, deadlines, and stale responses.
Use fixed nonexecuting DDL/DML text to test containment.
Use read-only isolated catalog fixtures only when checking the existing terminal adapter.

Verify Neovim headlessly for `.csql`, opted-in `.sql`, and unrelated `.sql` files.
Verify the VS Code extension with headless extension-host tests and VSIX packaging.
Run installation checks from built artifacts in clean environments.
Only mark a supported platform/profile after these checks actually pass.

## Out of scope

This session implements no production language tool.
The release scope excludes a new Tree-sitter grammar, PL/CSQL validation, formatting, refactoring, live editor connections, and semantic/style lint.
It also excludes package/extension publication and additional repositories.
Full CUBRID syntax conformance across all releases is not a release claim.

## Further notes

The [parser research](parser-research.md) compares native reuse, Tree-sitter, SQLGlot, and ANTLR.
The chosen split follows that evidence and the narrow native experiment.
The [execution rules](execution.md) govern integration and fresh-agent assignments.
The ticket files remain the local task graph; this planning session creates no external issues.
