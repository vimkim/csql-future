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
- [ ] **6. Acceptance.** Verify navigation, replacement, terminal resizing,
  metadata failures, credentials, history boundaries, and real CUBRID behavior.
  Update the README and review the final diff.
- [ ] **Integration.** Commit all task changes. Request the required approval
  before rebasing and merging into `main`.

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

### Plan accepted

- Created work item 560 and a separate worktree from `main` at `0e95b34`.
- Preserved the separate help/editor task and the older fallback task.
- Menu implementation and focused PTY verification are complete.
- SQL context and full identifier replacement are complete.
- Client/server catalog loading and process cleanup are complete.
- Standalone snapshot ordering and authentication fallback are complete.
- Cache, alias/column completion, and failure recovery are complete.
- Next action: finish full regression and real CUBRID acceptance.

## Verification log

Step 1: two completion PTY tests passed. The existing indentation/editing test
passed after moving its literal Tab to an indentation position. The initial
full run passed 59 tests and exposed that obsolete Tab expectation.

## Resume

Read this checklist and work item 560. Inspect the current branch and status.
Continue the first unchecked implementation step. Record each result and its
verification before starting the next step.

Step 2: six SQL-context tests passed. Cases include relation positions, owners,
quotes, replacement suffixes, comments, strings, aliases, and nested scopes.

Step 3: catalog PTY tests passed. They verify asynchronous menu updates, cache
reuse, explicit refresh, responsive editing during a slow query, and process
cleanup on exit. All nine launch/bypass tests passed.

Step 4: standalone PTY tests passed. They prove the snapshot process exits
before input, live standalone refresh starts no client, and failed metadata
authentication preserves csql-owned password input and excludes secrets from history.

Step 5: cache reuse, forced refresh, retained names after refresh failure, and
later recovery passed terminal tests. Four metadata tests passed for escaping,
malformed output, owner identity, credentials, and connection-option routing.
Both standalone tests now pass after correcting status clipping and test
synchronization. A multiline completion/resize/history test also passed.
