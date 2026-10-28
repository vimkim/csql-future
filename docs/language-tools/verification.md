# Planning verification record

Baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
Date: 2026-10-28.
Only planning documents, starter fixtures, and a feasibility script changed.
Production source and existing tests remain unchanged.

| Check | Result | Limits |
| --- | --- | --- |
| Native parse-only experiment | Seven fixed expectations passed, plus unfinished-input completion | Linux `11.5.0.2704-cc94778` only |
| Traced final native run | No observed network calls or descendant executable; writable opens stayed in private temp paths | Network/execve/openat trace, not a full sandbox proof |
| First `just test` | 117 tests, one PTY error | Preserve this failed attempt |
| Focused failed-test rerun | One test passed | Does not explain the initial failure |
| Second `just test` | 117 tests passed in 45.070 seconds | Existing terminal/unit suite, not future language-tool acceptance |
| `just build` | Wheel and source distribution built successfully | Existing Python package only |
| Markdown source validation | Passed for all packet documents | Source validation, not rendered layout |
| Ticket graph/link check | Eleven nodes, no cycles, blocking text agrees, relative links exist | Dispatch still requires exact live baselines and external E01 resolution |
| Starter corpus JSON | Eleven unique requirement fixtures parsed successfully | Intended requirements, not full 11.5 qualification results |
| Diff whitespace check | Passed | No production implementation diff exists |

## Initial suite failure

The first `just test` ran 117 tests in 57.230 seconds.
`test_default_retention_keeps_latest_ten_thousand_and_deduplicates_recall` failed at `tests/test_editable_session.py:1211`.
It raised `IndexError` because the rendered screen lacked the expected `History search:` split marker.
The test uses a fixed 0.05-second read before inspecting that overlay.
This suggests timing sensitivity, but the cause was not established.
No production or test repair was made under this planning scope.

The focused command passed one test in 0.643 seconds:

```bash
uv run python -m unittest discover -s tests -p test_editable_session.py \
  -k test_default_retention_keeps_latest_ten_thousand_and_deduplicates_recall -v
```

The subsequent complete suite passed all 117 tests.
The local full rerun log is `/tmp/csql-language-plan-569-test-second.log`.
That temporary path is supporting evidence, not a portable project dependency.
Future agents must retain the initial failure in their baseline assessment.

## Document checks

The Markdown validator is the installed `markdown-write` skill's `scripts/check_markdown.py`.
The graph/link check parsed all ticket records and checked referenced document paths.
It also checked starter-corpus IDs and the retained native evidence.

A Mermaid syntax-check attempt returned dependency exit 2 because Python Playwright was unavailable.
No dependency installation was authorized or performed.
The final spec uses the module table and prose instead of a Mermaid diagram.
No Mermaid diagram remains in this packet, so no diagram-rendering claim is made.

## Qualification still required

The qualified 11.5 native worker, production lint CLI, LSP, and editor packages remain unimplemented.
Their acceptance commands are requirements listed in the tickets.
This planning suite cannot satisfy those future release gates.

The user selected 11.5 first during review.
All implementation targets now use the observed build's exact profile.
A research review also required conservative feature predicates before native parsing.
The revised contracts and ticket 02 include that requirement.

## Main advanced after the planning baseline checks

Another session integrated completion work 568 as `99d49e13698b609ff4885a418578f7f50485e82f` during this session.
The primary checkout is clean and its completion task worktree was removed by its owner.
Work item 568 reports a passing 130-test suite and real-CUBRID acceptance for that integration.
Those are the other session's results, not fresh checks performed by this planning session.
The 117-test results above belong to the planning branch's original `c292d00` baseline.
The approved rebase must include the newer completion behavior and run proportionate combined checks.
The contracts and snapshot ticket now preserve its added schema metadata.

## Approved rebase verification

The user approved the planning packet's integration and main push.
The two planning commits rebased onto `99d49e1` without conflicts.
Fresh combined checks passed all 130 tests in 45.692 seconds.
The log is `/tmp/csql-language-plan-569-integration-tests.log`.

The native experiment also passed all seven fixed expectations with the integrated completion module.
Unfinished-input completion still returned `id` and `name`.
The observed native library hash matches the original experiment.
The new run is `/tmp/csql-language-plan-569-integration-native.json`.

The eleven-ticket graph, blocking text, starter corpus, relative links, Markdown source, and instruction structural checks passed.
The diff against the integration destination contains only `docs/language-tools` files.
No production source or existing test changed in this planning packet.
