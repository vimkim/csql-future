# 공통 CUBRID 언어 도구의 파서 선택 조사

**한국어** | [English](parser-research.en.md)

> 초기 계획 보존 기록: 독립 [cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools) 프로젝트가 기존 단일 저장소 계획을 대체합니다. 아래는 당시 기록이며 현재 구현 작업의 할당 지침이 아닙니다.

조사 시점: 2026-10-28. 이 문서는 설계 근거이며 파서 배포판·전체 CUBRID 문법을 인증하지 않습니다.
계획 세션의 네이티브 실험 결과는 별도로 기록했습니다.
조사 후 사용자는 11.5 우선을 선택했고 명세는 관찰한 `11.5.0.2704-cc94778`을 첫 검증 대상으로 고정했습니다.
아래 11.4 참조는 비교 근거이며 초기 대상이 아닙니다.

## 권고

작은 프로세스 인터페이스 뒤에 버전을 고정한 네이티브 CUBRID 파서 워커를 둡니다.
미완성 입력은 기존의 허용적인 Python 완성 로직으로 처리합니다.
초기 편집기 색상은 어휘 규칙으로 시작하고, 별도 문법 유지비를 정당화할 편집 이점이 있을 때 Tree-sitter를 도입합니다.
Neovim·VS Code는 언어 서버 하나의 완성·진단을 공유할 수 있습니다.

이 권고는 아래 근거와 조정자의 실험에서 도출한 추론입니다.
허용 범위가 넓은 일반 SQL 파서의 성공을 CUBRID 유효성 증거로 취급하지 않습니다.
워커·편집기 의존성을 선택적으로 별도 설치해 터미널 패키지의 필수 의존성 없는 설치도 유지합니다.
워커 부재는 명시적인 사용 불가이며 문법 통과가 아닙니다.

첫 대상은 포괄적인 “11.4+”·“11.5” 대신 정확한 릴리스·빌드여야 합니다.
로컬 develop 소스의 11.5.0 표기는 11.4 호환성을 입증하지 않습니다.
실험 바이너리의 식별값도 소스 체크아웃과 별도로 보고해야 합니다.

## 근거 식별값과 한계

| 근거 | 확인한 식별값 | 입증 범위 |
| --- | --- | --- |
| 읽기 전용 로컬 CUBRID 소스 | `/home/vimkim/gh/cb/develop`, `4ddf3b1550cae1ed82d65b5a9a6182912acd237f`, VERSION `11.5.0` | 해당 커밋의 구조 |
| 11.4 릴리스 참조 | `v11.4.6^{commit}` = `0e7d3c11e62ed8a4d354d0c951412f739e6be9ce`, VERSION `11.4.6` | 별도 릴리스 기준 존재. 런타임 검증 없음 |
| DerekStride SQL 문법 | `987a64a7b105e267b39725a81ad2db628dc3178c` | 문서·라이선스 스냅샷 |
| m-novikov SQL 문법 | `587f30d184b058450be2a2330878210c5f33b3f9` | 문서·라이선스 스냅샷 |
| SQLGlot | `tobymao/sqlglot`, `a32ef6365267049425dd93f45eb7af361466b854` | 문서·방언 목록 |
| ANTLR 문법 모음 | `antlr/grammars-v4`, `70518282d3fd096b8577d0a03d925edf8b5f1c9c` | SQL 디렉터리 목록 |

로컬 CUBRID의 무관한 변경을 수정하지 않았습니다.
`git describe`는 가까운 11.4 태그를 찾지만 VERSION은 11.5.0입니다.
지원 릴리스는 describe 대신 VERSION·정확한 커밋으로 식별합니다.
태그 객체 `2c9fecc8df7e82f132f5c299c3ab0fdd37570f20`은 실제 11.4.6 소스 커밋과 다릅니다.

## 비교

| 방법 | CUBRID 지원·권위 | 미완성 입력 | 오프라인·배포 | 유지보수·라이선스 |
| --- | --- | --- | --- | --- |
| 네이티브 파서 워커 | 고정 CUBRID 문법에 일치. 파싱은 카탈로그 해석·실행과 별개 | 미완성 문장을 거부할 수 있어 단독 완성 전략에는 부적합 | Linux 한 빌드에서 DB 없는 호출 확인. 라이브러리·초기화·자료 의존성 필요 | 빌드별 추적. 내부 ABI는 안정된 외부 인터페이스가 아님. 파서 파일 Apache-2.0 |
| 새 CUBRID Tree-sitter 문법 | 제한된 조사에서 검증 가능한 업스트림 없음. 범위 맵·네이티브 비교 필요 | 증분 복구가 강점 | 생성 C 파서·런타임·바인딩 필요. native/WASM 배포는 전체 엔진보다 가벼울 수 있음 | 두 번째 방언 구현을 릴리스별 관리. 런타임 MIT, 문법 라이선스 별도 |
| 기존 일반 Tree-sitter SQL 문법 | 편집기 출발점. 조사한 두 프로젝트 모두 엄격한 CUBRID 검증을 주장하지 않음 | 편집·허용적 복구 목적 | 기존 패키지·생성 파서로 준비 감소 | 두 프로젝트 MIT. fork는 CUBRID 차이를 직접 관리 |
| SQLGlot 사용자 방언 | 기본 목록에 CUBRID 없음. 사용자 방언 가능하나 파싱 성공이 검증은 아님 | 구조화된 오류. Tree-sitter식 증분 편집 계약은 아님 | 순수 Python 배포가 편하지만 의존성 추가 | MIT. CUBRID 규칙과 업스트림 버전 변화 관리 필요 |
| 새 ANTLR CUBRID SQL 문법 | 조사 목록에 CUBRID 없음. Oracle/MySQL 문법은 대체 불가 | 오류 복구 가능. 편집 전략·지연 측정 필요 | Java 생성기와 여러 타깃. 런타임 의존성 존재 | 도구·런타임 BSD-3-Clause, 재사용 문법 라이선스 별도. SQL 문법 소유 비용 큼 |

