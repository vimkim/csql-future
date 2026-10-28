# 10: 설정 가능한 VS Code 확장

**한국어** | [English](10-vscode.en.md)

**구현 결과:** 로컬 VSIX를 설치해 Neovim과 공통 완성·진단을 공유하고 CUBRID 어휘 기반 구문 강조를 제공합니다.

**선행 조건:** 05, 08.

**상태:** 명세 작성 완료. 선행 결과의 검증·통합을 기다립니다.

## 새 에이전트에 전달할 문맥

[명세](../spec.md), [계약](../contracts.md), [실행 규칙](../execution.md), 선행 보고서를 읽습니다.
지원 의존성을 고르기 전에 공식 확장·언어 서버·TextMate 가이드를 읽습니다.
계획 기준: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
조정자는 실제 할당 기준과 선행 커밋을 제공합니다.

## 범위와 소유 파일

`editors/vscode/`, 패키지 잠금·테스트·설치 가이드를 소유합니다.
언어 ID `cubrid`, TypeScript, 버전 고정 `vscode-languageclient`, 사용자 설치 Python 서버 argv를 사용합니다.
TextMate 규칙과 구문 강조·주석·괄호·들여쓰기의 기본 언어 설정을 제공합니다.
기본 `.csql` 연결을 설정할 수 있어야 합니다.
`.sql` 선택 연결에는 workspace/user `files.associations`를 사용합니다.
일반 SQL 문서를 가로채거나 marketplace에 게시하지 않습니다.

## 완료 조건

- [ ] 기본 `.csql`과 명시적 `.sql` 연결에서 공통 완성·serial 진단이 동작합니다.
- [ ] 무관한 SQL 문서에서는 이 클라이언트를 시작하지 않고 명시적 사용자 언어 연결도 유효합니다.
- [ ] 스냅샷 설정·재로드·미저장 `cubrid` 문서·대체·Unicode 범위·닫기가 서버 계약과 같습니다.
- [ ] 신뢰한 서버·런타임 설정과 argv 배열을 사용합니다. 프로젝트 데이터로 임의 명령을 실행하지 못합니다.
- [ ] 서버·의존성·런타임 부재 시 문서를 손상시키지 않고 조치 가능한 가용성 안내를 제공합니다.
- [ ] TextMate 예제로 키워드·주석·문자열·식별자·CSQL 명령 줄을 확인합니다.
- [ ] 검증한 VS Code engine·client 버전 조합을 고정하고 remote Linux를 포함한 Linux extension-host 범위를 문서화합니다.
- [ ] 재현 가능한 의존성 설치·headless extension-host 검사·로컬 VSIX 생성 `just package-vscode`를 추가합니다.
- [ ] 검사 중 GUI·브라우저 자동 열기·패키지 게시·DB 연결을 하지 않습니다.

## 근거와 인계

범위만 커밋하고 검사·패키징 명령, 실제 버전, VSIX 위치와 커밋을 `reports/10.md`에 기록합니다.
티켓 11에 반영합니다.
