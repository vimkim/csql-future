# Native parser feasibility experiment

[한국어](feasibility.md) | **English**

Question: can a CUBRID parser distinguish valid, invalid, and incomplete text without executing a SQL script?

Result: **yes for seven fixed fixtures on the identified Linux 11.5 development build**.
The [JSON observations](evidence/native-probe.json) and [syscall summary](evidence/native-probe-trace.json) retain the evidence.
This result selects an implementation direction, not a production compatibility claim.

## Exact environment

| Item | Observed value |
| --- | --- |
| Native version returned by library | `11.5.0.2704-cc94778` |
| Matching source commit | `cc947788d3b7dc402f46192d0f3299ddcc8563ba` |
| Loaded library | `/home/vimkim/gh/cb/develop/build_preset_debug_gcc/cs/libcubridcs.so.11.5` |
| Library SHA-256 | `56eb36e9a46e3b6f5258974b25085b81d1679430618041343e4d979704822b33` |
| Runtime locale/message prefix | `/home/vimkim/.cub/install/develop/debug` |
| Current source checkout HEAD | `4ddf3b1550cae1ed82d65b5a9a6182912acd237f`, distinct from the binary |
| Native entry point | `parser_parse_string_with_escapes(parser, text, false)` |
| Charset/language | Explicit `en_US.utf8` |
| Database | None opened, created, or registered |

The script uses ctypes only as an experiment.
The production design uses a compiled worker and a qualified runtime manifest.
The script's `--source-commit` value records the matching build identity supplied by the operator.
The binary's own returned version and digest provide independent observations.
This experiment does not verify the provenance of every runtime dependency.

## Observations

| Fixture | Observed native result |
| --- | --- |
| `CREATE SERIAL order_no START WITH 10 INCREMENT BY 2;` | Tree returned, no parser errors |
| `CREATE SERIAL order_no START WITH ;` | No tree, syntax error |
| `SELECT e. FROM employees e;` | No tree, parser error |
| Missing table/column names in a SELECT | Tree returned, no parser errors |
| Korean text, emoji, and CRLF | Tree returned, no parser errors |
| Two SQL statements | Tree returned, no parser errors |
| `DROP TABLE must_never_be_executed;` | Tree returned, no parser errors |

The existing completion function returned `id` and `name` at the unfinished `e.` cursor.
It did so even though the strict parser rejected that document.
The missing-table case shows why parser acceptance differs from catalog validation.
The DROP fixture was text for the parser, not an executed statement.

The final traced run performed no network syscalls.
It launched no client or descendant executable.
Its writable file opens stayed in the experiment's private temporary area.
The trace covered network, execve, and openat operations for these fixtures only.
It is not a complete syscall sandbox or an audit of all native grammar actions.

## Reproduce on this host

Run from the repository root:

```bash
timeout 20s strace -f -e trace=network,execve,openat \
  -o /tmp/cubrid-language-probe-569.strace \
  python -B docs/language-tools/experiments/native_parser_probe.py \
  --library /home/vimkim/gh/cb/develop/build_preset_debug_gcc/cs/libcubridcs.so.11.5 \
  --prefix /home/vimkim/.cub/install/develop/debug \
  --source-commit cc947788d3b7dc402f46192d0f3299ddcc8563ba
```

The command prints JSON and returns 0 when every fixed expectation holds.
It uses temporary configuration, registry, log, and working-directory paths.
It initializes errors, locales, charset, messages, and default parameters.
It then creates, parses, inspects, and frees parser contexts serially.
It never calls a connection, compilation, or execution function.

The command depends on the exact available library and compatible runtime assets.
On another machine, supply equivalent verified inputs and record their identities.
Do not install this experiment as the lint command.

## Earlier attempts and corrections

The first exploratory call initialized built-in locales without setting the active charset.
The debug library aborted at a `lang_charset()` assertion.
The corrected sequence calls `lang_init()` and `lang_set_charset_lang()` explicitly.
The final script disables core dumps and bounds CPU time.

An earlier trace also showed that a relative error-log name resolved under the existing installation's log directory.
The final script passes an absolute private log path.
The retained trace confirms that correction.
The earlier probe log was preserved; no existing installation was rebuilt or reconfigured.

## Remaining qualification gates

1. Qualify a production worker for this exact 11.5 build before product support.
2. Audit qualified grammar actions for executing or catalog-dependent behavior.
3. Pin syntax-affecting parameters instead of inheriting user configuration.
4. Check internal-error flags as well as ordinary parser error lists.
5. Measure native error coordinate units with invalid Korean/emoji/CRLF fixtures.
6. Verify partial trees, empty input, multiple errors, crashes, deadlines, and malformed requests.
7. Package the worker and enumerate runtime assets and license notices.
8. Enforce coverage predicates before parsing unaudited forms. Native statement kinds alone cannot enforce the literal-SELECT subset.

The positive Unicode fixture does not prove diagnostic-coordinate correctness.
The small corpus does not establish all statement families.
These gates belong to implementation tickets, not unstated completed work.
The user selected 11.5 first after reviewing the planning direction.
Other 11.5 builds and 11.4 remain separate qualification work.

The matching source exposes the parser operations and keeps SQL compilation/execution in later CSQL stages.
See [native parser implementation](https://github.com/CUBRID/cubrid/blob/cc947788d3b7dc402f46192d0f3299ddcc8563ba/src/parser/parse_tree_cl.c), [parser declarations](https://github.com/CUBRID/cubrid/blob/cc947788d3b7dc402f46192d0f3299ddcc8563ba/src/parser/parser.h), and [CSQL execution](https://github.com/CUBRID/cubrid/blob/cc947788d3b7dc402f46192d0f3299ddcc8563ba/src/executables/csql.c).
