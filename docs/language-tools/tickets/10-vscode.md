# 10: Deliver configurable VS Code extension

**What to build:** VS Code users install a local VSIX that shares completion/diagnostics with Neovim and supplies CUBRID lexical highlighting.

**Blocked by:** 05, 08.

**Status:** specified. Wait for verified blocker integration.

## Fresh-agent context

Read [spec](../spec.md), [contracts](../contracts.md), [execution](../execution.md), and blocker reports.
Use the official extension, language-server, and TextMate guides before selecting supported dependency versions.
Planning baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
The coordinator supplies the exact dispatch baseline and blocker commits.

## Scope and ownership

Own `editors/vscode/`, its package lock, tests, and installation guide.
Use language ID `cubrid`, TypeScript, a pinned `vscode-languageclient`, and a user-installed Python server argv.
Provide TextMate rules and basic language configuration for highlighting/comments/brackets/indentation.
Default `.csql` association is configurable. Use workspace/user `files.associations` for `.sql` opt-in.
Do not claim generic SQL documents or publish to a marketplace.

## Acceptance criteria

- [ ] Default `.csql` activation and explicit `.sql` association produce shared completion and serial diagnostics.
- [ ] An unrelated SQL document does not start this language client. Explicit user language associations remain effective.
- [ ] Schema snapshot settings/reload, unsaved `cubrid` documents, replacements, Unicode ranges, and document closure match server contracts.
- [ ] The extension uses trusted server/runtime settings and argv arrays. Project data cannot execute an arbitrary command.
- [ ] Missing server/dependencies/runtime produce actionable availability feedback without corrupting document text.
- [ ] TextMate fixtures cover keywords, comments, strings, identifiers, and CSQL command lines.
- [ ] Pin a tested VS Code engine/client version pair and document Linux extension-host scope, including remote Linux use.
- [ ] Add reproducible dependency installation, headless extension-host checks, and `just package-vscode` producing a local VSIX.
- [ ] No visible GUI, browser auto-opening, package publication, or database connection occurs during checks.

## Evidence and handoff

Commit scoped files and record test/packaging commands, actual versions, VSIX location, and commit in `reports/10.md`.
This contributes to ticket 11.
