# Tab completion progress

Work item: **560**. Branch: `tab-completion`. Merge destination: `main`.

The approved plan keeps the current editor and adds schema completion through
the installed `csql`. No new Python runtime dependency is required.

## Checklist

- [ ] **1. Completion menu.** Add Tab, Ctrl+N/P, Enter, and Esc handling.
  Enter accepts a candidate without submitting SQL. Other modes retain their keys.
- [ ] **2. SQL context.** Detect table positions in unfinished SQL. Replace the
  identifier at the cursor. Respect comments, strings, owners, and quoted names.
- [ ] **3. Catalog provider.** Fetch accessible tables and columns through a
  bounded background `csql` process in client/server mode. Parse plain output.
- [ ] **4. Standalone snapshot.** Fetch metadata before the standalone client
  starts. Close the metadata client before starting the interactive client.
  Do not capture password keystrokes or query a second client during standalone use.
- [ ] **5. Cache and columns.** Cache metadata per session. Refresh client/server
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
- Next action: implement the menu with fixed candidates, then verify its keys.

## Verification log

No implementation checks have run yet.

## Resume

Read this checklist and work item 560. Inspect the current branch and status.
Continue the first unchecked implementation step. Record each result and its
verification before starting the next step.
