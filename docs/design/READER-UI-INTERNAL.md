# 공통 독서 UI 경계

이 문서는 개발용 기록이며 공개 콘텐츠 생성 입력에 포함하지 않는다.

## 확인한 원인

명조 목록은 `QuestCatalog.astro`의 `catalog not-content` 안에 있다. 명조 퀘스트와 설정집의 생성 HTML, 스타레일의 `MissionReader.astro`는 Starlight의 `sl-markdown-content` 안에 별도 스타일 경계 없이 배치되어 있었다.

Starlight `markdown.css`는 비인라인 형제의 위쪽 여백, 제목·목록 간격, `details`의 왼쪽 테두리와 안쪽 여백, `summary`의 음수 여백과 가상 펼침 표시를 제공한다. `.not-content`의 하위 요소는 이 문서 스타일에서 제외된다. 사용자 HTML의 폼·그리드·접기·절대 배치 노드에는 해당 영역에서 직접 정한 간격과 표현을 적용한다.

두 사이트의 reading-kit 1.3.1 manifest 해시는 같았다. 원문 대사 화면은 명조의 `quest-source-line`과 스타레일의 `Scene.astro`가 각 게임의 자료 구조를 변환한다. 이 어댑터를 유지하면서 공통 독서 UI 표면을 공유한다.

## 명조 어댑터

`source/tools/generate.mjs`는 장면 Markdown 제목과 `scene-N` 앵커를 기존 위치에 둔다. 각 장면의 대사·선택지·분기와 접힌 장면 정보는 `readerFrame`으로 감싼다. Markdown 제목을 HTML 문자열 안에 함께 넣으면 Markdown의 HTML 블록 처리에 따라 제목이 일반 텍스트로 남을 수 있으므로 제목은 독립 블록으로 유지한다.

- 프레임: `rw-reader not-content`, `data-reading-template="reader"`, 기존 명조 어댑터 클래스 `quest-reader`.
- 원문 행: 기존 `quest-source-line` 및 행 종류 클래스를 보존하고, `rowAttributes`의 `rw-source-row`, `data-reading-template="row"`, `data-reading-kind`를 더한다.
- 화자가 분리된 본문: 기존 `quest-speech`에 `rw-source-body`를 더한다. 화자·대사 번호·콜론의 접근성 표현은 기존 마크업을 유지한다.
- 접기: `readerDisclosure`를 사용하고 `quest-info`·`quest-scene-info`와 `data-pagefind-ignore`를 보존한다. `summary` 안에는 별도 펼침 문자나 아이콘을 추가하지 않는다.

원문 파일 선택, SHA 대조, 장면 정규식, 행 분류, 원문 태그 제거·이스케이프, 목록 정렬, 원문 TXT 복사 코드는 기존 구현을 유지한다. 이번 변경은 HTML의 스타일 경계와 공통 행 속성을 추가한다.

## 공유 스타일 계약

공통 독서 프레임의 간격·목록·폼·접기는 reading-kit이 관리한다. 게임 어댑터는 화자 열과 대사 번호 표시 등 게임별 배치만 관리한다. 전역 `sl-markdown-content details`나 게임별 `.speaker`처럼 다른 템플릿에도 영향을 주는 규칙의 범위를 확대할 때는 두 사이트의 인접 표면을 함께 대조한다.

프레임 안에서 제목·본문·보조 정보의 여백은 명시한다. 행 전체의 `white-space:pre-wrap`은 템플릿의 공백까지 표시하므로 원문 본문 요소에만 적용한다. 모바일에서는 원문과 선택지·분기의 의미를 유지하며 화자 열을 읽기 순서에 맞게 배치한다.

관계도 노드는 별도 검증 대상이다. 기존 `rw-map-node`는 절대 배치이며 Starlight의 `svg + div`, `div + div` 위쪽 여백 선택자가 적용될 수 있다. 공통 UI 경계에서 위치 여백을 관리하고, 선의 끝점과 노드의 위치를 실제 렌더링으로 확인한다.

## 통합 검증 대상

루트 담당자가 공통 helper·스타일을 제공한 뒤 생성과 검증을 수행한다. 이 어댑터 작성 단계에서는 생성·빌드·브라우저를 실행하지 않았다.

- 기존 생성 자료와 새 자료의 퀘스트·장면·원문 행 수, 장면 앵커, 원문 TXT SHA가 같다.
- 각 `scene-N` 제목 다음에 해당 장면의 공통 프레임이 오며 원문 행이 다른 장면으로 이동하지 않는다.
- 대사 번호 토글, 화자와 본문, 선택지·분기, 원문 다운로드와 이전·다음 퀘스트 탐색이 유지된다.
- 접힌 출처의 펼침 표시가 한 개이며 열고 닫아도 다음 장면 간격이 일정하다.
- 320px·중간 폭·넓은 화면에서 가로 넘침, 폼 높이·기준선, 줄바꿈, 키보드 포커스를 확인한다.
- 긴 원문, 화자가 없는 행, 선택지·분기가 함께 있는 장면, 자료 정보가 없는 장면, 본문이 없는 장면을 대조한다.

공개 문서에 표시하는 원문은 기존 원문 보존 QA로 대조한다. 문서 스타일을 배제했다는 사실만으로 실제 화면 검증을 통과했다고 판단하지 않는다.
