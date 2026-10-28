# Current features and roadmap

[한국어](roadmap.md) | **English**

`csql-future` starts with better input and history search in the terminal.
The direction is a shared CUBRID language engine that brings the same completion to multiple editors.

This document separates available features from planned work. Design tickets
and proposed commands are implementation requirements. They do not establish installation availability or complete CUBRID syntax support.

## Available now

| Feature | Usage and scope |
| --- | --- |
| Persistent command history | Latest 10,000 unique commands by default, deduplication, submission ages, multiline text |
| Ctrl+R search | Every space-separated term must occur in the query, regardless of case or term order |
| CUBRID SHOW completion | Contextual keywords and objects for inspection and diagnostic statements |
| CSQL session completion | Names and common arguments for `;plan`, `;trace`, `;schema`, and more |
| SQL comment hint completion | Hint names inside `/*+ ... */`, `--+`, and `//+`, excluding argument completion |
| Schema-aware completion | Accessible tables/views, their columns, simple aliases, and supported index/user/catalog contexts |
| Multiline and external editing | Ctrl+J for a newline, Ctrl+X Ctrl+E for `$VISUAL` or `$EDITOR` |
| Native batch execution | Pipes, input files, `-c`, and redirections pass through to native `csql` |

Search supports a fuzzy-search-style workflow. It does not correct typos or skip
characters within a term. Hint names use a CUBRID 11.5 source snapshot.
Suggestions do not replace server syntax or privilege checks.
See the [README](../README.en.md) and [usage guide](usage.en.md) for installation and limits.

## Planned language-tool delivery

| Item | Intended behavior |
| --- | --- |
| Shared completion core | Consistent context, identifier, and alias handling across terminal and editors |
| LSP language server | Completion and syntax diagnostics for editor documents |
| Offline syntax checks / lint CLI | Check with a qualified CUBRID parser without SQL execution or database connections |
| Schema snapshots | Table and column completion from metadata JSON in editors |
| VS Code extension | Completion, syntax diagnostics, highlighting, basic indentation, file associations |
| Neovim integration | The same LSP completion/diagnostics, highlighting, indentation, file associations |

The initial qualification target is Linux x86-64 and CUBRID
**11.5.0.2704-cc94778**. A small fixed experiment demonstrated parsing without a
database on that build. The production worker, syntax coverage, editor packaging,
and integrated acceptance require separate work. Other 11.5 builds and 11.4 support require their own qualification.

The initial lint scope is **syntax diagnostics**. It does not establish table
existence, privileges, execution results, or semantic/style checks.
`cubrid-lint` and `cubrid-language-server` are proposed command names.
Do not present them as installed features of the current terminal package.

## Later goals

- **CUBRID SQL formatting:** connect SQL formatting to editor formatting actions. This is outside the first language-tool delivery.
- **Richer highlighting:** evaluate Tree-sitter after initial Vim syntax and TextMate rules.
- **Broader completion and validation:** consider CTE/derived results, PL/CSQL, semantic/style lint, and live editor catalogs.
- **More environments:** qualify additional CUBRID builds, versions, and operating systems separately.

These goals do not promise release dates. See the [language-tool design](language-tools/README.en.md) for interfaces and implementation order.
