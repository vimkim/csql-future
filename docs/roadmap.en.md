# Current features and roadmap

[한국어](roadmap.md) | **English**

`csql-future` starts with better input and history search in the terminal.
The shared engine, lint CLI, and LSP belong to the separate
[cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools) project.
VS Code and Neovim clients already use that LSP. This terminal still uses its own completion engine.

This document separates current terminal features, independent products, and remaining work.
The [initial language-tool plans](language-tools/README.en.md) are historical records.

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

## Separate language tools available now

| Project | Current role |
| --- | --- |
| [cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools) | Shared completion core, `cubrid-lint` offline checks, `cubrid-language-server`, and optional schema snapshots |
| [cubrid-vscode](https://github.com/vimkim/cubrid-vscode) | Shared LSP completion and diagnostics, highlighting, basic indentation, and file associations |
| [cubrid.nvim](https://github.com/vimkim/cubrid.nvim) | The same LSP completion and diagnostics, highlighting, basic indentation, and file associations |

These products have separate installation instructions. Installing `csql-future`
installs neither `cubrid-lint` nor `cubrid-language-server` or the editor clients.
The clients use a separately installed server. Strict syntax checks also need a qualified native worker.

Current native qualification covers the exact CUBRID **11.5.0.2704-cc94778** build
on Linux x86-64 and a bounded syntax subset. See the core project's
[current coverage](https://github.com/vimkim/cubrid-language-tools/blob/main/docs/coverage.en.md)
and [installation guide](https://github.com/vimkim/cubrid-language-tools/blob/main/docs/install.en.md)
for supported constructs and matching core, worker, and manifest requirements.
Other builds, versions, and platforms require separate qualification.

The shared checker reports syntax results and authoring warnings without executing
submitted SQL or CSQL commands. It does not check object existence, privileges,
execution results, or semantic/style rules. These checks are separate from terminal
completion. SHOW and hint suggestions do not establish native syntax support.

## Remaining terminal integration

Migration from this terminal's completion engine to the shared core remains planned.
The terminal owns completion menus, history, PTY handling, and SQL execution.
Ctrl+X Ctrl+E already opens an external editor. LSP features in that editor require
the separate editor client and server configuration.

## Later goals

- **CUBRID SQL formatting:** connect SQL formatting to editor formatting actions. Formatting is not implemented.
- **Richer highlighting:** evaluate Tree-sitter after initial Vim syntax and TextMate rules.
- **Broader completion and validation:** consider CTE/derived results, PL/CSQL, semantic/style lint, and live editor catalogs.
- **More environments:** qualify additional CUBRID builds, versions, and operating systems separately.

These goals do not promise release dates. See the [shared engine roadmap](https://github.com/vimkim/cubrid-language-tools/blob/main/docs/product-roadmap.en.md) for current priorities.
