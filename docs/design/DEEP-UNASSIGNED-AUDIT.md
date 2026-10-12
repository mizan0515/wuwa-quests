# 명조 미확인 대화와 Sequence 추가 조사

고정 입력은 2026-10-08 추출물과 이전 자료집의 미귀속 9,331상태다. 이번 추가 조사는 그중 호출 근거가 없었던 1,877상태를 동일 목록으로 재검토했다. 실제 사용·게임 진행 조건·출시 버전·지역은 정적 참조와 별도로 미확인으로 유지한다.

## 결과와 보존

- 355상태에서 추가 설정 참조를 확인했다. GuessJokerPlotConfig 188, PhantomBattleDialog 155, DrinksRoleInvite 9, RogueEvent 3상태다.
- 전체 분류는 `no_korean 591 / quest 1,143 / level 1,812 / entity 3,829 / config 434 / unreferenced 1,522`다. 기존 분류의 우선순위와 복수 소유 관계를 유지했다.
- 전체 42,667 원문 행, 한국어가 있는 40,197행, 고유 한국어 키 39,231개, 687개 읽기 그룹을 유지했다. 새 참조는 기존 원문에 사용 근거를 추가한다.
- 이전 상태별 raw·화자·선택지·분기·행 순서·기존 소유 관계와 근거가 그대로 일치했다. 모든 그룹의 ID·제목·원문 요약·상태·기존 장면 링크를 유지하고 `kinds`만 더 정확한 분류로 갱신했다.
- 설치본에서 추가 추출한 FlowLists 1,187개가 고정 스냅샷의 파일별 SHA256과 전부 일치했다. 다른 소비 코드·리소스의 버전까지 동일하다고 확대하지 않는다.

## 참조를 확인한 방법

게임에 포함된 generated Config accessor의 필드 번호와 타입을 읽었다. 이전 감사는 주로 FlatBuffers root string에 저장된 JSON 참조를 읽었지만, 일부 설정은 FlowListName·FlowId·StateId를 별도 scalar 필드에 저장한다.

`typed_flow_schemas.json`에는 11개 테이블의 확인한 필드와 DB/accessor 해시를 기록한다. 설치본 JS나 게임 데이터 파일을 저장소에 배포하지 않는다. SQL Id와 native Id가 일치하는 행만 처리하고, 입력 DB 해시와 직렬화가 달라지면 중단한다.

PhantomBattleDialog의 PlotName은 설치본 소비 코드가 `GetFlowStateActions(PlotName, FlowId, StateId)`에 넘기는 것을 확인했다. DrinksRoleInvite의 AfterTalk은 `FlowListName,FlowId` 쌍이며, 실제 소비 코드가 AfterTalkStateId 벡터에서 선택한 상태를 `StartFlow`에 넘긴다. Teleporter의 Plot 삼중 문자열도 실제 `split`과 StartFlow 호출로 의미를 확인했다. Teleporter는 이번 고정 코호트에서 새로 분류되는 상태가 없었다.

기록한 `/references/<index>`는 이 선언된 필드에서 재구성한 참조다. 원문 근거 펼침에 실제 필드·값·직렬화·accessor와 소비 코드의 리소스 경로·해시를 함께 보여준다. 임무 이름이나 지역은 이 참조만으로 부여하지 않는다.

독립 검증은 exporter의 FlatBuffers reader나 graph traversal을 사용하지 않는 manual struct decoder로 SQL PK, blob 해시, 선언 필드와 값, 정확한 상태 및 호출 체인을 재생했다. 새 355상태의 355참조가 모두 통과했다. 사이트 검증기는 기존 JSON 위치 재생과 이 별도 typed decoder를 함께 사용한다.

## 조사한 추가 표면과 한계

ConfigDB 1,278,457행에 구조 검사를 적용했다. 2,140,194 table 위치, 469,307 vector 위치, 520,958 nested string을 조사했고, 594,877 JSON 필드를 읽었다. 이 추가 구조 검사에서는 고정 코호트에 연결되는 새 명시 JSON 참조를 찾지 못했다. 구조적 탐지 결과는 새로운 스키마의 완전성을 보증하지 않는다.

별도 직렬화인 general_event 850행은 `u32 count → 길이 접두 UTF-8 key/value → flag 2 bytes` 형식으로 끝까지 디코딩했다. 대사·연출 관련 후보 41행에는 NetworkId·NetworkRes·Sequence 및 Prompt 등 과거 참조가 있었다. 현대 Flow 상태와의 연결을 입증하지 못해 귀속에 사용하지 않았다. 남은 unsupported root와 native scalar/vector의 정체가 모두 확정된 것은 아니다.

설치본 JavaScript 20,632파일에서 고정 코호트의 FlowListName literal도 조사했다. 예외 목록·리소스 검사·전투 연출 같은 언급은 실행 호출이나 임무 소유 근거로 승격하지 않았다.

## Sequence 대사와 native 리소스

raw Flow에서 Sequence 관련 필드 3,340개를 조사했다: SequenceDataAsset 1,609, SequenceNames 1,620, Sequence 110, AnimSequence 1개다. 별도로 PlaySequenceData 416호출을 조사했다. 동일 PAK provider의 읽기 전용 목록은 Sequence 관련 virtual file 168,415개를 반환했다.

