# 02: Qualify the pinned 11.5 native parser worker

**What to build:** A caller can initialize an exact release profile and parse fixed SQL through a separate process without a database.

**Blocked by:** None.

**Status:** specified. Can start immediately under the implementation handoff.

## Fresh-agent context

Read [spec](../spec.md), [contracts](../contracts.md), [research](../parser-research.md), and [feasibility](../feasibility.md).
Read [execution](../execution.md) and the personal CUBRID policies before native builds.
Planning baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
The coordinator supplies the exact dispatch baseline.
The existing 11.5 experiment establishes feasibility but does not satisfy production qualification.

## Scope and ownership

Own a new `native/parser-worker/` build, qualification manifest, and notices.
Own `src/csql_future/validation/`, including document maps, diagnostics, profile checks, and worker adapter.
Own `tests/native_parser/` and worker/position tests.
Define an extensible coverage registry with separate family files for later tickets.
Include conservative feature predicates and apply them before unaudited native parsing.
Initial supported coverage is literal SELECT and CREATE SERIAL.
Do not modify CUBRID's shared source checkout or initialize a database.
Use a dedicated pinned-source worktree and `cubrid-build` instructions if a build is needed.
Coordinate `justfile` edits. Do not edit ticket 01's completion module.

## Acceptance criteria

- [ ] Qualify build `11.5.0.2704-cc94778` at source `cc947788d3b7dc402f46192d0f3299ddcc8563ba` with matching headers, library identity, platform, and runtime assets.
- [ ] Prove valid/invalid CREATE SERIAL, literal SELECT, incomplete input, empty input, and multiple statements through the JSON-lines process interface.
- [ ] Reject mismatched profiles/libraries and distinguish unavailable runtime, parser rejection, internal errors, and process failure.
- [ ] Check internal-error flags, ordinary error lists, and partial trees. Never infer success from a non-null tree alone.
- [ ] Audit executing/catalog-dependent grammar actions and syntax parameters for the initial coverage. Record explicit settings and private initialization paths.
- [ ] Coverage predicates distinguish literal SELECT from table queries, CTEs, and subqueries before parsing. Unknown forms remain unsupported.
- [ ] Korean/emoji/CRLF negative fixtures establish native coordinate units or trigger the documented statement-span fallback.
- [ ] Code-point/byte/UTF-16 conversion checks cover surrogate pairs, boundaries, EOF, and invalid positions.
- [ ] Native calls remain serialized and outside the caller's protocol event loop. Deadlines kill/reap only the owned worker.
- [ ] Trace representative parsing with no database connection, submitted-text execution, descendant client, or external writable configuration.
- [ ] Add documented `just build-native-parser` and `just test-native-parser` recipes with explicit source/runtime inputs. Missing mandatory prerequisites fail visibly.

## Evidence and handoff

If pinned-build reuse fails, retain the evidence and stop this ticket before asserting support.
Do not substitute another native build or create a new dialect parser without revising the spec.
Commit scoped work and record qualification, commands, identities, limitations, and commit in `reports/02.md`.
This unlocks ticket 03.
