# csql-with-history

`csql-with-history` is a Linux-first wrapper around the installed, unmodified
`csql` executable. Interactive terminal launches use a wrapper-owned multiline
editor and styled Catppuccin-inspired prompt. Noninteractive launches still
replace the wrapper process with csql so scripts retain csql's normal behavior.

## Runtime and installation

The launcher uses Python 3.10 or newer and only the standard library at runtime.
It uses the `csql` executable on `PATH`, so selecting a CUBRID work environment
also selects the underlying client. The wrapper installs independently of CUBRID.

```bash
just sync                         # uv tool install --reinstall .
csql-with-history --help
csql-with-history -u dba mydb
```

`uv tool install --reinstall .` installs an isolated tool environment and exposes
`csql-with-history` in `uv tool dir --bin` (normally `~/.local/bin`). That directory
must be on `PATH`. `just sync` can run from any working directory with
`just --justfile /path/to/csql-with-history/justfile sync`.
The installation remains usable after the source checkout moves or disappears.
`--help` and `--version` work without a CUBRID installation. Other arguments
pass through to csql; run `csql` directly for its native usage.

For development, run `uv sync`, `just test`, or
`uv run csql-with-history -u dba mydb`. `just build` creates wheel and source
archives in `dist/`.

### Nushell cs and daily updates

The personal `cs` alias in `~/my-cubrid/aliases.nu` calls `csql.sh`. The integration
in `my-cubrid` launches this tool after selecting the database, choosing SA/CS
mode, and checking the selected client's source tree against the running server.
Load your CUBRID environment and use `cs [DATABASE] [CSQL OPTIONS]` as before.
Direct `csql` remains available through the active CUBRID environment.

`daily-update-cubrid` registers `~/gh/csql-with-history` and runs `just sync`
after its guarded fetch and fast-forward. It requires an independent clean
checkout on `main` tracking `origin/main` from `vimkim/csql-with-history`.
Use `daily-update-cubrid --dry-run ~/gh/csql-with-history` to preview an update.

The accepted wrapper options are:

- `--history-file PATH`, defaulting to `.csql_history.sqlite3` in the launch
  directory. A relative path is resolved from that directory once.
- `--history-limit N`, defaulting to 10,000; `N` must be an integer.
- `--no-history`, which disables saving while retaining read-only recall from an
  existing selected history file.

Pipe input and csql's `-i`/`--input-file` and `-c`/`--command` forms go straight
to csql without creating or changing wrapper history. Process replacement
preserves csql's standard streams, redirections, signals, and exit status. The
parser recognizes csql options that take values so SQL, passwords, filenames,
and other values resembling wrapper options remain csql values. Use `--` to
stop all wrapper-option processing.

## Interactive input

Input starts immediately after `csql-with-history> ` on the same line. The
editor updates changed rows without clearing the display on each keypress;
cursor movement leaves unchanged text and the status bar in place. Ctrl+L
refreshes the editor. Layout follows the live terminal dimensions, including
after a resize, even when exported `COLUMNS` or `LINES` values are stale.

At the styled prompt:

- Enter submits the entire draft.
- Ctrl+J inserts a newline without submitting; Alt+Enter does the same.
- Left/Right move within the draft. Up/Down move between logical draft lines;
  at the first or last line they browse older/newer history. Moving newer than
  the latest entry restores the unfinished draft.
- Home, End, Backspace, and Delete edit the recalled or unfinished draft.
- Ctrl+R opens a temporary history search below the current draft. Search is
  case-insensitive and every space-separated term must occur somewhere in the
  complete command, including across embedded newlines. Up/Down selects a
  result, Enter recalls it for editing without execution, and Esc restores the
  draft and cursor from before the search.
- Ctrl+C clears an idle draft. In the history picker it closes the picker and
  clears the unfinished draft. Ctrl+D exits when the draft is empty.

Each draft line is handed to csql unchanged as one physical csql input line.
csql therefore remains responsible for SQL parsing, session commands, automatic
execution, its command buffer, and explicit `;xrun`. A draft containing embedded
newlines is one wrapper submission, while drafts submitted separately remain
separate even when csql accumulates them internally.

## Persistent history

Interactive submissions are appended to the selected SQLite file before they
are handed to csql. SQL that later fails and csql session commands are therefore
available after restart, and a multiline draft remains one entry with its
newlines intact. The wrapper stores separate submissions rather than attempting
to reconstruct csql's command buffer.

Up/Down recall presents identical complete command texts once, in latest-use
order, while repeated submissions remain separate stored records. Recall only
changes the editable draft; Enter is still required to submit it. A submission
whose first character is a space is not retained. `--no-history` neither appends
nor removes entries, but can browse an existing selected file.