## 네이티브 파서 근거

파서는 생성·문자열 파싱·해제를 노출합니다. 문자열 파서는 입력 설정 후 `parser_main`을 호출하며 직접 실행하지 않습니다.
Bison·Flex로 문법·lexer를 생성합니다. 새 방언 없이 엄격한 파서를 재사용할 경로지만 올바른 초기화 없는 내부 진입점 호출의 안전성까지 입증하지 않습니다.
[선언](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/parser/parser.h#L68-L85),
[문자열 파싱](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/parser/parse_tree_cl.c#L2008-L2063),
[빌드 생성](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/CMakeLists.txt#L304-L344).

공개 `db_open_buffer`는 DB 연결을 확인하며 내부 구현은 파서를 직접 호출합니다.
일반 CSQL은 이후 컴파일·실행합니다. CSQL 스크립트 실행이나 공개 세션 API가 오프라인 문법 전용 경로인 것은 아닙니다.
직접 내부 파서 경로에는 별도 워커·검증이 필요합니다.
[세션 API](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/compat/db_vdb.c#L1021-L1062),
[컴파일](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/executables/csql.c#L2275-L2297),
[실행](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/executables/csql.c#L2346-L2355).

네이티브 파싱은 프로세스 전역 상태·언어 설정을 사용합니다.
grammar action은 시스템 파라미터를 읽고 collation·언어 등 문맥 오류도 낼 수 있습니다.
워커 내부 호출을 직렬화하고 thread-safe라고 가정하지 않습니다. 네이티브 실패를 문법 거부와 구분합니다.
프로세스 인터페이스로 내부 ABI 차이를 격리한다는 것은 설계 추론이며 업스트림 공개 ABI 약속이 아닙니다.
[전역 상태](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/parser/csql_grammar.y#L23912-L23930),
[파라미터 의존 action](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/parser/csql_grammar.y#L23842-L23860).

문장 종류만으로 리터럴 SELECT와 테이블 쿼리·CTE·서브쿼리를 구분하지 못합니다.
초기 범위를 좁히려면 파싱 전에 보수적 구문 조건을 두거나 도달 가능한 계열 전체를 검증해야 합니다.
이는 공유 쿼리 문법에서 도출한 요구사항이며 종류 검사만으로 범위 판정이 완성된다는 주장이 아닙니다.

파서 문법·헤더에는 Apache-2.0 고지가 있습니다. 저장소는 엔진·커넥터 라이선스를 구분합니다.
워커 배포에는 관련 고지와 포함한 제3자 라이브러리 목록이 필요합니다. 엔진 라이선스만으로 전이 의존성을 설명하지 못합니다.
[헤더 고지](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/src/parser/parser.h#L1-L20),
[라이선스 구분](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/COPYING#L1-L19).

## Tree-sitter 근거

Tree-sitter는 오류가 있는 본문에서도 유용한 증분 트리를 목표로 합니다.
`ERROR` 노드와 삽입된 `MISSING` 토큰을 구분하므로 ERROR만 검사하면 복구 일부를 놓칩니다.
둘 다 검사해도 선택한 문법의 적합성일 뿐 CUBRID 릴리스 적합성은 아닙니다.
[목표](https://tree-sitter.github.io/tree-sitter/),
[오류·누락 노드](https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html#special-nodes),
[런타임 MIT](https://github.com/tree-sitter/tree-sitter/blob/master/LICENSE).

DerekStride 프로젝트는 허용적인 일반 SQL 문법이며 C·공유 라이브러리·언어 패키지 설치와 별도 생성 파일 브랜치를 안내합니다.
고정 버전의 편집기 탐색 후보이지 CUBRID 검증 기준은 아닙니다.
[README](https://github.com/DerekStride/tree-sitter-sql/blob/987a64a7b105e267b39725a81ad2db628dc3178c/README.md),
[MIT](https://github.com/DerekStride/tree-sitter-sql/blob/987a64a7b105e267b39725a81ad2db628dc3178c/LICENSE).
m-novikov 문법은 PostgreSQL부터 시작하며 편집기용 느슨한 파싱을 우선합니다.
CUBRID 전용 문장·스크립트 지원은 별도 작업입니다.
[README](https://github.com/m-novikov/tree-sitter-sql/blob/587f30d184b058450be2a2330878210c5f33b3f9/README.md),
[MIT](https://github.com/m-novikov/tree-sitter-sql/blob/587f30d184b058450be2a2330878210c5f33b3f9/LICENSE).

당시 `CUBRID tree-sitter grammar github`, `"tree-sitter-cubrid"` 검색과
GitHub 저장소 `cubrid tree-sitter` 검색에서 전용 후보를 찾지 못했고 API는 `total_count: 0`이었습니다.
색인·메타데이터 조사일 뿐 비공개·미색인·다른 이름의 문법 부재를 증명하지 않습니다.

## SQLGlot·ANTLR 근거

SQLGlot의 기본 목록에는 CUBRID가 없습니다. 사용자 방언·플러그인은 가능하지만 엔진이 거부할 입력도 파서가 허용할 수 있습니다.
엄격한 규칙·CUBRID 코퍼스가 필요하며 MySQL·일반 방언 선택으로 대신할 수 없습니다.
[방언 목록](https://sqlglot.com/sqlglot/dialects.html),
[사용자 방언·허용성](https://github.com/tobymao/sqlglot/blob/a32ef6365267049425dd93f45eb7af361466b854/README.md#faq),
[MIT](https://github.com/tobymao/sqlglot/blob/a32ef6365267049425dd93f45eb7af361466b854/LICENSE).

조사한 ANTLR SQL 목록은 Oracle PL/SQL·MySQL·PostgreSQL 등을 포함하지만 CUBRID는 없습니다.
Java 생성기의 여러 타깃과 Python generator/runtime 버전 일치가 필요합니다.
도구 재사용은 가능해도 전체 CUBRID SQL 문법은 별도 프로젝트입니다.
[목록](https://github.com/antlr/grammars-v4/tree/70518282d3fd096b8577d0a03d925edf8b5f1c9c/sql),
[타깃](https://github.com/antlr/antlr4/blob/master/doc/targets.md),
[Python 버전](https://github.com/antlr/antlr4/blob/master/doc/python-target.md),
[라이선스](https://github.com/antlr/antlr4/blob/master/LICENSE.txt).

CUBRID에는 ANTLR PL/CSQL 문법과 `checkSyntaxAndGetStaticSqls`가 있습니다.
루틴 하나를 파싱하고 내장 static SQL과 위치를 반환합니다.
그러나 `static_sql`은 첫 키워드 뒤 느슨한 `SS_*` 토큰을 허용하므로 전체 SQL 검증기는 아닙니다.
로컬 11.4.6에도 이 메서드가 있습니다. 향후 절차 문법의 근거로 사용할 수 있습니다.
[루틴 검사](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/pl_engine/pl_server/src/main/java/com/cubrid/plcsql/compiler/PlcsqlCompilerMain.java#L104-L125),
[진입 문법](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/pl_engine/pl_server/src/main/antlr/PlcParser.g4#L33-L43),
[static SQL](https://github.com/CUBRID/cubrid/blob/4ddf3b1550cae1ed82d65b5a9a6182912acd237f/pl_engine/pl_server/src/main/antlr/PlcParser.g4#L252-L265).

## 편집기 연동

언어 서버 하나로 여러 편집기에 완성·진단을 제공할 수 있습니다.
VS Code는 JS/TS 클라이언트와 다른 언어의 서버를 분리하고 Neovim은 내장 LSP를 제공합니다.
이는 Python 코어·얇은 어댑터 설계 근거이며 특정 프레임워크·클라이언트 버전 인증은 아닙니다.
[VS Code](https://code.visualstudio.com/api/language-extensions/language-server-extension-guide),
[Neovim](https://neovim.io/doc/user/lsp.html).

## 남은 검증

1. 네이티브 실험의 정확한 바이너리·설정·정상/오류/미완성 결과를 보존합니다. 11.4를 대상으로 삼는다면 별도 검증합니다.
2. 명시적 기능·기한·충돌 처리·재현 가능한 초기화를 갖는 비실행 워커를 패키징합니다. 잘못된 입력·여러 문장을 검사합니다.
3. 편집기 범위 공개 전에 한글 UTF-8·비BMP·CRLF 오류 위치를 측정합니다. 네이티브 행·열만으로 단위를 알 수 없습니다.
4. 문법 거부·미지원 언어/버전·워커 실패·선택적 의미 검사를 구분합니다. 별도 구현 전 PL/CSQL·세션 실행은 제외합니다.
5. 실제 플랫폼 행렬을 검증합니다. Linux 실험 하나로 Windows·macOS를 입증하지 못합니다.

이 조사 에이전트는 파서 패키지 설치·SQL/CSQL 실행·벤치마크·코퍼스 적합성 검사를 수행하지 않았습니다.
별도 실현 가능성 실험은 조정자가 담당했습니다.
