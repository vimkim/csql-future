# Tab completion progress

Work item: **560**. Branch: `tab-completion`. Merge destination: `main`.

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
- [ ] **Integration.** After approval, rebase onto current `main`, run the
  affected checks, merge, push `main`, and clean up the task worktree and branch.

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
| Plan | `c4708bc` | Created this checklist and work item 560 from `main` at `0e95b34`. |
| 1 | `b1f8fea` | Added the menu, navigation, acceptance, cancellation, and terminal tests. |
| 2 | `72386bb` | Added SQL context, quotes, owners, scopes, and full identifier replacement. |
| 3 | `d94e05c` | Added background catalog loading, limits, cleanup, and connection routing. |
| 4 | `3a6844a` | Added the sequential standalone snapshot and authentication fallback. |
| 5 | `f315412` | Added cache verification, alias columns, refresh failure, and recovery. |
| 6 | Final acceptance commit | Added real CUBRID acceptance, reserved-word quoting, and documentation. |

Final review added expression-parenthesis handling and preserved indentation on
later draft lines. It also separated reserved-word quoting from keyword suggestions.
The final acceptance commit contains those changes and the tests for them.

The separate help/editor task advanced `main` to `77dd83b` during this work.
Its changes remain untouched. The task branch still starts from `0e95b34`.

## Verification log

| Check | Result |
| --- | --- |
| `just test` | Passed all 82 tests after the fixture correction below. |
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

Read work item 560 and inspect the branch and worktree status.
Finish acceptance if its checkbox remains open. Then request integration approval
under the supplied AGENTS.md Git workflow. After approval, rebase onto current
local `main`, preserve its help/editor changes, resolve conflicts, and repeat the
affected checks. Merge, push `main`, and clean up this task worktree and branch.
Record the final integration commit and verification in the tracker.
