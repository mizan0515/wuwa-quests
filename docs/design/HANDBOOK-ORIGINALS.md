# 도감·튜토리얼 한국어 원문 확장 — issue 52

독자가 원문 보관함에서 튜토리얼·도움말·에코·잔상 도감을 검색하고, 자료의 실제 페이지·분류·조리 연결을 따라 본문과 출처를 확인하도록 기존 원문 형식에 증분 통합했다. 설치본과 보존 캐시, 이전 원문 묶음은 수정하지 않았다. 사용자 소유 RECORD-READING-INTERNAL.md와 기존 Python bytecode는 작업 대상에서 제외했다.

## 수록과 보존

| 종류 | 보존 행 | 기본 읽기 항목 | 기본 목록 밖의 원문 |
|---|---:|---:|---:|
| 튜토리얼 페이지 | 1,178 | 1,144 | 한국어 본문 없음 34 |
| 게임 도움말 | 686 | 663 | 본문 없음 21, 단일 테스트 표시 1, xx 자리표시자 1 |
| 잔상 도감 | 267 | 68 | 한국어 본문 없음 199 |
| 에코 도감 | 112 | 47 | 한국어 본문 없음 65 |
| 도감 분류 | 18 | 18 | 0 |
| 합계 | 2,261 | 1,940 | 321 |

기존 원문 9,228행과 읽기 항목 8,668개를 보존하여 총 원문 11,489행, 기본 읽기 항목 10,608개가 되었다. 새 원문 필드 5,176개는 OK 4,158 / MISSING_KEY 75 / NO_REFERENCE 925 / EMPTY 18로 보존한다. 기본 목록 밖의 항목은 「빈·테스트 원문 포함」 선택과 기존 개별 source 경로로 열 수 있다. 일반 게임 설명의 ‘테스트’ 언급은 제외하지 않는다. 단일 본문 「테스트」 및 실제 xx 자리표시자는 별도 상태로 보존한다. 이는 실제 게임에서 사용되는지에 대한 판정이 아니다.

새 데이터 파일은 settings/records-tutorials.json, records-help.json, records-monster-handbook.json, records-echoes.json, records-handbook-types.json이다. 기존 records-*.json 14개는 바이트 단위로 불변이다. index의 기존 항목·별칭·URL도 보존하고 source_relations만 증분 추가했다. 기존 index와 manifest의 2칸 들여쓰기·LF·끝 개행 형식을 유지했다.

## 실제 연결

source-relations.json의 1,268개 관계는 튜토리얼 부모 724개, 조리 레시피 98개, 잔상 도감 분류 267개, 아이템 도감 수록 139개, 무기 도감 수록 40개이다. 부모의 페이지 배열은 1,134회 참조/고유 페이지 1,099개를 가리킨다. 나머지 79페이지는 이 부모 테이블에서 관계가 확인되지 않아 별도의 부모를 만들어 넣지 않았다. 전체 페이지는 보존하고 검색/개별 원문에 연결했다. 배열 순서는 자료의 수록 순서이며 플레이·작중 시간 순서로 해석하지 않는다.

guidetutorial 부모 30001의 실제 field 3 배열은 [1, 3000102]이다. 페이지 1의 field 2는 Tutorial_01_Title, field 4는 GuideTutorialPage_1000001_Content를 담고 있다. 문자열 키의 1000001을 페이지 ID로 사용하지 않는다. 이 페이지는 「잔상이 격파된 후 남긴 주파수는 <color=#ffd12f>에코</color>가 될 수 있습니다.」로 시작하는 한국어 원문을 그대로 보존한다. 원본 BinData SHA-256은 19b313c678bb7371bffe66d1bdf7b883843dc222acab9c5bf54cc9dfc4be8623이다.

monsterhandbook은 SQL/FB ID, MonsterId(field 1), Type(field 2)를 대조하고 field 3 이름과 field 6 본문만 읽는다. 310000010의 한국어 이름은 「선봉 암괴」이며 본문은 「부서진 암석 구조의 잔상. 시력이 약하고 제멋대로 설치는 걸 좋아한다.」로 시작한다. 독립 대조에서 이 도감의 68본문 행 중 기존 원문과 동일한 6회가 확인되었고, 나머지는 새 본문 62회/고유 원문 47개이다. 에코 도감의 47행/94본문 필드는 기존 원문과 겹치지 않는 고유 본문 69개로 확인되었다. 표 전체의 미해석 nested 필드를 읽었다거나 FlatBuffers 전체 스키마 EOF를 증명했다는 뜻은 아니다.

조리는 cookformula의 실제 FormulaItemId(field 1)와 FoodItemId(field 2)를 기존 아이템 원문 ID 및 정본 별칭에 연결한다. 재료 배열·수량·조리 성공 조건은 해석하지 않았다. 아이템 도감의 Type과 표제(field 2)는 서로 다른 원문이므로 합치지 않고 각각 표시한다. 무기 도감은 실제 수록 ID만 기존 무기 원문과 연결하며 별도 새 배경 본문을 주장하지 않는다.

## 출처와 확인 범위

읽기 전용 입력은 보존 ConfigDB 캐시이다. BuildInfo.txt의 Stream=branch_3.7_final / Changelist=8837363 / PatchVersion=3.7.0 및 ConfigVersion.txt의 PublicJsonVersion=8836145는 캐시 메타데이터 관찰값이다. 현재 설치본과의 일치 및 최초 출시 버전은 UNVERIFIED로 유지하며 기존 manifest.client_version을 변경하지 않는다. 메타데이터 파일 해시는 각각 30f9d636453ce31b95970ccd1f414f895bb79abbefd43c357acba64471a0b602와 1f23a458c59d5eaef240f3c437db9268cf2df2c8e23d799005e44f72e5c0b23a이다.

