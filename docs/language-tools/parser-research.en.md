# Parser choices for shared CUBRID language tools

[한국어](parser-research.md) | **English**

Research snapshot: 2026-10-28. This note supplies design evidence. It does not certify a parser distribution or all CUBRID syntax. The planning session's native feasibility results are recorded separately.

Product decision after research: the user selected 11.5 first. The spec pins the observed `11.5.0.2704-cc94778` build for initial qualification. The 11.4 reference below remains comparison evidence, not the initial target.

## Recommendation

Use a version-pinned native CUBRID parser worker for authoritative SQL parsing, behind a small process interface. Keep the existing tolerant Python completion logic for unfinished input. Start editor coloring with a lexical grammar; introduce a CUBRID Tree-sitter grammar only when its editing value justifies maintaining another grammar. Completion and diagnostics can share one language server across Neovim and VS Code.

This recommendation is an inference from the evidence below and the coordinator's native feasibility probe. It avoids treating a permissive generic SQL parser as proof of CUBRID validity. It also preserves the current terminal package's dependency-free installation: parser workers and editor dependencies can be optional, separately installed tools. A missing worker must produce an explicit unavailable result, never a syntax pass.

The first qualification target should be one exact CUBRID release/build, not an unqualified “11.4+” or “11.5” dialect. The local develop source says 11.5.0; it does not prove 11.4 compatibility. The native probe's installed binary has its own identity and must be reported separately from the source checkout.

## Evidence identities and limits

| Evidence | Identity observed | What it establishes |
| --- | --- | --- |
| Local CUBRID source, read only | `/home/vimkim/gh/cb/develop`, commit `4ddf3b1550cae1ed82d65b5a9a6182912acd237f`; `VERSION` contains `11.5.0` | Source architecture at this commit |
| Local 11.4 release reference | `v11.4.6^{commit}` = `0e7d3c11e62ed8a4d354d0c951412f739e6be9ce`; `VERSION` contains `11.4.6` | A distinct release baseline is available; no runtime qualification was performed here |
| DerekStride SQL grammar | `987a64a7b105e267b39725a81ad2db628dc3178c` | Repository documentation and licensing snapshot |
| m-novikov SQL grammar | `587f30d184b058450be2a2330878210c5f33b3f9` | Repository documentation and licensing snapshot |
| SQLGlot | `tobymao/sqlglot`, `a32ef6365267049425dd93f45eb7af361466b854` | Documentation/dialect inventory snapshot |
| ANTLR grammar collection | `antlr/grammars-v4`, `70518282d3fd096b8577d0a03d925edf8b5f1c9c` | SQL directory inventory snapshot |

The local CUBRID checkout has unrelated changes. No research operation edited it. `git describe` finds a nearby 11.4 tag although `VERSION` is 11.5.0; use `VERSION` and exact commits rather than deriving the supported release from `git describe`. The annotated tag object `2c9fecc8df7e82f132f5c299c3ab0fdd37570f20` is not the peeled 11.4.6 source commit.

## Comparison

| Approach | CUBRID coverage and authority | Incomplete input | Offline and distribution | Maintenance and license |
| --- | --- | --- | --- | --- |
| Native CUBRID parser worker | Matches its pinned SQL parser, including CUBRID productions; parsing is distinct from catalog resolution and execution | Can reject an unfinished statement; unsuitable as the only completion strategy | Feasibility probe demonstrates database-free calls on one Linux build; deployment still needs its library, initialization and data dependencies | Track one native build at a time; internal ABI is not a stable external interface. Parser files carry Apache-2.0 headers |
| Purpose-built CUBRID Tree-sitter grammar | No qualifying upstream CUBRID grammar was found in this bounded search. A new grammar would need an explicit coverage map and native comparisons | Incremental recovery is a central strength | Generated C parser, runtime, language bindings and grammar distribution; native or WASM packaging can be lighter than a whole engine installation | A second dialect implementation must follow CUBRID releases. Tree-sitter runtime is MIT; grammar licensing is separate |
| Existing generic Tree-sitter SQL grammars | Useful editor starting points; neither inspected project claims strict CUBRID validation | Designed for editing and permissive recovery | Existing language packages and generated parsers reduce setup work | MIT for both inspected projects; a CUBRID fork would own dialect divergence |
| SQLGlot custom dialect | Built-in inventory has no CUBRID entry; a new custom dialect is possible. Upstream warns that successful parsing is not validation | Has structured parser errors, but not the documented incremental editing contract of Tree-sitter | Pure Python distribution is convenient; still adds a dependency to this project | MIT. Must implement CUBRID rules and account for upstream parser behavior/version changes |
| New ANTLR CUBRID SQL grammar | No CUBRID SQL directory in the inspected grammars-v4 inventory; an Oracle/MySQL grammar is not a CUBRID grammar | Error recovery available, but an editing strategy and latency need measurement | Java generator; multiple runtime targets including Python, JS/TS, C++. A runtime dependency remains | ANTLR tool/runtime BSD-3-Clause; each reused grammar has its own license. SQL grammar ownership remains substantial |

