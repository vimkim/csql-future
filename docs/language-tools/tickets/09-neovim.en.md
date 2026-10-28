# 09: Deliver configurable Neovim integration

[한국어](09-neovim.md) | **English**

> Historical planning archive: the independent [cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools) project supersedes this original monorepo plan. These are preserved records, not the current implementation dispatch instructions.

**What to build:** Neovim users get shared completion/diagnostics and basic CUBRID highlighting/indentation for selected files.

**Blocked by:** 05, 08.

**Status:** specified. Wait for verified blocker integration.

## Fresh-agent context

Read [spec](../spec.en.md), [contracts](../contracts.en.md), [execution](../execution.en.md), and blocker reports.
Use current primary Neovim documentation for its built-in client APIs.
Planning baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
The coordinator supplies the exact dispatch baseline and blocker commits.

## Scope and ownership

Own `editors/neovim/`, its headless tests, and its installation/configuration guide.
Use filetype `cubrid`, a user-configured server argv, built-in LSP, Vim syntax rules, and conservative indentation.
Default `.csql` association is configurable. `.sql` requires explicit patterns or a local filetype choice.
Do not implement a Tree-sitter grammar or a second completion engine.
Do not change the VS Code client or Python server except through separately coordinated defect fixes.

## Acceptance criteria

- [ ] A default `.csql` buffer starts the server and receives shared completion plus serial diagnostics.
- [ ] An opted-in `.sql` buffer behaves the same. An unrelated `.sql` buffer keeps its prior SQL filetype/client behavior.
- [ ] Users can disable default associations and configure per-project patterns without global dialect takeover.
- [ ] Snapshot schema completion, explicit replacements, Unicode locations, document changes, and close cleanup match protocol fixtures.
- [ ] Lexical rules distinguish keywords, strings, comments, identifiers, and eligible session commands. Basic indentation preserves continuation blocks without claiming full parsing.
- [ ] A missing native worker leaves completion and highlighting available with explicit diagnostic availability information.
- [ ] Add `just test-neovim` using headless processes and fresh configurations. Test Neovim 0.11+ APIs without deprecated setup calls.
- [ ] Document installation, server/runtime prerequisites, association examples, and observed version limits.

## Evidence and handoff

Commit scoped files and record headless transcripts, actual Neovim versions, fixture parity, and commit in `reports/09.md`.
This contributes to ticket 11.
