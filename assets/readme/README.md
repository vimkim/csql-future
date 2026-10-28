# README 화면 자료

**한국어** | [English](README.en.md)

정적 SVG는 편집기의 Catppuccin 계열 색상을 사용합니다.
배경은 `#1e1e2e`, 본문은 `#cdd6f4`, 프롬프트는 `#cba6f7`,
키는 `#89b4fa`, 보조 설명은 `#a6adc8`입니다. 제목은 SQL 프롬프트와 커서를 모티프로 사용합니다.

`hero.svg`는 직접 작성한 벡터 제목입니다.
`history.svg`와 `completion.svg`는 프로젝트 PTY 테스트 도구로 실제 설치된 편집기를 실행해
캡처한 본문을 렌더링합니다. 히스토리와 `employees` 카탈로그는 설명용 테스트 데이터입니다.
실제 DB·사용자 히스토리·자격 증명을 사용하지 않습니다.
터미널 본문의 순서를 유지하고 바깥 빈 행을 자른 뒤 필요한 강조만 적용합니다.

저장소 루트에서 캡처를 재생성합니다.

```bash
uv run python tests/capture_readme.py
```

너비 900px의 데스크톱과 360px의 모바일 환경에서 SVG를 확인하세요.
README는 시연 동작을 Markdown으로도 설명하므로 작은 화면에서 축소된 터미널 본문은 보조 자료로 사용합니다.
정적 SVG에는 외부 글꼴·스크립트·내장 래스터 이미지·애니메이션이 없습니다.

<a id="live-demodb-recording"></a>

## 실제 demodb 녹화

`demodb-demo.gif`는 데이터가 들어 있는 CUBRID 샘플 DB를 독립 모드에서 열어 실제 편집기를 녹화합니다.
편집 가능한 터미널 원본은 asciicast v2 형식의 `demodb-demo.cast`입니다.
SVG와 같은 색상, DejaVu Sans Mono 글꼴, 88열·24행 터미널을 사용하고 완성 메뉴에서 잠시 멈춥니다.

`csql-future -S -u dba --no-pager demodb`를 실행하고 `s`를 `SELECT`로 완성합니다.
힌트 메뉴에서 `PARA`로 필터링해 `PARALLEL`을 선택하고 `(2)`를 붙입니다.
`FROM` 뒤에서 `athlete`를 완성한 다음 SELECT 목록으로 돌아가 `name`·`code`를 완성합니다.
`LIMIT 3`으로 실행하고 `;plan detail`을 완성한 뒤 `;exit`로 종료합니다.
쿼리는 샘플 데이터를 읽기만 하며 `;plan`은 세션 설정을 변경합니다.
임시 디렉터리로 녹화 히스토리를 개인 히스토리와 분리합니다.

다시 녹화하려면 `PATH`에 `csql`이 있는 CUBRID 환경과 데이터가 채워진 `demodb`가 필요합니다.
DB는 독립 모드에서 접근할 수 있어야 합니다.
`just sync`로 프로젝트를 설치하고 [agg](https://github.com/asciinema/agg)와 DejaVu Sans Mono 글꼴을 준비합니다.
저장소 루트에서 다음 명령을 실행합니다.

```bash
python3 tools/record_readme_demo.py
```

스크립트는 이 체크아웃의 편집기 코드를 사용하고 예상 메뉴·결과가 없으면 실패합니다.
DB를 만들거나 서버를 관리하지 않습니다. 이 디렉터리의 `demodb-demo.cast`·`demodb-demo.gif`만 덮어씁니다.
다른 녹화를 미리 확인하려면 `--output-dir /tmp/csql-demo`를 사용합니다.

녹화된 세션은 DB 없이 재생할 수 있습니다.

```bash
asciinema play assets/readme/demodb-demo.cast
```

<a id="live-history-recording"></a>

## 실제 히스토리 녹화

`history-demo.gif`는 실제 `demodb` 독립 모드에서 Ctrl+R 검색과 히스토리 탐색을
보여 주는 별도 녹화입니다. `history-demo.cast`에 터미널 출력을 보관합니다.
자동 완성 영상과 같은 색상·터미널 크기·글꼴·녹화 환경을 사용합니다.
`history.svg`도 정적 예시로 남아 있습니다.

다음 쿼리를 실제로 실행해 새 히스토리를 만듭니다.

```sql
select name from athlete limit 3;
select code from athlete limit 3;
```

Ctrl+R과 아래 방향키로 두 항목을 탐색한 뒤 `name`을 입력하면 일치하는 쿼리
하나만 남습니다. Enter로 편집기에 불러온 상태에서 잠시 멈추고, Enter를 다시 눌러
실행한 뒤 `;exit`로 종료합니다. 임시 디렉터리에서 이 세션이 만든 히스토리만
사용하며 개인 히스토리는 읽지 않습니다.

자동 완성 영상과 같은 환경을 준비한 뒤 저장소 루트에서 재생성합니다.

```bash
python3 tools/record_history_demo.py
```

스크립트는 두 쿼리가 히스토리에 보이는지, `name` 검색 후 한 항목만 남는지,
불러오기만으로 SQL이 실행되지 않는지,
총 세 번의 쿼리 실행이 성공하는지 확인합니다. `history-demo.cast`와
`history-demo.gif`만 기록하며 자동 완성 녹화는 변경하지 않습니다.
별도 경로에서 확인하려면 `--output-dir /tmp/csql-history-demo`를 사용합니다.

```bash
asciinema play assets/readme/history-demo.cast
```
