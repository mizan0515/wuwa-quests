# 게시 데이터와 검색

원문 보관함의 읽기 항목 전체를 상단 검색에서 찾는다. 개별 정적 원문 페이지가 있는 항목은 기존 HTML 색인을 사용하고, 나머지 한국어 원문은 Pagefind의 addCustomRecord로 같은 검색 색인에 등록한다. 환경설정 UI와 빈·테스트 기록의 별도 보관함 접근은 유지한다. 검색 결과는 기존 원문 주소로 연결하며 문자열 일치로 다른 자료를 병합하지 않는다.

| 산출물 | 생성자 | 소비자와 공개 목적 |
|---|---|---|
| settings/index.json, records-*.json | 보존 설정 입력과 generate-lore | 원문 다운로드·이전 주소 호환, 본문 검색, 상세 원문 |
| settings/library-index.json | library-discovery | 목록·필터·별칭에 필요한 기본 메타데이터 |
| settings/library-details-*.json | library-discovery | 해당 원문의 관계·출처·본문 필드 정보, 상세 진입 때 요청 |
| settings/library-diagnostics.json | library-discovery | 진단 선택 또는 원문 상세에 연결된 비어 있는 자료 |
| pagefind | 기존 HTML 색인과 search-originals | 제목·본문 검색; 전체 원문 JSON을 검색창에서 받지 않음 |
| reading-data 전체 | 기존 공통 모델 생성기 | 빌드의 편집 관계와 전체 원문·해시·링크 QA; 게시에서는 graph와 blockIndex 묶음을 함께 제외 |

전체 검증 모델은 public/reading-data와 dist/reading-data에 남겨 기존 검증기를 그대로 실행한다. 실제 branch publisher의 _config.yml만 공개 제외 경계를 적용한다. HTML·브라우저 자산에서 reading-data URL을 직접 요구하지 않는지 확인하고, 게시 후보 검사도 같은 경계를 사용한다. 원문 TXT·settings 원자료·개별 HTML·검색 색인은 유지한다.

원문과 사용 문맥은 기존 source ID, 필드, 화자, 판본, 인용 위치로 연결한다. 같은 문자열만으로 다른 장면·판본을 합치지 않는다. 공통 UI는 10월 14일에 검증된 공유 컴파일러를 재사용하며 이번 변경은 새 리더를 만들지 않는다. 검색 색인의 확대 비용과 메타데이터 제외 절감, 초기 목록 감소를 각각 측정한다.