Ctrl+R search uses the same deduplicated latest-use view. The picker is part of
the prompt rather than a full-screen interface: it keeps the unfinished draft
visible, marks one selected result, limits its result window to the available
terminal height, and reports an explicit no-match state. Long results are
truncated for display only; recalling them preserves their complete text.

The selected file is the history scope, independent of the database name or
connection target. The default hidden file isolates launch directories; an
explicit path can share history between them. Already-running wrappers refresh
committed shared entries when Up starts a new browse or Ctrl+R opens search.

Each saved submission is inserted and pruned in one short SQLite transaction,
so repeated submissions count toward retention even though recall and search
display identical command text once. The default keeps the latest 10,000 rows;
`--history-limit` sets the committing wrapper's limit.

Writers use WAL journal mode and a 300 ms busy timeout. WAL allows live readers
alongside a writer, while SQLite serializes writers; the `-wal` and `-shm`
sidecar files belong with the history file while sessions are live. This policy
is for same-host local filesystems. Network-filesystem sharing is neither
supported nor implied by the same-host tests because WAL depends on shared
memory between processes.

If live writers use different limits, every successful commit applies that
writer's configured limit to the shared file. Commit order therefore determines
the retained rows: a smaller-limit writer can prune rows permanently, while a
later larger-limit writer can retain new rows up to its limit but cannot restore
what was pruned. No persistent database-wide limit silently overrides either
invocation.

If the selected history file cannot be opened, read, or written, the wrapper
warns that persistent history is unavailable and that newly retained entries
will disappear on exit. The enhanced editor stays active in an explicit
`MEMORY-ONLY` mode: Up/Down recall and Ctrl+R search continue to use retained
current-session submissions, including multiline text and the same deduplicated
latest-use view. Leading-space and `--no-history` exclusions still apply.

Memory-only mode lasts until the wrapper exits. The wrapper closes the failed
SQLite connection and does not retry, reconnect after the destination becomes
available, or backfill volatile submissions. Restarting opens the selected
store afresh, so submissions committed before the failure remain available and
post-failure submissions do not appear. A history failure does not switch to
ordinary-csql fallback and does not prevent csql from executing the affected or
later submissions.

The wrapper removes its editor display before handing the terminal back to csql,
leaves csql result and error output in the transcript, and draws one current
prompt/status display when csql is ready again.

### SQL-input boundary

Interactive csql runs on a private pseudo-terminal. Readiness requires both:

1. the private csql prompt bytes, used only to remove csql's hidden transport
   prompt; and
2. the child pseudo-terminal's kernel line discipline being noncanonical with
   echo disabled, the mode libedit enters while it is actually reading SQL.

Neither a random prompt marker nor a period of silence is accepted by itself.
Consequently, query output that happens to contain the private prompt text is
relayed as output while csql is executing, and quiet work does not return input
ownership early. The current slices validate this connected SQL-input path and
capture only text returned by the wrapper editor as a submission. While csql has
a child attached to its pseudo-terminal, input, output, and the child line
discipline remain owned by that terminal program. This lets password input keep
csql's no-echo behavior and lets pagers, editors, and shells use the terminal
until they return. Linux `/proc` child information distinguishes a temporary
terminal program from libedit's otherwise identical raw/no-echo SQL-input mode.
The enhanced editor then resumes in the same csql session; this is not an
ordinary-csql fallback.

Only text returned by the wrapper editor is a wrapper submission. Thus `;edit`
may be retained, but text typed in the external editor, pager keystrokes, shell
commands, and password responses are neither reconstructed nor saved as separate
history entries.

The wrapper propagates every live terminal resize to csql's private terminal.
The enhanced editor redraws a long or multibyte draft immediately at the new
dimensions, and pagers, editors, and shells observe resizes while they own the
terminal. Returning from a terminal program redraws one prompt and status bar at
the current size without removing the program or query output from scrollback.

Ctrl+C typed while csql is running is relayed to csql's terminal rather than
handled as an editor command. A direct-versus-wrapped acceptance case interrupts
a three-way join of a 1,000-row physical table and successfully executes another
query in both sessions. This does not imply that every csql query phase cancels
immediately. The prototype's slow six-way `db_class` join is reproducible in the
production harness: both direct and wrapped csql emit a query plan, then fail to
return within a bounded five seconds after Ctrl+C. That places the observed wait
in query execution and demonstrates a direct-csql limitation, not wrapper-added
delay. The harness terminates both bounded probes and verifies cleanup instead
of waiting indefinitely or claiming universal cancellation.

SIGHUP and SIGTERM are forwarded to the csql process group. The wrapper restores
the complete outer terminal settings and exits with `128 + signal`; cleanup has
a one-second graceful bound followed by a process-group kill so csql cannot be
left waiting indefinitely for terminal input. Ordinary `;exit`, empty-draft
Ctrl+D, early csql error exits, and signal exits preserve the observed csql exit
status behavior.

