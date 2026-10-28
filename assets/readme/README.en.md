# README visuals

[한국어](README.md) | **English**

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
is supplementary on small screens. The assets have no external fonts, scripts,
embedded raster images, or animation.
