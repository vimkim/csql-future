# Introducing csql-future to CUBRID colleagues

[한국어](internal-introduction.md) | **English**

## Copy for internal sharing

**Add Ctrl+R history search and CUBRID-specific Tab completion to your daily CSQL workflow.**

Do you scroll through terminal output for an earlier query or check table names
and SHOW syntax repeatedly? `csql-future` adds an editor in front of your
installed `csql`, helping you find and revise queries with your normal connection options.

**Use Ctrl+R to reuse a query.** Type remembered fragments, such as a table name
and a condition. Search ignores case and term order, and keeps multiline queries
together. Recall a result into the editor, revise it, and then submit it.
History survives restarts. Identical commands update their latest submission
time instead of adding duplicates. The fuzzy-search-style workflow uses substring matching: every search term must appear in the query.

**Use Tab for CUBRID-specific suggestions.** Complete SHOW statements such as
`SHOW TABLES`, `SHOW COLUMNS`, `SHOW INDEX`, and `SHOW THREADS`. Find session
commands and common arguments for `;plan`, `;trace`, and `;schema`.
CUBRID SQL hint names also complete inside `/*+ ... */`, `--+`, and `//+` comments.

**Complete names from your actual schema.** Suggestions include accessible
tables, views, and their columns. In a draft with `SELECT e.` followed by
`FROM employees e;`, Tab offers columns from `employees`. This can reduce trips to another screen just to check a name.

With Linux, Python 3.10+, uv, and a CUBRID environment, start with:

```bash
uv tool install git+https://github.com/vimkim/csql-future.git
csql-future -u dba mydb
```

Replace `mydb` with your database name. Use your existing CSQL options, including
`-S` for standalone or `-C` for client/server mode when needed.
Submit one familiar query, then find it again with Ctrl+R.

The plan is to use the separate `cubrid-language-tools` shared engine to extend
this experience through **LSP, a VS Code extension, and Neovim support**. Offline syntax checks and **syntax highlighting** come next,
with **CUBRID SQL formatting and editor formatting integration** as later goals.
These editor and language tools are roadmap items, separate from current installed features.

[Project and installation](../README.en.md) · [Usage](usage.en.md) ·
[Roadmap](roadmap.en.md) · [Issues and suggestions](https://github.com/vimkim/csql-future/issues)

## Short demo sequence

Preparation: connect to a test database you can query. Replace `employees` and
the example columns with real names. Suggestions depend on metadata visible to your user.

| Step | Demonstration | Message |
| --- | --- | --- |
| 1 | Start `csql-future` with your normal connection options | Keep your existing CSQL connection workflow. |
| 2 | Submit a multiline SELECT against a real table | The whole query becomes one history entry. |
| 3 | Press Ctrl+R and type the table name and another word | Narrow results regardless of case or term order. |
| 4 | Recall with Enter and change a condition | Edit a recalled result before submitting it. |
| 5 | Press Tab after `SHOW ` and `SHOW CREATE ` | Get contextual CUBRID SHOW suggestions. |
| 6 | Press Tab after `;pl`, then after `;plan ` | Discover session commands and common arguments. |
| 7 | Press Tab after `SELECT /*+ RE` | Complete CUBRID hint names. |
| 8 | Complete `SELECT * FROM emp` and a `SELECT e.` column position | Use real table/view names and columns from that table. |
| 9 | Exit, reconnect from the same directory, and press Ctrl+R | Keep history across sessions. |

Enter accepts a completion candidate. Press Enter after the menu closes to submit
the draft. After showing hint completion, finish the comment and SQL or clear
the draft with Ctrl+C. Ctrl+X Ctrl+E already supports an external editor.
Planned Neovim LSP support is a separate feature.

## Distinguish current features from plans

Current features are **history, Ctrl+R search, multiline editing, and
SHOW/session/hint/schema completion**. Search requires every term as a substring
and does not correct typos. Hint completion covers names. Enter parenthesized arguments yourself.

LSP, offline syntax checks, VS Code, Neovim, and highlighting belong to the
planned language-tool delivery. Formatting is a later goal. Do not present editor
extensions as part of the current installation. Check the [roadmap](roadmap.en.md) when preparing a presentation.