모든 선택 DB와 KO 주/half DB의 SHA-256은 handbook-provenance.json에 기록했다. DB 연결은 mode=ro이다. 한국어 RedirectDbIndex=1만 half DB로 이동하며 half-only 키를 보존한다. 원문 field index, 실제 text_id, raw, 정리한 text, 상태, locale DB, BinData SHA가 각 항목에 남는다. 공개 입력에는 호스트 절대 경로가 없다. 실제 한국어 rich text 안의 <texture=/Game/.../>는 raw에 보존하고 표시 본문·검색용 text에서만 숨긴다. 자산 URL 변환이나 자산 fetch는 추가하지 않았다.

db_Term.term 185행과 termconfig 655행의 field 1은 SQL Term과 동일한 중국어 literal이다. term.field 2는 모두 비어 있고 termconfig의 60개 비어 있지 않은 field 2는 모두 UTF-8 색 문자열 #c79f49이다. 이 필드에서 한국어 정의 참조는 확인되지 않았다. 7바이트 문자열 길이를 정의 벡터 길이로 해석하지 않는다. guidetutorial의 SQL TutorialType=11인 125행은 binary field 1=0이며 두 값을 각각 보존하고 의미를 UNVERIFIED로 둔다. 부모 관계의 근거는 실제 field 3 배열이다.

## 재현과 검증

사이트 저장소의 source/tools/wuwa_handbook.py는 정본 스킬 fb_utils.py의 제한된 offset reader를 재사용한 구현이며 필요한 문자열 terminator와 UInt32 vector bounds 검사를 추가했다. 정본 스킬 자체는 변경하지 않았다. 아래 경로는 내부 재현용이며 공개 생성 입력에 들어가지 않는다.

```powershell
python -B -X utf8 D:/game/projects/wuwa-quests/source/tools/expand_handbook_originals.py --configdb D:/game/.game-work/wuwa-20261008/extracted/Client/Content/Aki/ConfigDB --site D:/game/projects/wuwa-quests --output D:/game/.codex-work/handbook-expansion/wuwa/NEW-FRESH-DIRECTORY --baseline D:/game/.codex-work/handbook-expansion/wuwa/initial-extraction --apply

python -B -X utf8 D:/game/projects/wuwa-quests/source/tools/verify_handbook_originals.py --configdb D:/game/.game-work/wuwa-20261008/extracted/Client/Content/Aki/ConfigDB --site D:/game/projects/wuwa-quests --snapshot D:/game/.codex-work/handbook-expansion/wuwa/verified-extraction --output D:/game/.codex-work/handbook-expansion/wuwa/NEW-FRESH-VERIFICATION.json

# private DB와 snapshot 없이 실행하는 공개 산출물 검증
# 작업 디렉터리 D:/game/projects/wuwa-quests/source
node --test tools/handbook-originals.test.mjs
```

새 출력 디렉터리는 비어 있어야 한다. 기존 정본 설정을 처음 확장할 때는 --baseline 없이 실행한다. --apply를 생략하면 private snapshot과 제안 index만 만들며 사이트는 수정하지 않는다. 현재의 owned 확장을 재생성할 때는 저장한 최초 baseline을 사용한다. 원본 cache/snapshot을 덮어쓰지 않는다.

verified-extraction이 최종 private snapshot이며 initial-extraction 및 final-extraction은 이전 증거로 보존한다. verification-final.json의 독립 재생은 추출기를 호출하지 않고 별도 offset traversal과 키별 SQL lookup으로 6,039필드(원문 5,176+부모 제목 724+아이템 도감 표제 139), 부모 724개, 조리 98개, SQL/FB ID와 관계 순서를 PASS로 확인했다. 기존 원문 묶음 14개와 읽기 항목 8,668개 보존, 원문 키/raw/locale/상태·부모 순서/숫자 추정·정상 테스트 본문·texture raw·호스트 경로 변조 10개를 거절했다.

공개 focused guard는 private 입력 없이 manifest/원문·진단 경로·수록 수·원문 보존 해시·관계 sidecar와 index의 전수 일치를 확인한다. 기존 URL/별칭, 잘못된 기본 읽기 상태, 진단 누락, 부모 배열/추정 ID, 조리/분류/수록 오연결, index 관계 누락, 설치본 일치 주장 등 13변조를 동일 validator로 거절했다. package.json의 qa:reading aggregate에 연결했다. 최초 UI canary의 제목 공백 가정은 실패했으며 문자열 표기 추정 대신 원문 페이지 ID의 실제 렌더 순서를 확인하도록 수정했다.

작성자는 전체 빌드·export·브라우저·Git을 실행하지 않았다. 코드·공개 입력은 root 빌드 시작 전에 동결했다. 전체 gate, 생성 산출물, 모바일·키보드·검색/필터·원문 복귀 및 최종 공개는 root가 검증·반영한다.

정본 스킬 후속 제안은 setting-texts.md에 위 observed schemas/페이지 배열/KO redirect/진단 구분과 실제 캐시 경계 및 새 durable CLI를 연결하는 것이다. 이는 별도 승인 범위이며 이번 작업에서 스킬은 수정하지 않았다.
