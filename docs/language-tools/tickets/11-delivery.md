# 11: Check installation and the complete delivery matrix

**What to build:** Engineers and agents can install local artifacts and reproduce the documented terminal/editor/lint workflows on the qualified platform.

**Blocked by:** 06, 07, 09, 10.

**Status:** specified. Wait for verified blocker integration.

## Fresh-agent context

Read the complete [spec](../spec.md), [contracts](../contracts.md), [execution](../execution.md), graph, and all ticket reports.
Inspect current repository guidance, packaging, and CI before adding aggregate checks.
Planning baseline: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
The coordinator supplies the exact dispatch baseline and every integrated blocker commit.

## Scope and ownership

Own aggregate verification recipes/scripts, release-install documentation, and the final support/coverage matrix.
Update README and packaging metadata only as needed for the completed implementation.
Use disposable installation environments and local wheel/sdist/VSIX artifacts.
Preserve the existing user-level wrapper installation.
Do not publish packages/extensions, push branches, open PRs, or deploy under this ticket's authority.

## Acceptance criteria

- [ ] `just test`, `just build`, all native/core/CLI/LSP/corpus checks, and both headless editor checks pass on the combined integration tip.
- [ ] Add `just test-language` as a documented aggregate. Missing required release/runtime/editor prerequisites fail rather than silently skip.
- [ ] A clean base wheel install keeps the wrapper dependency-free. Optional LSP installation exposes the documented server with pinned compatible dependencies.
- [ ] Native worker build/install instructions reproduce the qualified pinned 11.5 profile and include runtime assets/notices.
- [ ] Built-artifact smoke checks cover stdin/path lint, all exits, CUBRID-specific syntax, and schema-aware completion through both clients.
- [ ] Shared corpus outcomes and converted diagnostic locations agree across core, CLI, LSP, Neovim, and VS Code.
- [ ] `.csql`, opted-in `.sql`, and unrelated `.sql` association checks all pass without global dialect changes.
- [ ] Record actual supported OS, architecture, Python, native profile, Neovim, VS Code, and dependency versions. Other platforms remain unqualified.
- [ ] Documentation distinguishes syntax coverage, unsupported constructs, catalog snapshots, semantic/style exclusions, and missing-runtime behavior.
- [ ] Run Standards and Spec review against the exact implementation baseline. Resolve findings and repeat affected checks.

## Evidence and handoff

Commit scoped files and record the final matrix, artifact paths/hashes, complete verdicts, review results, and commit in `reports/11.md`.
Report any remaining merge/publication gate separately from implementation completion.
The coordinator requests review of the committed result under the user's Git workflow.
