# Language tool contracts, revision 1

[한국어](contracts.md) | **English**

> Historical planning archive: the independent [cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools) project supersedes this original monorepo plan. These are preserved records, not the current implementation dispatch instructions.

These are implementation requirements.
No entry point in this document is available at the planning baseline.
See the [spec](spec.en.md) for scope and the [tickets](tickets/README.en.md) for delivery order.

## Text and positions

The core accepts a Unicode string containing the original text.
Its offsets count Unicode code points from zero.
A span `[start, end)` includes `start` and excludes `end`.
Both offsets must satisfy `0 <= start <= end <= len(text)`.
Completion cursor offsets use the same convention.

Do not normalize Unicode, newline spelling, case, or whitespace before mapping offsets.
In CRLF, CR and LF occupy separate code points.
The next logical line starts after LF.
Protocol positions exclude the line terminator.
Positions inside a CRLF terminator are invalid external input.
The adapter rejects them rather than altering the document.

Build explicit per-document maps among code-point offsets, UTF-8 byte offsets, and UTF-16 protocol positions.
Never use a native byte column directly as an editor character index.
Reject offsets inside a multibyte UTF-8 sequence or UTF-16 surrogate pair.
Use zero-based lines internally and in LSP.
Human CLI locations use one-based line and code-point column.

LSP v1 negotiates UTF-16 and uses UTF-16 when the client omits position encodings.
Do not advertise UTF-8 support before implementing and testing it.
The completion edit replaces the entire selected token span, including the suffix after the cursor.
An empty span inserts at the cursor.

Native error coordinates are private adapter input.
Ticket 02 must measure their units against the selected build.
If native data cannot identify a reliable token, use a statement span with `rangePrecision: statement`.
For EOF errors, a zero-length EOF span is allowed.
Do not present an estimated token range as exact.

Example text `가😀x\r\nSELECT 1;` places `x` at code-point offset 2, UTF-8 byte offset 7, and UTF-16 character 3.
The second line starts at code-point offset 5 and UTF-8 byte offset 10.

## Completion interface

`complete(text, cursor, profile, schema=None)` returns one immutable result.
The result contains a replacement span, ordered items, an allowed flag, and optional availability information.
Each item contains insertion text, a label, and a kind/detail.
Caller-supplied schema values preserve the integrated terminal schema, including users, database identity, system flags, and indexes.

Calls perform no filesystem, network, subprocess, environment, or terminal operations.
The same inputs produce the same ordered output.
Incomplete SQL remains eligible for completion.
Comments and string contents suppress SQL completion.
Session-command completion follows the integrated terminal baseline.
Unknown schema data limits suggestions without inventing names.

The existing `suggest` entry point remains as a compatibility adapter during migration.
Terminal menu state remains outside this interface.
Catalog acquisition remains outside this interface.

## Validation interface

`validate(text, profile, script_mode)` returns status, coverage, profile identity, and diagnostics.
The validator accepts document text only.
It never accepts a database connection or executes submitted text.
Profile selection is explicit and does not depend on a database server version probe.

| Status | Required meaning |
| --- | --- |
| `valid` | Every statement belongs to qualified coverage and passes the selected parser-stage checks |
| `syntax-error` | At least one supported statement has a parser-stage syntax error |
| `unsupported` | No syntax error occurred, but some language/version coverage is unsupported |
| `tool-error` | Input acquisition, configuration, initialization, or worker operation failed |

Coverage is `complete` only when every statement can be checked under the selected profile.
Otherwise it is `partial` or `none`.
Syntax errors and unsupported regions can coexist in one result.
Preserve both diagnostics.
Apply status priority `tool-error > syntax-error > unsupported > valid`.
Parser failure must not erase earlier errors or return a partial pass.

An empty document passes only after input validity and profile/worker availability checks succeed.
Unterminated comments and quoted tokens are syntax errors.
Reject NUL and invalid UTF-8 input as tool input errors before calling NUL-terminated native interfaces.
Do not silently truncate them.

