# 공통 CUBRID 언어 도구: 구현 문서 묶음

**한국어** | [English](README.en.md) · [문서 목차](../README.md)

> 초기 계획 보존 기록: 독립 [cubrid-language-tools](https://github.com/vimkim/cubrid-language-tools) 프로젝트가 기존 단일 저장소 계획을 대체합니다. 아래는 당시 기록이며 현재 구현 작업의 할당 지침이 아닙니다.

## 현재 제품

공통 완성 코어·`cubrid-lint`·`cubrid-language-server`는 독립 프로젝트에 구현되어 있습니다.
별도 [VS Code](https://github.com/vimkim/cubrid-vscode)·[Neovim](https://github.com/vimkim/cubrid.nvim)
클라이언트는 이 LSP를 사용합니다. `csql-future`는 여전히 자체 완성 엔진을 사용하며 전환은 후속 작업입니다.
현재 안내는 코어 프로젝트의 [설치 가이드](https://github.com/vimkim/cubrid-language-tools/blob/main/docs/install.md)와
[지원 범위](https://github.com/vimkim/cubrid-language-tools/blob/main/docs/coverage.md),
제품별 역할은 터미널 [로드맵](../roadmap.md)을 확인하세요.
아래의 계획 상태·코드 참조·체크포인트·실험은 당시 범위를 보존합니다.

## 2026-10-28 계획 원문

상태: 2026-10-28에 작성한 계획 산출물입니다. 여기 설명하는 편집기 도구와 린트 명령은 계획 기준 시점에 구현되지 않았습니다.
사용자에게 소개할 현재 기능과 확장 방향은 [로드맵](../roadmap.md)에서 확인하세요.

[명세](spec.md), [계약](contracts.md), [티켓 의존 관계](tickets/README.md)부터 읽습니다.
[파서 조사](parser-research.md)는 선택 근거를 설명합니다.
[실현 가능성 보고서](feasibility.md)는 실험과 한계를 기록합니다.
[실행 규칙](execution.md)은 통합·에이전트 제약을 보존합니다.
[검증 기록](verification.md)은 최초 테스트 실패와 이후 통과 결과를 포함합니다.

선택한 설계는 기존 Python 완성 구현을 터미널과 언어 서버가 공유합니다.
별도의 버전 고정 네이티브 파서 워커가 오프라인 문법 진단을 제공합니다.
Neovim과 VS Code는 같은 언어 서버를 사용합니다.
초기 구문 강조에는 각각 Vim syntax와 TextMate 규칙을 사용하며 Tree-sitter는 후속 개선입니다.

사용자는 **CUBRID 11.5 우선**을 선택했습니다.
초기 검증 대상은 성공한 실험과 같은 `11.5.0.2704-cc94778` 빌드입니다.
실험은 이 호스트에서 DB 없이 파싱하는 경로를 확인했습니다.
11.5 전체 문법이나 운영용 패키징을 입증하지는 않습니다.
다른 11.5 빌드와 11.4는 별도 검증이 필요합니다.

## 저장소 스냅샷

| 항목 | 값 |
| --- | --- |
| 계획 기준 커밋 | `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f` |
| 원래 작업 브랜치 | `planning/language-tools` |
| 원래 작업 체크아웃 | `/home/vimkim/gh/csql-future-project` |
| 병합 대상 | `/home/vimkim/gh/csql-future`의 `main` |
| 통합 후 정식 문서 위치 | `/home/vimkim/gh/csql-future/docs/language-tools` |
| 작업 기록 | `work-tracker show 569` |
| 확인한 완성 통합 | 작업 568, main 커밋 `99d49e13698b609ff4885a418578f7f50485e82f`에서 완료 |

다른 세션은 각자의 작업 트리를 소유하고 독립적으로 진행할 수 있습니다.
구현 조정자는 완성 코드를 추출하기 전에 실제 상태를 확인해야 합니다.
사용자는 이 계획 문서의 rebase·main 통합·main push를 승인했습니다.
통합 검증 전에 브랜치를 완성 통합 커밋 `99d49e1` 위로 rebase했습니다.
티켓 01의 실제 할당 기준 커밋에도 이 결과를 포함해야 합니다.

## 납품 범위

이 문서는 범위를 제한한 구현 티켓 11개를 선택합니다.
각 티켓에는 새 에이전트 문맥 하나와 별도 작업 트리가 필요합니다.
계획 세션에서는 구현 티켓을 수행하지 않았습니다. 로컬 계획 커밋은 승인되었습니다.
당시 승인은 이 계획 문서의 통합에만 적용됩니다.
구현 통합에는 구체적인 결과와 해당 승인이 필요합니다.
확장·패키지·이슈·PR 게시와 배포에는 별도 권한이 필요합니다.
