# 네이티브 파서 실현 가능성 실험

**한국어** | [English](feasibility.en.md)

질문: SQL 스크립트를 실행하지 않고 CUBRID 파서가 정상·오류·미완성 본문을 구분할 수 있는가?

결과: **식별된 Linux 11.5 개발 빌드에서 고정 예제 7개는 가능했습니다.**
[JSON 관찰](evidence/native-probe.json)과 [시스템 호출 요약](evidence/native-probe-trace.json)에 근거를 보존합니다.
이 결과는 구현 방향을 선택하는 근거이며 운영 호환성 주장이 아닙니다.

## 정확한 환경

| 항목 | 관찰 값 |
| --- | --- |
| 라이브러리 반환 버전 | `11.5.0.2704-cc94778` |
| 일치하는 소스 커밋 | `cc947788d3b7dc402f46192d0f3299ddcc8563ba` |
| 로드한 라이브러리 | `/home/vimkim/gh/cb/develop/build_preset_debug_gcc/cs/libcubridcs.so.11.5` |
| 라이브러리 SHA-256 | `56eb36e9a46e3b6f5258974b25085b81d1679430618041343e4d979704822b33` |
| locale·메시지 prefix | `/home/vimkim/.cub/install/develop/debug` |
| 현재 소스 HEAD | `4ddf3b1550cae1ed82d65b5a9a6182912acd237f`, 바이너리와 다름 |
| 네이티브 진입점 | `parser_parse_string_with_escapes(parser, text, false)` |
| 문자셋·언어 | 명시적 `en_US.utf8` |
| 데이터베이스 | 열기·생성·등록하지 않음 |

ctypes는 실험에만 사용합니다. 운영 설계는 컴파일 워커와 검증된 runtime manifest를 사용합니다.
`--source-commit`은 작업자가 제공한 일치 빌드 식별값을 기록합니다.
바이너리 자체의 반환 버전·digest는 독립 관찰입니다.
모든 런타임 의존성의 출처까지 검증한 실험은 아닙니다.

## 관찰

| 예제 | 네이티브 결과 |
| --- | --- |
| `CREATE SERIAL order_no START WITH 10 INCREMENT BY 2;` | 트리 반환, 파서 오류 없음 |
| `CREATE SERIAL order_no START WITH ;` | 트리 없음, 문법 오류 |
| `SELECT e. FROM employees e;` | 트리 없음, 파서 오류 |
| SELECT에서 없는 테이블·컬럼 이름 사용 | 트리 반환, 파서 오류 없음 |
| 한글·이모지·CRLF | 트리 반환, 파서 오류 없음 |
| SQL 문장 두 개 | 트리 반환, 파서 오류 없음 |
| `DROP TABLE must_never_be_executed;` | 트리 반환, 파서 오류 없음 |

엄격한 파서가 거부한 미완성 `e.`에서도 기존 완성 함수는 `id`, `name`을 반환했습니다.
없는 테이블 예제는 파서 허용과 카탈로그 검사가 다름을 보여 줍니다.
DROP 예제는 실행문이 아닌 파서 입력 본문이었습니다.

최종 추적 실행에서는 네트워크 시스템 호출·클라이언트·자손 실행 파일이 관찰되지 않았습니다.
쓰기용 파일 열기는 실험 전용 임시 영역 안에 있었습니다.
추적은 이 예제들의 network·execve·openat만 다뤘습니다.
전체 시스템 호출 sandbox나 모든 grammar action 검토는 아닙니다.

## 이 호스트에서 재현

저장소 루트에서 실행합니다.

```bash
timeout 20s strace -f -e trace=network,execve,openat \
  -o /tmp/cubrid-language-probe-569.strace \
  python -B docs/language-tools/experiments/native_parser_probe.py \
  --library /home/vimkim/gh/cb/develop/build_preset_debug_gcc/cs/libcubridcs.so.11.5 \
  --prefix /home/vimkim/.cub/install/develop/debug \
  --source-commit cc947788d3b7dc402f46192d0f3299ddcc8563ba
```

명령은 JSON을 출력하고 모든 고정 기대값이 맞으면 0으로 종료합니다.
설정·레지스트리·로그·작업 디렉터리에 임시 경로를 사용합니다.
오류·locale·문자셋·메시지·기본 파라미터를 초기화한 뒤 파서 문맥을 직렬로 생성·파싱·확인·해제합니다.
연결·컴파일·실행 함수는 호출하지 않습니다.

정확한 라이브러리와 호환 런타임 자료가 필요합니다.
다른 호스트는 동등하게 검증한 입력과 식별값을 제공·기록해야 합니다.
이 실험을 린트 명령으로 설치하지 않습니다.

## 초기 시도와 수정

첫 탐색 호출은 내장 locale만 초기화하고 활성 문자셋을 설정하지 않아
디버그 라이브러리의 `lang_charset()` assertion에서 중단되었습니다.
수정한 순서는 `lang_init()`, `lang_set_charset_lang()`을 명시 호출합니다.
최종 스크립트는 core dump를 끄고 CPU 시간을 제한합니다.

초기 추적에서는 상대 오류 로그명이 기존 설치의 로그 디렉터리로 해석되었습니다.
최종 스크립트는 절대 전용 경로를 전달하고 보존한 추적이 수정을 확인합니다.
초기 로그는 보존했으며 기존 설치를 재빌드·재설정하지 않았습니다.

## 남은 검증 조건

1. 제품 지원 전에 정확한 11.5 빌드의 운영 워커를 검증합니다.
2. 지원 grammar action의 실행·카탈로그 의존 동작을 검토합니다.
3. 사용자 설정 상속 대신 문법 영향 파라미터를 고정합니다.
4. 일반 파서 오류 목록과 내부 오류 플래그를 함께 확인합니다.
5. 잘못된 한글·이모지·CRLF 예제로 네이티브 오류 좌표 단위를 측정합니다.
6. 부분 트리·빈 입력·다중 오류·충돌·기한·잘못된 요청을 확인합니다.
7. 워커를 패키징하고 런타임 자료·라이선스 고지를 열거합니다.
8. 미검토 형태 파싱 전에 지원 조건을 적용합니다. 문장 종류만으로 리터럴 SELECT 범위를 제한할 수 없습니다.

정상 Unicode 예제는 진단 좌표 정확성을 입증하지 않습니다.
작은 코퍼스는 모든 문장 계열을 입증하지 않습니다.
이 조건은 구현 티켓의 작업이며 이미 완료한 숨은 작업이 아닙니다.
사용자는 계획 검토 후 11.5 우선을 선택했습니다. 다른 11.5 빌드와 11.4는 별도 검증입니다.

일치 소스는 파서 연산을 노출하며 컴파일·실행은 후속 CSQL 단계에 둡니다.
[네이티브 파서 구현](https://github.com/CUBRID/cubrid/blob/cc947788d3b7dc402f46192d0f3299ddcc8563ba/src/parser/parse_tree_cl.c),
[파서 선언](https://github.com/CUBRID/cubrid/blob/cc947788d3b7dc402f46192d0f3299ddcc8563ba/src/parser/parser.h),
[CSQL 실행](https://github.com/CUBRID/cubrid/blob/cc947788d3b7dc402f46192d0f3299ddcc8563ba/src/executables/csql.c)을 참고합니다.
