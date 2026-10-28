# 06: Qualify queries and DML through CLI and LSP

**What to build:** Engineers and agents can check the selected release's query/DML syntax offline through the existing CLI and server.

**Blocked by:** 04.

**Status:** specified. Wait for verified blocker integration.

## Fresh-agent context

Read [spec](../spec.md), [contracts](../contracts.md), [research](../parser-research.md), [execution](../execution.md), and reports 02–04.
Consult the pinned 11.5 grammar and local manual for concrete syntax fixtures.
Planning baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
The coordinator supplies the exact dispatch baseline and blocker commits.

## Scope and ownership

Own a query/DML coverage-family registry file and `tests/corpus/query-dml/`.
Own its coverage audit and contract-level CLI/LSP regression checks.
Qualify SELECT, CTE/subquery, join/expression, INSERT, UPDATE, DELETE, and MERGE parser paths.
Reuse the native grammar. Do not implement a second grammar.
Do not add CTE result-column inference or other new completion semantics.
Shared native-adapter changes require a coordinator-owned serialization slot.

## Acceptance criteria

- [ ] Each included native statement kind has valid, invalid, and incomplete fixtures plus a recorded grammar-action audit.
- [ ] Extend pre-parse feature predicates only for audited query paths. Shared native kinds cannot bypass coverage restrictions.
- [ ] CUBRID-specific query expressions and quoted identifiers use source/manual-backed fixtures.
- [ ] Missing table/column names do not require a database or become syntax errors solely because they are absent.
- [ ] Nested expressions, CTEs, subqueries, comments, strings containing semicolons, and multiple statements preserve diagnostic source mapping.
- [ ] CLI and LSP produce equivalent statuses/codes and converted locations for the same corpus.
- [ ] Executing/catalog-dependent paths remain unsupported until their safe parser-only handling is proven.
- [ ] Supported production coverage is explicit. Fixtures alone do not imply all CUBRID releases are supported.
- [ ] Add `just test-query-syntax`, including representative no-connection/no-execution observations.
- [ ] Shared completion and initial vertical-slice checks remain green.

## Evidence and handoff

Commit scoped files and record grammar references, corpus verdicts, native identity, and commit in `reports/06.md`.
This contributes to ticket 11's release matrix.
