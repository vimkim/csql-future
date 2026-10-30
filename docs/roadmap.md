# 현재 기능과 로드맵

**한국어** | [English](roadmap.en.md)

`csql-future`는 CSQL의 일상적인 입력·검색을 개선하는 터미널 도구에서 출발합니다.
공통 엔진·린트 CLI·LSP는 별도 [cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools)에서 관리합니다.
VS Code·Neovim 클라이언트는 이미 이 LSP를 사용합니다. 이 터미널은 여전히 자체 완성 엔진을 사용합니다.

이 문서는 현재 터미널 기능, 독립 제품, 남은 작업을 구분합니다.
[초기 언어 도구 계획](language-tools/README.md)은 과거 기록입니다.

## 지금 사용할 수 있는 기능

| 기능 | 사용 방법과 범위 |
| --- | --- |
| 영구 명령 히스토리 | 기본 최근 고유 명령 10,000개. 중복 제거, 제출 시각, 여러 줄 보존 |
| Ctrl+R 검색 | 공백으로 나눈 검색어를 모두 포함하는 쿼리 검색. 순서·대소문자 무관 |
| CUBRID SHOW 완성 | 조회·진단 문장의 다음 키워드와 문맥에 맞는 객체 후보 |
| CSQL 세션 명령 완성 | `;plan`, `;trace`, `;schema` 등 명령 이름과 주요 인자 |
| SQL 주석 힌트 완성 | `/*+ ... */`, `--+`, `//+` 안의 힌트 이름. 인자 완성은 제외 |
| 스키마 기반 완성 | 접근 가능한 테이블·뷰, 해당 컬럼, 단순 별칭, 일부 인덱스·사용자·카탈로그 문맥 |
| 여러 줄·외부 편집기 | Ctrl+J로 줄바꿈, Ctrl+X Ctrl+E로 `$VISUAL` 또는 `$EDITOR` 실행 |
| 기존 배치 실행 | 파이프·입력 파일·`-c`·리다이렉션을 네이티브 `csql`로 전달 |

검색은 퍼지 검색 스타일의 사용 흐름을 제공하지만, 오타 보정이나 검색어 내부의 문자 건너뛰기 매칭은 지원하지 않습니다.
힌트 이름은 CUBRID 11.5 소스 스냅샷을 사용합니다. 완성 후보 제공은 서버의 문법·권한 검사를 대신하지 않습니다.
설치와 상세 제약은 [README](../README.md)와 [사용 가이드](usage.md)를 참고하세요.

## 현재 제공하는 별도 언어 도구

| 프로젝트 | 현재 역할 |
| --- | --- |
| [cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools) | 공통 완성 코어, 오프라인 검사 `cubrid-lint`, `cubrid-language-server`, 선택적 스키마 스냅샷 |
| [cubrid-vscode](https://github.com/vimkim/cubrid-vscode) | 공통 LSP의 완성·진단, 구문 강조, 기본 들여쓰기, 파일 연결 |
| [cubrid.nvim](https://github.com/vimkim/cubrid.nvim) | 같은 LSP의 완성·진단, 구문 강조, 기본 들여쓰기, 파일 연결 |

이 제품들은 각각 설치 안내를 제공합니다. `csql-future`를 설치해도
`cubrid-lint`, `cubrid-language-server`, 편집기 클라이언트는 설치되지 않습니다.
클라이언트는 별도로 설치한 서버를 사용합니다. 엄격한 문법 검사에는 검증된 네이티브 워커도 필요합니다.

현재 네이티브 검증 대상은 Linux x86-64의 정확한 CUBRID **11.5.0.2704-cc94778** 빌드이며,
문법 지원은 한정된 부분집합입니다. 지원 구문과 코어·워커·매니페스트의 일치 조건은 코어 프로젝트의
[현재 지원 범위](https://github.com/vimkim/cubrid-language-tools/blob/main/docs/coverage.md)와
[설치 가이드](https://github.com/vimkim/cubrid-language-tools/blob/main/docs/install.md)를 확인하세요.
다른 빌드·버전·플랫폼은 별도 검증이 필요합니다.

공통 검사기는 제출된 SQL이나 CSQL 명령을 실행하지 않고 문법 검사 결과와 작성 경고를 제공합니다.
객체 존재 여부·권한·실행 결과·의미·스타일 규칙은 검사하지 않습니다.
이 검사는 터미널 완성과 별개입니다. SHOW·힌트 후보는 네이티브 문법 지원을 보장하지 않습니다.

## 남은 터미널 연동 작업

이 터미널의 자체 완성 엔진을 공통 코어로 전환하는 작업은 아직 남아 있습니다.
완성 메뉴·히스토리·PTY 처리·SQL 실행은 터미널이 담당합니다.
Ctrl+X Ctrl+E는 이미 외부 편집기를 엽니다. 해당 편집기에서 LSP 기능을 사용하려면
별도 편집기 클라이언트와 서버를 설정해야 합니다.

## 이후 확장 목표

- **CUBRID SQL 포매팅:** 코드 정렬과 편집기 포매팅 동작을 연결합니다. 포매팅은 아직 구현되지 않았습니다.
- **구문 강조 개선:** 초기 Vim syntax·TextMate 규칙 이후 Tree-sitter 도입을 검토합니다.
- **더 넓은 완성·검사:** CTE·파생 결과, PL/CSQL, 의미·스타일 린트, 편집기 실시간 카탈로그를 검토합니다.
- **추가 환경:** 다른 CUBRID 빌드·버전과 운영체제는 환경별 검증 이후 확대합니다.

배포 날짜를 확정한 약속은 아닙니다. 현재 우선순위는
[공통 엔진 로드맵](https://github.com/vimkim/cubrid-language-tools/blob/main/docs/product-roadmap.md)을 참고하세요.
