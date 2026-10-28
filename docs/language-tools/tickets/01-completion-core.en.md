# 01: Extract reusable completion without terminal regressions

[한국어](01-completion-core.md) | **English**

**What to build:** A pure completion caller can obtain the terminal's current suggestions and replacement spans. The terminal consumes that same module.

**Blocked by:** E01, reconciliation with concurrent completion work 568. No internal blockers.

**Status:** specified. Resolve E01 before dispatch.

## Fresh-agent context

Read [spec](../spec.en.md), [contracts](../contracts.en.md), and [execution](../execution.en.md).
Read the integrated completion, metadata, CLI, and completion/PTY tests.
Include `syntax.py`, `completion_data.py`, and `test_command_completion.py` from main commit `99d49e1`.
Planning baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
The coordinator supplies the exact dispatch baseline and the resolved work-568 commits.

## Scope and ownership

Own `src/csql_future/language/`, the compatibility surface in `completion.py`, and necessary imports in `cli.py` and `metadata.py`.
Include necessary import adjustments in `syntax.py` and `completion_data.py` without changing their recorded provenance.
Own focused additions in `tests/test_completion.py`, `tests/test_command_completion.py`, and a new `tests/test_language_core.py`.
Keep menu state in the terminal adapter.
Retain old imports through a compatibility adapter during migration.
Do not change catalog queries, history behavior, key bindings, native parsing, or editor clients.
Coordinate any `justfile` edit with the coordinator.

## Acceptance criteria

- [ ] A pure `complete` call implements the contracts without I/O and uses deterministic code-point replacement spans.
- [ ] All completion behavior integrated from work 568 remains covered, including any new schema types or command contexts.
- [ ] Existing `suggest`, schema value imports, and terminal menu acceptance continue to work.
- [ ] Incomplete SQL, quoted identifiers, owner shadowing, aliases, and token suffix replacement retain their results.
- [ ] Korean/emoji text before a replacement does not change the replacement target.
- [ ] Add `just test-language-core`. It checks the public completion interface and compatibility behavior.
- [ ] `just test` passes against the integrated baseline.

## Evidence and handoff

Commit only scoped files after reviewing the diff.
Record exact commands, counts, baseline, commit, unrelated dirt, and remaining limitations in `reports/01.md`.
This unlocks ticket 04 after ticket 03 also completes.