- 3,340필드: exact native package 미발견 49, child 선택/비리소스 metadata 1,708, 존재하지만 native property graph를 전수 디코딩하지 않은 것 1,583개.
- PlaySequenceData 416호출: exact package 미발견 40, 유효한 native object path 형식이 아닌 값 3, 존재하지만 graph를 전수 디코딩하지 않은 것 373개.
- 관련 2,072상태 중 1,429상태에 읽을 원문이 있었으며 28,509행이 기존 임무 장면 또는 미귀속 원문 읽기에 보존되어 있었다. 643상태에는 지원하는 Flow schema의 읽을 한국어가 없었다. 이 지원 경로에서 추가할 spoken/choice/screen row는 0행이었다.

실제 Sequence 소비 코드에서는 MovieSceneDialogueSubsystem의 DialogueId가 FlowSequence.CreateSubtitleFromTalkItem을 통해 현재 ShowTalk.TalkItems의 항목을 찾고, PlotSubtitleView가 그 TidTalk과 Options.TidTalkOption을 읽는다. 따라서 animation 파일의 숫자나 이름으로 새 대사를 만들지 않는다.

native canary는 Flow에 명시된 정확한 DA_M1_7_01 경로를 선택했다. UE package header/name/import/export/tagged property를 디코딩하여 GeneratedData ObjectProperty의 정확한 import를 따라 Generated_DA_M1_7_01도 읽었다. 같은 basename의 다른 폴더가 추출 필터에 잡혔지만 그 파일을 원래 호출의 자료로 사용하지 않았다. KeyFrames/FinalPos struct array의 상세 payload와 전체 native MovieScene event graph는 미확인이다. OpenMultiTextCaption의 native 인자도 전체 리소스에서 확인한 것이 아니므로 영상/연출 화면 문구 전체가 완전하다고 주장하지 않는다.

1,522상태의 잔여 판정은 **조사·디코딩한 표면에서 새 소유 근거가 없다**는 뜻이다. 미사용·삭제·시험용·플레이 불가를 뜻하지 않는다. 서버가 제공하는 Flow, 아직 디코딩하지 않은 native event 인자, 별도 런타임 경로는 미확인으로 남는다.

## 재현과 검증

```text
python -B -X utf8 source/tools/attribute_dialogues.py --repo <owned-repo> --configdb <fixed-ConfigDB> --flowlists <fixed-FlowLists> --client-scripts-root <extracted-Aki-JavaScript>
python -B -X utf8 source/tools/verify_dialogue_attribution.py --repo <owned-repo> --configdb <fixed-ConfigDB> --flowlists <fixed-FlowLists> --dist <built-dist>
npm run build
npm run qa:reading
```

생성/빌드와 공개 게시, 브라우저 실사용 검증은 별도 범위다. 이 문서는 내부 조사 근거이며 독자용 원문이나 검색 색인에 넣지 않는다.

이번 owned checkout에서 수행한 검증은 다음과 같다.

| 검증 | 결과와 범위 |
| --- | --- |
| 사이트 build | PASS, 2,242페이지와 Pagefind의 2,243 HTML |
| qa:reading | PASS, 112개 검사 |
| 실제 DB + 렌더된 attribution | PASS, 9,331상태·687페이지·11,398 고유 호출 경로 |
| 실제 DB quest supplement | PASS, 766임무·3,688추가 장면·16,561추가 행 |
| 원문 렌더 | PASS, 766임무·13,019장면·115,702표시 행·16,862선택지·9,289분기 |
| 전체 링크/앵커 | PASS, 2,243 HTML·213,035 링크/앵커·766임무 원문 해시 |
| 기존 인물·지역 탐색 | PASS, 215 HTML·433원문 참조 |
| SEO와 변조 canary | PASS, 2,242페이지·원문 검색 metadata 오염 0·24개 canary |

실제 브라우저의 모바일·키보드·뒤로 가기 검증과 게시/병합은 통합 담당자가 별도로 수행한다. 위 PASS는 실제 게임 플레이 및 native event graph 전수 검증을 뜻하지 않는다.

## 추가 native canary 재검증

Generated KeyFrames의 SSequencesKeyFrames(자막·shot 시각과 FrameEventFrames)와 FinalPos의 Transform을 명명된 struct로 읽었다. 이 canary의 payload는 시간·위치 자료였다. 정확한 DA import로 따라간 M1_7_01_1Z의 MovieSceneDialogueSection 8개를 별도 manual FText decoder로 재생했고, DialogueInfo·DialogueID·SpeakerID가 해당 SequenceDataAsset을 호출하는 ShowTalk의 TidTalk·TalkItem ID·WhoId와 8개 모두 일치했다. 기존 Flow 원문을 다시 가리키는 근거이며 새 본문은 없었다.

OpenMultiTextCaption 소비 코드가 전달 인자를 TidSubtitleText로 사용하는 것은 확인했다. 조사한 EventChannel의 Function은 null이므로 특정 호출과 본문 인자는 입증하지 못했다. master blueprint의 OpenCaptionImage는 이미지 경로였다. 한국어가 없는 다른 PlaySequenceData 경로도 Data_M0229에서 명시 import와 SubSequence 4개를 따라 scene·camera·audio·function 자료를 조사했으나 새 본문 키를 확인하지 못했다.

이번 추가 조사에서 새 읽을 원문과 귀속은 0건이었다. 51개 UFunction/UStruct script tail과 4개 native container schema의 최초 실패 package·export·offset을 별도 내부 근거에 남겼다. 함수 직렬화와 bytecode의 명명된 reader가 필요한 경계이며, 조사한 canary를 전체 native graph의 완전성으로 확대하지 않는다.
