[한국어](README.md) | **English**

<p align="center">
  <img src="assets/readme/hero.svg" width="100%" alt="csql-future: searchable history and schema-aware completion for CUBRID CSQL">
</p>

**Find your last query with Ctrl+R. Finish your next one with Tab.**

`csql-future` adds **searchable command history**, **CUBRID-specific completion**,
and multiline editing to your daily CSQL workflow. It runs your installed `csql`
with the database, user, and connection options you normally use.

[Get started](#get-started) · [Keyboard shortcuts](#keyboard-shortcuts) ·
[Usage guide](docs/usage.en.md) · [Documentation](docs/README.en.md) ·
[Internal introduction and demo](docs/internal-introduction.en.md)

## Watch a demodb session

<p align="center">
  <img src="assets/readme/demodb-demo.gif" width="100%" alt="Real demodb client/server session: complete SELECT, filter hints to PARALLEL, choose athlete from table names, move back to complete its columns, run the query, complete a session command, and quit">
</p>

Start with `s` + **Tab**, accept `SELECT`, then open hint completion with
`/*+` + **Tab** and type `PARA` to select `PARALLEL`. After `FROM` + **Tab**,
choose `athlete`, move back after the hint, and press **Tab** for its columns.
The recording runs the query, completes `;plan detail`, and quits with `;exit`.
This is the real editor and CUBRID sample database in client/server (`-C`) mode.
[Recording source and regeneration](assets/readme/README.en.md#live-demodb-recording).

## Ctrl+R: find the query instead of writing it again

Remember a table name and a condition? Press **Ctrl+R** and type those words.
For example, `employees active` finds queries containing both terms, regardless
of term order or case. Multiline SQL stays together in one result.

This gives you a fuzzy-search-style workflow based on remembered fragments.
The current matching rule requires **every space-separated term to occur as a
substring somewhere in the query**. It does not correct typos or skip characters
within a term.

<p align="center">
  <img src="assets/readme/history-demo.gif" width="100%" alt="Real demodb client/server history demo: run two athlete queries, browse them with Ctrl+R and Down, search for name to leave one matching query, recall with Enter, then press Enter again to run it">
</p>

The demo runs `select name from athlete limit 3;` and
`select code from athlete limit 3;`, then presses **Ctrl+R** and browses with
**Down**. Searching for `name` narrows the two entries to one matching query.
**Enter** recalls it into the editor.
A second Enter runs it. [Regenerate the history GIF](assets/readme/README.en.md#live-history-recording).

- **Survives restarts:** SQLite retains the latest 10,000 unique commands by default.
- **Less duplication:** submitting identical text updates its latest submission time.
- **Whole multiline queries:** recall the complete text for editing.
- **Visible age:** each result shows the time since its latest submission.

Enter recalls a search result **into the editor**. Edit it, then press Enter again to submit it.

## Tab: complete CUBRID commands and your actual schema

Completion covers SQL keywords, CUBRID inspection and diagnostic statements,
CSQL session commands, SQL comment hints, and real table and column names.

| Draft text | Example Tab candidates |
| --- | --- |
| `SHOW TA` | `TABLES` and other matching SHOW keywords |
| `SHOW CREATE ` | `TABLE`, `VIEW` |
| `;pl` / `;plan ` | `;plan` / `simple`, `detail`, `off` |
| `;sc` / `;schema emp` | `;schema` / accessible tables and views |
| `SELECT /*+ RE` | CUBRID hints such as `RECOMPILE`, `REEXECUTE` |
| `SELECT * FROM emp` | Accessible tables and views such as `employees` |
| `SELECT e.` with `FROM employees e;` later in the draft | Columns from that table |

**SHOW and diagnostic SQL:** complete statements such as `SHOW TABLES`,
`SHOW COLUMNS`, `SHOW INDEX`, `SHOW CREATE TABLE`, and `SHOW THREADS` in context.
Session commands such as `;plan`, `;trace`, `;schema`, `;get`, and `;set` also offer names and common arguments.

**SQL comment hints:** complete CUBRID hint names inside `/*+ ... */`, `--+`,
and `//+` comments. The current scope covers hint names. Enter table and index arguments inside parentheses yourself.

**Schema-aware names:** completion uses tables, views, and columns visible to
your connection user. It resolves simple aliases such as `e.` and reads text after the cursor, including a later FROM clause.

```sql
select <cursor> from employees;
```

With the cursor in the SELECT list, Tab offers columns from `employees`.
`<cursor>` marks the cursor position for this example.

<p align="center">
  <img src="assets/readme/completion.svg" width="100%" alt="Column completion: select e. from employees e offers department, id, and name from the demo schema">
</p>

Keep typing to filter the open list. Backspace broadens the matches again.
Use Up/Down to choose a candidate and **Enter** to insert it. SQL is submitted
after the list closes and you press Enter again. **Esc** keeps your current draft.

*The static completion image uses the actual editor with an illustrative
`employees` catalog from the test harness. [Regenerate the captures](assets/readme/README.en.md).*

<a id="get-started"></a>

## Get started

Requires Linux, Python **3.10+**, [uv](https://docs.astral.sh/uv/), and a CUBRID
environment with `csql` on `PATH`. There are no mandatory Python runtime dependencies.

```bash
uv tool install git+https://github.com/vimkim/csql-future.git
csqlf -u dba mydb
```

You can use either `csql-future` or its shortcut, `csqlf`. Both commands behave identically.
Use your normal CSQL connection options, including `-S` for standalone mode and
`-C` for client/server mode. `--help` and `--version` work without CUBRID installed.

To install from a checkout:

```bash
git clone https://github.com/vimkim/csql-future.git
cd csql-future
just sync
```

`just sync` installs `csql-future` and `csqlf` into uv's tool bin directory, normally
`~/.local/bin`. Keep that directory on `PATH`. The installed tool works
independently of the checkout.

<a id="keyboard-shortcuts"></a>

## Keyboard shortcuts

Defaults are shown below. [Customize shortcuts](docs/usage.en.md#customize-shortcuts)
with `~/.config/csql-future/keymap.json` or `--keymap PATH`.
Run `csql-future --print-keymap` to list every action and its default keys.

| Key | Action |
| --- | --- |
| **Ctrl+R** | Search saved commands with multiple terms |
| **Tab** | Open completion, or select the next candidate in an open list |
| **Up / Down** | Move between draft lines, browse history at the boundaries |
| **Ctrl+P / Ctrl+N** | Browse history or select a search/completion result |
| **Enter** | Accept a result, or submit the draft in Input mode |
| **Ctrl+J** | Insert a newline. Ctrl+Enter also works with a compatible terminal |
| **Ctrl+X Ctrl+E** | Open `$VISUAL`, `$EDITOR`, or `vi`, in that order |
| **F1** | Show help for the current mode |
| **Esc** | Close search/completion and keep the draft |
| **Ctrl+Q** | Quit from the editor, search, or help |

## Built for your daily CSQL workflow

- **Your existing client:** runs the installed `csql` with your chosen database and user.
- **Editable drafts:** multiline input, Unix editing keys, and an external editor.
- **History per task:** defaults to `./.csql_history.sqlite3` in the launch directory.
  Choose a shared path to use history across directories on the same host.
- **Native batch behavior:** pipes, input files, `-c`, and redirected launches pass through to `csql`, preserving output and exit status.

| Option | Purpose |
| --- | --- |
| `--history-file PATH` | Choose a SQLite history file |
| `--history-limit N` | Retain the latest N unique commands. Default: 10,000 |
| `--no-history` | Read existing history without saving new submissions |
| `--no-completion` | Skip metadata queries and keep literal Tab input |
| `--keymap PATH` | Load custom shortcuts from JSON |
| `--print-keymap` | Print every default action and key |

### Schema completion boundaries

In client/server mode, the first Tab loads metadata in the background.
Later requests refresh a cache older than 60 seconds. Submit
`;refresh-completions` to refresh immediately. A separate connection reads **committed schema** using the launch connection and user.

In standalone mode, metadata is read once before the interactive client starts.
Restart to see schema changes. Metadata reads use credentials supplied at launch.
A password entered later at CSQL's prompt cannot be reused. Editing and keyword completion remain available if metadata cannot be loaded.

Current schema completion excludes CTEs, derived-table columns, correlated outer
aliases, synonyms, and SQL held only in CSQL's internal command buffer.
Interactive support is Linux-first. See the [usage guide](docs/usage.en.md) for details and limits.

## Next: bring the same completion engine to editors

The separate [cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools) project
is building the shared engine for future terminal and editor integration.
The following features are **planned**.

| Stage | Goal |
| --- | --- |
| Shared completion engine + **LSP** | One language server sharing completion logic with the terminal |
| **Offline syntax checks / linting** | Report syntax errors through the CUBRID parser without executing SQL |
| **VS Code extension** | Completion, syntax diagnostics, highlighting, and basic indentation |
| **Neovim support** | Completion and diagnostics through the same LSP, plus highlighting |
| Later: **formatting** and more | A CUBRID SQL formatter, editor formatting integration, and Tree-sitter evaluation |

The first language-tool delivery starts with qualification of one CUBRID 11.5 build.
Formatting and semantic/style lint remain later goals. You can already use
Ctrl+X Ctrl+E with Neovim or another external editor. LSP integration is a separate planned feature.
See the [roadmap](docs/roadmap.en.md) and [shared engine project](https://github.com/vimkim/cubrid-language-tools).

## Try it with one query you use today

Connect with `csql-future`, submit a query, then find and edit it with Ctrl+R.
Try Tab after `SHOW `, `;`, a table prefix, and a column prefix.
Start with the queries you already find and revise every day.

Share the [internal introduction and demo](docs/internal-introduction.en.md), or
[report a reproducible issue or suggestion](https://github.com/vimkim/csql-future/issues).

## Development and verification

```bash
just test      # Unit and external-process PTY tests
just build     # Wheel and source distribution
```

See the [verification guide](docs/usage.en.md#verification) for real-CUBRID scripts
and environment requirements. The [completion checklist](docs/completion-plan.en.md) records implementation history.

## License

[Apache License 2.0](LICENSE). Original CUBRID copyright notices are preserved.
