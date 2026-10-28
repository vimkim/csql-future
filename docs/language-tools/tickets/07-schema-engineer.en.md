# 07: Qualify schema and engineer commands

[한국어](07-schema-engineer.md) | **English**

> Historical planning archive: the independent [cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools) project supersedes this original monorepo plan. These are preserved records, not the current implementation dispatch instructions.

**What to build:** Engineers can check selected schema and CUBRID diagnostic/maintenance command syntax without running those commands.

**Blocked by:** 04.

**Status:** specified. Wait for verified blocker integration.

## Fresh-agent context

Read [spec](../spec.en.md), [contracts](../contracts.en.md), [execution](../execution.en.md), and reports 02–04.
Use the pinned source and manual to identify release-valid command spellings.
Planning baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
The coordinator supplies the exact dispatch baseline and blocker commits.

## Scope and ownership

Own schema/engineer coverage-family registry files and `tests/corpus/schema-engineer/`.
Qualify TABLE, VIEW, INDEX, SERIAL DDL and the spec's release-valid engineer command kinds.
Do not change terminal completion behavior or add stored-routine validation.
Do not execute DDL, tracing, statistics, configuration, or transaction text as an oracle.
Shared native-adapter changes require a coordinator-owned serialization slot.

## Acceptance criteria

- [ ] Every included native statement kind has source/manual evidence, valid/invalid/incomplete fixtures, and a grammar-action audit.
- [ ] Extend pre-parse feature predicates only for audited schema/command paths. Reject unknown forms before unaudited parsing.
- [ ] SHOW, DESCRIBE/DESC, EXPLAIN, EVALUATE, statistics, tracing, and transaction/settings forms are included only where the selected release supports them.
- [ ] Missing schema objects do not trigger a database lookup during syntax validation.
- [ ] `CREATE`/`ALTER`/`DROP` fixtures remain parser input only. Representative traces show no client execution or database access.
- [ ] Parser contextual/internal failures remain separate from ordinary syntax rejection.
- [ ] Unqualified object kinds or commands produce unsupported coverage instead of an unqualified pass.
- [ ] CLI and LSP agree on statuses, codes, and mapped spans, including Unicode identifiers.
- [ ] Add `just test-engineer-syntax`. Shared worker and vertical-slice checks remain green.

## Evidence and handoff

Commit scoped files and record audited productions, omissions, corpus verdicts, and commit in `reports/07.md`.
This contributes to ticket 11's release matrix.
