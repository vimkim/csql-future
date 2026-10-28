# 08: Check mixed CSQL boundaries without session effects

[한국어](08-script-boundaries.md) | **English**

**What to build:** `.csql` scripts receive useful SQL diagnostics alongside a small checked session-command subset and explicit coverage gaps.

**Blocked by:** 04.

**Status:** specified. Wait for verified blocker integration.

## Fresh-agent context

Read [spec](../spec.en.md), [contracts](../contracts.en.md), [corpus](../corpus.json), [execution](../execution.en.md), and ticket 04's report.
Read CSQL's source/manual command recognition rules without invoking user scripts.
Planning baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
The coordinator supplies the exact dispatch baseline and blocker commits.

## Scope and ownership

Own `validation/scripts.py`, script fixtures/tests, and script-mode documentation.
Recognize session lines only at eligible CSQL line boundaries outside strings, quoted identifiers, and comments.
Preserve a source map when sending SQL portions to the native parser.
Qualify exact `;help`, `;exit`, and `;autocommit on/off` lines.
Other session commands, includes, shell commands, delimiter changes, and PL/CSQL bodies remain unsupported.
Do not implement session effects or include-file loading.

## Acceptance criteria

- [ ] Mixed valid command lines and supported SQL pass in CSQL mode with complete coverage.
- [ ] Supported commands with invalid arguments produce a stable syntax diagnostic.
- [ ] Strings/comments containing apparent commands or semicolons never create new session actions or false script boundaries.
- [ ] Same-line SQL statements, final EOF, CRLF, and leading whitespace retain original offsets.
- [ ] `;read` and shell-command fixtures produce unsupported diagnostics without opening targets or starting processes.
- [ ] PL/CSQL routines remain one unsupported region, even when their bodies contain semicolons. Do not lint their fragments as ordinary SQL.
- [ ] Mixed invalid SQL and unsupported regions preserve both diagnostics and use documented status/exit priority.
- [ ] Malformed or ambiguous script boundaries never become a complete valid result.
- [ ] SQL mode and CSQL mode differ explicitly. The server applies the per-document configured mode.
- [ ] Add `just test-script-boundaries` with CLI/LSP parity and no-effects checks.

## Evidence and handoff

Commit scoped files and record mapping checks, command evidence, limitations, and commit in `reports/08.md`.
This unlocks tickets 09 and 10 after ticket 05 also completes.
