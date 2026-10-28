# 04: Prove completion and syntax diagnostics through LSP

[한국어](04-lsp-slice.md) | **English**

**What to build:** A protocol client receives shared completion and a CUBRID-specific serial diagnostic from one language server.

**Blocked by:** 01, 03.

**Status:** specified. Wait for verified blocker integration.

## Fresh-agent context

Read [spec](../spec.en.md), [contracts](../contracts.en.md), [execution](../execution.en.md), and blocker reports.
Read upstream pygls and LSP primary documentation before selecting tested dependency versions.
Planning baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
The coordinator supplies the exact dispatch baseline and blocker commits.

## Scope and ownership

Own `src/csql_future/lsp/`, protocol tests, and server usage documentation.
Add the `cubrid-language-server` entry point and optional `lsp` dependencies.
Serialize `pyproject.toml`, lockfile, and `justfile` changes with the coordinator.
Consume existing completion and validator interfaces.
Do not create editor-specific completion, broaden grammar coverage, or package editor clients yet.

## Acceptance criteria

- [ ] Complete initialize/open/full-change/completion/close/shutdown/exit protocol exchanges succeed over stdio.
- [ ] A valid serial produces no syntax error. Malformed serial produces the same core code/span through CLI and LSP.
- [ ] Unfinished relation/alias text still offers completion using a supplied test schema while native parsing rejects or lacks coverage.
- [ ] Completion text edits replace full token spans and preserve SQL after the cursor.
- [ ] Korean/emoji/CRLF locations agree after UTF-16 conversion. Advertised sync/encoding capabilities match implementation.
- [ ] Slow native parsing does not block completion. Cancellation, superseding changes, and close suppress stale diagnostics.
- [ ] Wrong-version, missing, timed-out, and crashed workers produce availability diagnostics without breaking keyword completion.
- [ ] Logs remain outside protocol stdout and server invocation never uses a shell.
- [ ] Add `just test-lsp` with a real subprocess protocol client. Add a vertical-slice check covering worker, core, CLI, and LSP.
- [ ] The optional dependency installation leaves the base wrapper's zero-dependency installation intact.

## Evidence and handoff

Commit scoped files and record the complete vertical-slice transcript, checks, dependencies, and commit in `reports/04.md`.
This is the gate before broader coverage or client packaging.
It unlocks tickets 05, 06, 07, and 08.
