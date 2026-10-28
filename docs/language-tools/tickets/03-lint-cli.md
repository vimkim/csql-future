# 03: Lint paths and stdin through the qualified parser

**What to build:** An AI agent can check serial/literal-query files or stdin offline and distinguish syntax, coverage, and tool outcomes.

**Blocked by:** 02.

**Status:** specified. Wait for verified blocker integration.

## Fresh-agent context

Read [contracts](../contracts.md), [spec](../spec.md), [execution](../execution.md), and ticket 02's report.
Read the [starter corpus](../corpus.json).
Planning baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
The coordinator supplies the exact dispatch baseline and worker qualification commit.

## Scope and ownership

Own `src/csql_future/lint.py`, lint/config tests, and CLI user documentation.
Add the `cubrid-lint` entry point with a serialized `pyproject.toml` edit.
Own project configuration parsing and explicit CLI overrides under `validation/`.
Do not broaden native syntax coverage beyond ticket 02.
Unknown CSQL commands and PL/CSQL must already yield unsupported coverage.
Do not add editor code, style rules, semantic checks, recursive file scans, or SQL execution.

## Acceptance criteria

- [ ] Path input, one stdin operand, multiple files, final EOF without newline, and human/JSON output satisfy the contracts.
- [ ] Valid/invalid serial and literal SELECT fixtures have the documented statuses and codes.
- [ ] Unicode/CRLF diagnostics preserve original source spans. JSON declares code-point offsets explicitly.
- [ ] Invalid UTF-8, NUL, unreadable input, invalid arguments/configuration, oversized input, and missing/crashing worker produce exit 3.
- [ ] Unsupported coverage produces exit 2. Syntax errors produce exit 1. Fully checked valid input produces exit 0.
- [ ] Mixed-file errors use priority 3, then 1, then 2, then 0, while retaining every document result.
- [ ] Private logs never contaminate JSON stdout. Default operation requests no database or credentials.
- [ ] `.csql` defaults to CSQL mode. Other files/stdin default to SQL mode. Explicit mode overrides work.
- [ ] Add `just test-lint` with external-process assertions against the installed entry point.
- [ ] `just build` succeeds and the built artifact includes the entry point and required profile resources.

## Evidence and handoff

Commit scoped files and record acceptance evidence, runtime identity, and commit in `reports/03.md`.
This unlocks ticket 04 after ticket 01 completes.