## Diagnostic values

Each diagnostic contains `code`, `severity`, `message`, `span`, `rangePrecision`, and `category`.
Keep codes stable and messages descriptive.
Native message text may differ by release and is not a machine decision key.
Sort by document input order, span start, span end, then code.
Deduplicate only identical diagnostic values.

| Code | Category | Severity | Meaning |
| --- | --- | --- | --- |
| `CUBRID-S1001` | `syntax` | `error` | Parser-stage syntax rejection |
| `CUBRID-U1001` | `unsupported` | `warning` | Unknown or mismatched parser profile/version |
| `CUBRID-U1002` | `unsupported` | `warning` | Statement/script construct outside qualified coverage |
| `CUBRID-T1001` | `tool` | `error` | Worker/runtime unavailable |
| `CUBRID-T1002` | `tool` | `error` | Worker crash, timeout, bad response, or initialization failure |
| `CUBRID-T1003` | `tool` | `error` | Input/configuration/encoding/size failure |

Warnings for unsupported coverage still prevent a successful lint exit.
No semantic/style diagnostic category is enabled in v1.
Internal parser errors and catalog-dependent grammar failures cannot become ordinary syntax errors without a verified classification.
Use tool failure or unsupported coverage when appropriate.

## Native worker process interface

The production worker is a compiled executable with a narrow JSON-lines protocol.
It is not the planning experiment's direct ctypes loader.
Requests and responses use UTF-8 and include `protocolVersion: 1` and a request `id`.
One worker processes requests serially.
The client sends one outstanding request per worker.

`initialize` selects a qualified profile and returns native version, source commit, settings, platform, manifest digest, and supported statement kinds.
It also identifies the revision of the coverage predicates.
Reject profile/runtime/manifest mismatches before parsing.
`parse` accepts text and returns diagnostics, coverage decisions, and parsed statement kinds for admitted forms.
Apply conservative coverage predicates before traversing native grammar actions.
A native statement kind cannot distinguish a literal SELECT from a complex query.
Audit the full reachable parser path for each admitted subset or family.
Unknown forms return unsupported coverage without entering unaudited native paths.
Coverage classification never replaces native syntax checking.
`shutdown` closes the worker.
There is no execute, connect, catalog lookup, file-include, or shell operation.
The worker calls parser creation, parsing, error collection, and cleanup only, after controlled initialization.

Use an explicit runtime prefix and trusted executable path.
Do not find an arbitrary library through PATH or inherited library search settings.
Create private writable configuration/log/temp paths.
Ignore ambient CUBRID configuration and database registries.
The qualification manifest identifies the runtime dependencies and explicit syntax settings.
Native globals remain private to that worker.
Process separation is failure isolation, not an operating-system sandbox claim.

Set a default 5-second parse deadline, 8 MiB UTF-8 document limit, 16 MiB response limit, and 256-diagnostic limit.
Expose trusted configuration overrides with positive bounded validation.
If a diagnostic limit prevents a complete result, return `tool-error` with truncation stated explicitly.
Kill and reap only the worker owned by this client after timeout or cancellation.
Do not retry failed SQL silently.
Completion remains usable while the worker starts, parses, or fails.

## Schema snapshot

Editor v1 reads optional JSON with `schemaVersion: 1`, `user`, and `relations`.
Each relation contains `owner`, `name`, `kind`, and a list of column names.
`kind` is `CLASS` or `VCLASS` in the first contract.
Preserve optional top-level `users` and `database`, defaulting to an empty list and empty string.
Preserve optional relation fields `system` and `indexes`, defaulting to false and an empty list.
Validate their types and retain them when converting the integrated terminal schema.
Names preserve their spelling.
Unknown fields are ignored, but invalid required fields reject the snapshot.
Snapshots contain metadata only, never credentials or executable commands.

