# README visuals

The static SVGs use the editor's Catppuccin-inspired colors: background
`#1e1e2e`, text `#cdd6f4`, prompt `#cba6f7`, keys `#89b4fa`, and muted labels
`#a6adc8`. The title uses the SQL prompt and cursor as its visual motif.

`hero.svg` is a hand-authored vector title. `history.svg` and `completion.svg`
render text captured from the actual installed editor through the project's PTY
test harness. The history and `employees` catalog are illustrative fixtures;
no live database, user history, or credentials are used. Terminal text is kept
in order, with blank outer rows cropped and restrained highlighting applied.

Regenerate the captures from the repository root:

```bash
uv run python tests/capture_readme.py
```

Preview the SVGs at 900-pixel desktop and 360-pixel mobile widths. The README
also explains every demonstrated action in Markdown so scaled terminal text
is supplementary on small screens. The SVGs have no external fonts, scripts,
embedded raster images, or animation.

## Live demodb recording

`demodb-demo.gif` records the actual editor against CUBRID's populated sample
database in standalone mode. Its editable terminal source is `demodb-demo.cast`
(asciicast v2). It uses the same palette as the SVGs, DejaVu Sans Mono, an
88-column by 24-row terminal, and pauses at the completion menus.

The sequence is: launch `csql-future -S -u dba --no-pager demodb`; complete
`s` to `SELECT`; open the hint menu and filter with `PARA`; accept `PARALLEL`
and add `(2)`; complete `athlete` after `FROM`; return to the SELECT list and
complete `name` and `code`; execute with `LIMIT 3`; complete `;plan detail`;
quit with `;exit`. The query only reads sample data, and `;plan` changes a
session setting. A temporary directory keeps the recording's query history
separate from personal history.

To record again, load a CUBRID environment with `csql` on PATH and an existing,
populated `demodb` that is available for standalone access. Install this project
with `just sync`, install [agg](https://github.com/asciinema/agg), and make the
DejaVu Sans Mono font available. Then run from the repository root:

```bash
python3 tools/record_readme_demo.py
```

The script uses editor code from this checkout and fails if expected menus or
query results do not appear. It does not create a database or manage servers.
It overwrites only `demodb-demo.cast` and `demodb-demo.gif` in this directory;
use `--output-dir /tmp/csql-demo` to preview another recording.

To replay the captured session without a database, use:

```bash
asciinema play assets/readme/demodb-demo.cast
```