The default shell is not replaced for wrapper convenience. csql selects
`CUBRID_CSQL_SHELL`, then `SHELL`, using its normal rules. The real-csql harness
runs that configured shell once through direct csql and once through the wrapper,
answers terminal cursor-position queries in both, and requires both paths to
execute a command and return. On the development host the configured Nushell at
`/home/linuxbrew/.linuxbrew/bin/nu` issued two cursor-position queries in each
path and returned successfully; its startup configuration diagnostics were
therefore treated as direct-csql behavior, not hidden by substituting `/bin/sh`.
Explicit ordinary-csql fallback for unsupported prompt states is delivered by a
later ticket and is not claimed here.

## Verification

The fast external-process suites use a synthetic csql executable, PTYs, an ANSI
screen model, and isolated temporary directories:

```bash
just test
```

The acceptance harness requires an initialized CUBRID runtime environment with
`csql` and `cubrid` on `PATH`. It creates two temporary standalone databases and a
temporary `CUBRID_DATABASES` registry. It also supplies a temporary CUBRID
runtime root so utility logs and other mutable runtime files stay isolated. The
harnesses compare noninteractive direct/wrapped calls and exercise editable
standalone and client/server sessions. They remove their resources on exit:

```bash
uv run python tests/verify_real_csql.py
uv run python tests/verify_editable_csql.py
```

The real-csql comparison covers pipe, file, command, successful SQL, failing SQL,
invalid csql options, wrapper-looking csql values, regular-file redirection,
redirected output, and history non-creation/non-modification. Only elapsed query
timing is normalized. The editable harness covers standalone and client/server
queries, errors followed by success, multiline submission, csql automatic and
explicit execution modes, session commands, prompt-looking output, quiet work,
and normal exit through the production PTY boundary. It additionally creates a
temporary password-authenticated user, verifies masked authentication and secret
exclusion, drives real `less`, `vi`, and `sh` processes through successful,
interrupted, nonzero, and missing-program returns, changes and executes csql's command buffer
through `vi`, and proves subsequent enhanced recall/search in the same session.
It resizes long multibyte drafts and live less, vi, and shell handoffs; the shell
checks its received dimensions and the returning editor checks its current
screen, result output, prompt, and status bar. It compares running-query Ctrl+C
directly with wrapped csql, verifies a successful later query, classifies the
bounded six-way catalog-query observation using plan output, and compares direct
and wrapped SIGTERM status, exact terminal settings, and process cleanup.
The configured default shell is compared with direct csql without overriding
the user's selection. The harness also validates SQLite
submission boundaries, restart recall and editing, draft restoration,
failed-command capture, leading-space exclusion, and read-only `--no-history`
against real csql. History search coverage includes multiline all-term matching,
cancellation, no-match safety, editable non-executing recall, deduplication,
latest-use order, and keyboard selection. The synthetic screen tests additionally
cover logical-line navigation and picker lifecycle in narrow and short terminals.
Shared-history coverage keeps two wrappers live across different launch
directories and database targets, checks browse and search refresh, runs
concurrent insert-and-prune work, validates configured and default retention
boundaries, confirms retained order through wrapper recall, and checks the actual
WAL journal mode and sidecars. Direct SQLite queries supplement the wrapper
observations with exact stored-row counts. Storage-failure coverage uses the
running wrapper with an unavailable destination and an actual SQLite writer
lock held beyond the busy timeout. It checks the warning and visible mode,
continued SQL execution and recall, the no-retry behavior after releasing the
lock, and the durable-versus-volatile boundary after restart.

## Prototype provenance

The separate throwaway prototype remains at
`/home/vimkim/gh/cb/csql-with-history-prototype`, branch
`prototype/csql-with-history`, inspected at commit `9394e38`. Its process-replace
bypass and comparison patterns informed this slice, but its Python packages,
PTY transport, SQLite layout, journal mode, and timeout choices are neither
runtime dependencies nor production requirements here.

## Extraction provenance and remaining work

This standalone project was extracted from `CUBRID/CUBRID` worktree
`/home/vimkim/gh/cb/csql-with-history`, branch `csql-with-history`, committed
revision `27fe60a090d6ceefcc815014270d8eee14c4556c` (2026-09-17).
Existing Apache-2.0 source notices and the license are preserved.
The original worktree's uncommitted ticket 09 implementation was not included.

This packaging task does not finish the original tickets 09–10: explicit
ordinary-csql fallback for unsupported prompt states and the complete integrated
production acceptance matrix remain pending in work-tracker item 172.
Tab completion is not implemented; Tab inserts a tab into the draft.