No snapshot means keyword completion and no invented relation names.
A failed refresh retains the last valid snapshot with an explicit stale message.
Initial load failure yields no schema and a visible availability message.
Reload on an explicit command or configuration change.
File watching is optional and must not cause an implicit database connection.
The existing terminal adapter continues its current live refresh behavior.

## CLI contract

Install the future commands `cubrid-lint` and `cubrid-language-server` with the Python package.
The server command requires the optional `lsp` dependencies.
If they are absent, it prints installation guidance to stderr and exits with a tool failure.

`cubrid-lint [--profile ID] [--script-mode sql|csql] [--format human|json] PATH...` checks explicit paths.
Support `--config PATH`, `--parser-worker PATH`, and `--runtime-prefix PATH` as explicit configuration overrides.
`-` reads stdin exactly once and can appear only once.
Do not recursively scan directories or expand globs inside the tool.
Default script mode is `csql` for `.csql` paths and `sql` for other paths or stdin.
An explicit mode overrides that default.
An EOF without a final semicolon is accepted if the selected native parser accepts it.
Source text is never submitted to CSQL.

Human output uses `path:line:column: severity code message` and a per-file status.
JSON stdout contains one object with `schemaVersion: 1`, `offsetEncoding: unicode-codepoints`, ordered document results, and the aggregate status.
Each document includes its path, selected profile, coverage, diagnostics, and status.
Each diagnostic's `span` contains numeric code-point `start` and `end` offsets.
Runtime logs go to stderr or private logs, never structured stdout.
An input failure still produces a document result in JSON mode.

| Exit | Meaning |
| --- | --- |
| 0 | Every input is fully checked and valid |
| 1 | Syntax errors exist and no tool error occurred |
| 2 | Unsupported coverage exists, with no syntax or tool error |
| 3 | Tool/input/configuration error, including invalid CLI arguments |

For mixed files, use priority 3, then 1, then 2, then 0.
Do not use an argument parser's default exit 2 for malformed arguments.
No `--ignore-unsupported` option exists in v1.

## Configuration and trust

Use optional project JSON `.cubrid-language.json` for profile, script mode, and schema snapshot path.
Initial default profile is `cubrid-11.5.0.2704-cc94778` after qualification.
Resolve relative snapshot paths against the configuration directory.
CLI precedence is explicit flags, explicit configuration, nearest ancestor configuration, then documented defaults.
For stdin, use the process working directory as the discovery origin.
Reject invalid configuration with `CUBRID-T1003`.
Editor language-server settings override project values per document.

Worker executable and runtime prefix come only from trusted user/editor settings or explicit CLI flags.
Project configuration cannot contain executable commands or credentials.
Use argv arrays and never invoke a shell to start the worker or server.
Do not install or download runtimes automatically.

## LSP contract

Use LSP 3.17 over stdio.
Use pygls for framing, JSON-RPC lifecycle, and protocol types.
Advertise only implemented features.
Initial document synchronization is full-text (`TextDocumentSyncKind.Full`).
Support initialize/initialized, didOpen/didChange/didClose, completion, shutdown/exit, and cancellation.
Add didChangeConfiguration with editor settings and the snapshot reload command.

Completion returns explicit `textEdit` ranges converted from core spans.
Diagnostics preserve core codes, severity, and document-version identity.
Debounce syntax checks by 250 ms initially.
Schedule native parsing outside the protocol event loop.
Discard results for superseded document versions.
Publish an empty list on close and cancel owned pending work.
Cancelled requests use the protocol's cancellation error.
Protocol stdout contains messages only.
Native stderr and server logs remain separate.

Missing runtime produces an availability/tool diagnostic while completion continues.
Untitled documents explicitly opened as `cubrid` can use keyword/snapshot completion.
They use SQL script mode unless the client supplies an explicit mode.
Do not activate the server for generic SQL language IDs.
Choose default script mode from the document URI using the CLI's filename rules.

These are project requirements based on the [LSP specification](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/).
The project does not claim support for every LSP feature.
