# 01: 터미널 회귀 없이 재사용 가능한 완성 추출

**한국어** | [English](01-completion-core.en.md)

**구현 결과:** 순수 완성 호출이 현재 터미널의 후보와 대체 범위를 반환하고, 터미널도 같은 모듈을 사용합니다.

**선행 조건:** E01, 병행 완성 작업 568과 통합 상태 확인. 내부 선행 티켓은 없습니다.

**상태:** 명세 작성 완료. 할당 전에 E01을 확인합니다.

## 새 에이전트에 전달할 문맥

[명세](../spec.md), [계약](../contracts.md), [실행 규칙](../execution.md)을 읽습니다.
통합된 완성·메타데이터·CLI 코드와 완성·PTY 테스트를 읽습니다.
main 커밋 `99d49e1`의 `syntax.py`, `completion_data.py`, `test_command_completion.py`를 포함합니다.
계획 기준: `c292d00c3e69a7e8bda08bb03b7e3073c8fe1b1f`.
조정자는 실제 할당 기준과 확인된 작업 568 커밋을 제공합니다.

## 범위와 소유 파일

`src/csql_future/language/`, `completion.py` 호환 인터페이스,
`cli.py`·`metadata.py`의 필요한 import를 소유합니다.
`syntax.py`·`completion_data.py`의 필요한 import도 조정하되 기록된 출처는 바꾸지 않습니다.
`tests/test_completion.py`, `tests/test_command_completion.py`, 새 `tests/test_language_core.py`의 집중 검사를 소유합니다.
메뉴 상태는 터미널 어댑터에 둡니다. 마이그레이션 동안 호환 어댑터로 기존 import를 유지합니다.
카탈로그 조회·히스토리·키·네이티브 파싱·편집기 클라이언트는 변경하지 않습니다.
`justfile` 수정은 조정자와 협의합니다.

## 완료 조건

- [ ] 순수 `complete` 호출은 I/O 없이 계약을 구현하고 결정적인 코드 포인트 대체 범위를 사용합니다.
- [ ] 작업 568의 새 스키마 타입·명령 문맥을 포함한 모든 통합 완성 동작을 검증합니다.
- [ ] 기존 `suggest`, 스키마 값 import와 터미널 메뉴 선택이 계속 동작합니다.
- [ ] 미완성 SQL, 인용 식별자, 소유자 가림, 별칭, 토큰 접미부 대체 결과를 유지합니다.
- [ ] 대체 위치 앞의 한글·이모지가 대체 대상을 바꾸지 않습니다.
- [ ] 공개 완성 인터페이스와 호환 동작을 확인하는 `just test-language-core`를 추가합니다.
- [ ] 통합 기준에서 `just test`를 통과합니다.

## 근거와 인계

diff 검토 후 범위에 해당하는 파일만 커밋합니다.
정확한 명령·개수·기준·커밋·무관한 변경·한계를 `reports/01.md`에 기록합니다.
티켓 03도 완료되면 티켓 04를 시작할 수 있습니다.
