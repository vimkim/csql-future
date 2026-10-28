# Tab completion progress

[한국어](completion-plan.md) | **English**

Work item: **560**. Branch: `tab-completion`. Merge destination: `main`.

This is the initial implementation record. See the [roadmap](roadmap.en.md) and
[usage guide](usage.en.md) for current features, including later system catalog support.

The approved plan keeps the current editor and adds schema completion through
the installed `csql`. No new Python runtime dependency is required.

## Checklist

- [x] **1. Completion menu.** Add Tab, Ctrl+N/P, Enter, and Esc handling.
  Enter accepts a candidate without submitting SQL. Other modes retain their keys.
- [x] **2. SQL context.** Detect table positions in unfinished SQL. Replace the
  identifier at the cursor. Respect comments, strings, owners, and quoted names.
- [x] **3. Catalog provider.** Fetch accessible tables and columns through a
  bounded background `csql` process in client/server mode. Parse plain output.
- [x] **4. Standalone snapshot.** Fetch metadata before the standalone client
  starts. Close the metadata client before starting the interactive client.
  Do not capture password keystrokes or query a second client during standalone use.
- [x] **5. Cache and columns.** Cache metadata per session. Refresh client/server
  metadata on expiry or request. Resolve simple aliases and column positions.
- [x] **6. Acceptance.** Verify navigation, replacement, terminal resizing,
  metadata failures, credentials, history boundaries, and real CUBRID behavior.
  Update the README and review the final diff.
- [x] **Integration preparation.** Continued with user approval. Rebased onto
  current `main` and preserved the newer help/editor and history-age features.
  Work item 560 records the final merge, push, cleanup, and verification result.

## Behavior

Tab opens a list of prefix matches. Ctrl+N/P and Down/Up select a candidate.
Enter accepts the candidate. Esc restores the draft. Enter submits SQL only
after the menu closes. Ctrl+N/P browse history when the menu is closed.

Table and view names come from `db_class`. Column names come from `db_attribute`.
The provider uses the selected database and user. Catalog queries stay outside
the interactive client's SQL buffer and wrapper history.

Client/server refresh sees committed metadata through a separate connection.
Standalone completion uses an initial snapshot, which can become stale.
Metadata failure leaves SQL editing and execution available.

## Progress log

| Step | Commit | Result |
| --- | --- | --- |
| Plan | `2e247c9` | Created this checklist and work item 560 from `main` at `0e95b34`. |
| 1 | `9737b1b` | Added the menu, navigation, acceptance, cancellation, and terminal tests. |
| 2 | `0810c07` | Added SQL context, quotes, owners, scopes, and full identifier replacement. |
| 3 | `bf79f13` | Added background catalog loading, limits, cleanup, and connection routing. |
| 4 | `b3ee15e` | Added the sequential standalone snapshot and authentication fallback. |
| 5 | `fcec592` | Added cache verification, alias columns, refresh failure, and recovery. |
| 6 | `7dc9b79` | Added real CUBRID acceptance, reserved-word quoting, and documentation. |

Final review added expression-parenthesis handling and preserved indentation on
later draft lines. It also separated reserved-word quoting from keyword suggestions.
The final acceptance commit contains those changes and the tests for them.

Separate help/editor and history-age work advanced `main` to `428ec9f` during
implementation. The user authorized continuation after acceptance. The rebase
preserves both features. Completion now has its own F1 help. External draft
editing remains available while the completion menu is open.

## Verification log

| Check | Result |
| --- | --- |
| `just test` | Passed 82 tests before rebase, 101 after rebase, and all 102 after integration adaptation. |
| `uv run python tests/verify_completion_csql.py` | Passed against CUBRID 11.5.0. |
| `uv run python tests/verify_real_csql.py` | Passed the native bypass comparison matrix. |
| `uv build` | Built wheel and source distribution. |
| Wheel contents | Confirmed the launcher, completion, and metadata modules. |

Real acceptance covers standalone and client/server table and column completion.
It checks non-executing acceptance, exact history entries, restricted-user catalog
visibility, and refresh after committed DDL. Each run uses temporary databases.

Focused checks cover malformed catalog output, escaping, credential routing,
quotes, owners, aliases, scopes, replacement suffixes, cancellation, and no matches.
Terminal checks cover multiline drafts, resizing, search, timeout, process cleanup,
failed refreshes, recovery, and disabled completion.

Earlier runs exposed an obsolete literal-Tab expectation, clipped status text,
and test synchronization problems. Those checks passed after correction.
A later full run exposed an existing synthetic PID-file race. The fixture now
publishes its PID file with an atomic rename. Its focused termination test passed.

## Limits

- Standalone metadata is a startup snapshot. Restart the wrapper to refresh it.
- Metadata reads use explicit launch credentials. They cannot reuse a password
  entered at the interactive prompt. Lookup failure leaves keyword completion.
- Client/server metadata uses a separate connection and sees committed schema.
  Restart after changing the interactive connection target or user.
- CTEs, derived-table columns, correlated outer aliases, synonyms, system tables,
  and fragments held only in csql's command buffer are outside this first version.
- Reserved-word quoting uses a CUBRID 11.5 snapshot.

## Resume

Read work item 560 before resuming. Implementation and integration approval are
complete. If the tracker remains open, inspect the branch and worktree status.
Finish the approved fast-forward merge, `main` push, and task cleanup after checks.
Preserve newer destination changes if `main` advances. Record final evidence in
the tracker. If the tracker is done, do not repeat integration.