## Native parser evidence

The parser interface exposes create, parse-string and free operations. The string parser sets its input and calls `parser_main`; execution is not part of that direct function. The grammar and lexer are generated through Bison and Flex. This provides a plausible strict-parser adapter without constructing a new dialect grammar. It does not establish that arbitrary internal parser entry points are safe to call without correct initialization. [Parser declarations](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/parser/parser.h#L68-L85), [string parsing](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/parser/parse_tree_cl.c#L2008-L2063), [build generation](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/CMakeLists.txt#L304-L344).

The public `db_open_buffer` function checks that a database connection exists. Its local implementation calls the parser directly. Ordinary CSQL later calls compilation and execution. Therefore, invoking CSQL with a script or using the public session API is not an established offline syntax-only path. The direct internal parser route requires its own worker and proof. [Session API](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/compat/db_vdb.c#L1021-L1062), [CSQL compilation](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/executables/csql.c#L2275-L2297), [CSQL execution](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/executables/csql.c#L2346-L2355).

Native parsing uses process-global parser state and language settings. Grammar actions also inspect system parameters and can report contextual errors, such as collation/language errors. Serialize calls inside a worker; do not assume thread safety. Keep native failures separate from syntax rejection. A process interface also confines internal ABI differences. This isolation is a design inference, not an upstream public ABI promise. [Global parser state](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/parser/csql_grammar.y#L23912-L23930), [parameter-dependent grammar actions](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/parser/csql_grammar.y#L23842-L23860).

A native statement kind cannot distinguish literal SELECT from table queries, CTEs, or subqueries. A narrowed initial scope therefore needs conservative feature predicates before unaudited native parsing. Alternatively, qualify the entire reachable family before accepting it. This is a design requirement derived from the shared query grammar, not a claim that statement-kind inspection supplies a complete coverage test.

The native grammar and parser headers carry Apache-2.0 notices. The repository distinguishes engine licensing from connector licensing. A worker package must retain applicable notices and inventory bundled third-party libraries; the engine license alone does not describe every transitive dependency. [Parser header license](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/parser/parser.h#L1-L20), [repository license split](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/COPYING#L1-L19).

## Tree-sitter evidence

Tree-sitter builds incremental syntax trees and aims to remain useful when source contains errors. Its query documentation distinguishes `ERROR` nodes from inserted `MISSING` tokens; checking only `ERROR` nodes misses some recoveries. Even checking both establishes conformance only to the selected grammar, not to a CUBRID release. [Runtime goals](https://tree-sitter.github.io/tree-sitter/), [error and missing nodes](https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html#special-nodes), [runtime license](https://github.com/tree-sitter/tree-sitter/blob/master/LICENSE).

DerekStride's project describes a permissive general SQL grammar, supplies C/shared-library and language-package installation paths, and directs consumers to generated files on a separate branch. It is a candidate for editor exploration, with pinned revisions, not an authoritative CUBRID validator. [Pinned README](https://github.com/DerekStride/tree-sitter-sql/blob/987a64a7b105e267b39725a81ad2db628dc3178c/README.md), [MIT license](https://github.com/DerekStride/tree-sitter-sql/blob/987a64a7b105e267b39725a81ad2db628dc3178c/LICENSE).

m-novikov's grammar initially targets PostgreSQL and explicitly prioritizes lax parsing for editors. Reuse would require CUBRID coverage work, especially dialect-specific statements and script commands. [Pinned README](https://github.com/m-novikov/tree-sitter-sql/blob/587f30d184b058450be2a2330878210c5f33b3f9/README.md), [MIT license](https://github.com/m-novikov/tree-sitter-sql/blob/587f30d184b058450be2a2330878210c5f33b3f9/LICENSE).

Web searches for `CUBRID tree-sitter grammar github` and `"tree-sitter-cubrid"`, plus GitHub repository search `cubrid tree-sitter`, found no dedicated candidate; the GitHub API returned `total_count: 0`. These searches inspect indexed pages and repository metadata. They do not prove that no private, unindexed, or differently named grammar exists.

## SQLGlot and ANTLR evidence

SQLGlot's documented built-in dialect list omits CUBRID. Custom dialects and plugins are supported. Upstream explicitly warns that the parser accepts inputs an engine might reject. A custom dialect would need strict acceptance rules and a CUBRID corpus; choosing MySQL or the generic dialect cannot substitute for that work. [Dialect inventory](https://sqlglot.com/sqlglot/dialects.html), [custom dialect and leniency documentation](https://github.com/tobymao/sqlglot/blob/a32ef6365267049425dd93f45eb7af361466b854/README.md#faq), [MIT license](https://github.com/tobymao/sqlglot/blob/a32ef6365267049425dd93f45eb7af361466b854/LICENSE).

The inspected ANTLR grammar collection's SQL directory includes Oracle PL/SQL, MySQL, PostgreSQL and other dialects, but no CUBRID directory. ANTLR generates several target languages through a Java tool; its Python guidance requires matching generator/runtime versions. Reusing the tool is viable; a complete CUBRID SQL grammar is still a separate project. [Pinned SQL inventory](https://github.com/antlr/grammars-v4/tree/70518282d3fd096b8577d0a03d925edf8b5f1c9c/sql), [runtime targets](https://github.com/antlr/antlr4/blob/master/doc/targets.md), [Python version matching](https://github.com/antlr/antlr4/blob/master/doc/python-target.md), [tool/runtime license](https://github.com/antlr/antlr4/blob/master/LICENSE.txt).

CUBRID itself already has an ANTLR PL/CSQL grammar and `checkSyntaxAndGetStaticSqls`. The function parses one routine and returns embedded static SQL text with positions. However, the `static_sql` production accepts loose `SS_*` token sequences after the statement's initial keyword. This is useful future procedural-syntax evidence, not a complete SQL validator. The method is present in the local 11.4.6 source too. [Routine checker](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/pl_engine/pl_server/src/main/java/com/cubrid/plcsql/compiler/PlcsqlCompilerMain.java#L104-L125), [grammar entry](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/pl_engine/pl_server/src/main/antlr/PlcParser.g4#L33-L43), [static SQL production](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/pl_engine/pl_server/src/main/antlr/PlcParser.g4#L252-L265).

## Editor integration

One language server can deliver completion and diagnostics to multiple editors. VS Code's official guide separates its JavaScript/TypeScript client from a server that may use another language. Neovim has a built-in LSP client. These facts support retaining Python for the shared core while using thin editor adapters. They do not select an LSP framework or certify a particular client version. [VS Code language-server guide](https://code.visualstudio.com/api/language-extensions/language-server-extension-guide), [Neovim LSP documentation](https://neovim.io/doc/user/lsp.html).

## Qualification work still required

1. Retain the native probe's exact binary identity, setup and valid/invalid/incomplete observations. Qualify 11.4 separately if it is the initial product target.
2. Package a controlled native worker with explicit capabilities, no query execution calls, deadlines, crash handling and reproducible initialization. Test malformed input and multiple statements.
3. Measure error locations for UTF-8 Korean, non-BMP characters and CRLF before exposing editor ranges. Native line/column fields alone do not prove offset units.
4. Maintain distinct results for syntax rejection, unsupported language/version, native worker failure and optional semantic checks. Exclude PL/CSQL bodies and session-command execution until separately implemented.
5. Verify the actual runtime platform matrix. One Linux probe establishes no Windows/macOS binary support.

No parser package was installed and no SQL or CSQL script was executed by this research agent. No benchmark or corpus-conformance test was performed. The coordinator owns the separate feasibility experiment.
