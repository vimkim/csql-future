# 05: Load offline schema snapshots in editor sessions

**What to build:** An editor session obtains schema-aware completion from a configured local metadata snapshot without connecting to CUBRID.

**Blocked by:** 04.

**Status:** specified. Wait for verified blocker integration.

## Fresh-agent context

Read the schema/configuration contracts, [spec](../spec.md), [execution](../execution.md), and ticket 04's report.
Read the existing immutable schema values and terminal catalog lifecycle tests.
Planning baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
The coordinator supplies the exact dispatch baseline and blocker commit.

## Scope and ownership

Own `src/csql_future/language/snapshots.py`, snapshot fixtures/tests, and snapshot user documentation.
Own the necessary LSP schema-setting/reload integration.
Provide a small valid metadata example and a documented conversion example from the current terminal schema value.
Do not change terminal live-query lifecycle, add automatic live editor connections, or add semantic lint.
Coordinate edits to shared LSP configuration handlers.

## Acceptance criteria

- [ ] Schema v1 snapshots produce relation, owner, alias-column, and quoted-name suggestions through the core and LSP.
- [ ] No snapshot produces keyword completion and no invented catalog names.
- [ ] Initial invalid/missing snapshots produce a visible availability message. Failed reloads retain the previous valid snapshot as stale.
- [ ] An explicit reload or per-document configuration change updates completion without editing the document.
- [ ] Relative paths and configuration precedence match the contracts. Snapshots contain no credentials or commands.
- [ ] Syntax validation and its exit status do not depend on the snapshot's presence or contents.
- [ ] Add `just test-schema-snapshots`. Retain the terminal metadata and PTY regression verdicts.

## Evidence and handoff

Commit scoped files and record commands, observations, and commit in `reports/05.md`.
This unlocks tickets 09 and 10 after ticket 08 also completes.
