# 명조 한국어 퀘스트 자료집

[자료집 바로가기](https://mizan0515.github.io/wuwa-quests/index.html)

GitHub Pages에서 제공하는 비공식 퀘스트 대사 자료집입니다. 766개 퀘스트의 대사·선택지를 버전과 임무 종류별로 찾아 읽을 수 있습니다.

## 화면과 기능

Astro Starlight의 왼쪽 버전·임무 목차, 가운데 대사 본문, 오른쪽 장면 목차를 제공합니다. Pagefind로 제목과 대사 전문을 검색하고 검색 결과에서 해당 장면으로 이동할 수 있습니다. 목록의 제목/ID 검색과 분류 필터, 같은 분류의 이전·다음 퀘스트, 밝은/어두운 테마, 대사 번호 표시, 원본 TXT 다운로드도 지원합니다. 이전·다음은 같은 분류 안의 퀘스트 ID 순서이며 이야기의 시간 순서를 뜻하지 않습니다.

## 자료 범위

사용자 제공 한국어 퀘스트 자료 중 한국어 제목과 대사가 있는 항목을 수록했습니다. 버전은 대화 식별자 등 추출 자료를 근거로 분류한 것으로 최초 출시 버전을 보장하지 않습니다. 버전과 임무 종류를 확인할 수 없는 경우 해당 표시를 유지합니다. 장면 번호는 추출 자료의 순서입니다.

## 권리와 출처

대사와 게임 콘텐츠의 권리는 KURO GAMES 등 해당 권리자에게 있습니다. 공식 서비스가 아닙니다. 공개 접근 가능 여부는 재게시 이용허락을 의미하지 않으며, 원문 전체의 재게시를 명시적으로 허용하는 이용허락은 확인되지 않았습니다. 게임 콘텐츠에 오픈 라이선스를 부여하지 않습니다.

공식 팬 콘텐츠 가이드라인: https://wutheringwaves.kurogames.com/p/en/produce.html

## 정적 게시

게시된 결과는 HTML·CSS·JavaScript와 검색 인덱스로 이루어진 정적 사이트입니다. 저장소의 `main` 브랜치 루트를 GitHub Pages 소스로 사용하며 `.nojekyll`을 포함합니다.

## 재생성

Node.js 22.12 이상을 사용합니다. `source/`에 Astro와 Starlight의 버전을 고정한 빌드 소스와 잠금 파일을 보관합니다. `content-manifest.json`과 `originals/`가 퀘스트 원본이며, 생성기는 각 TXT의 SHA-256을 확인하고 문서·분류를 생성합니다.

```sh
cd source
npm ci --ignore-scripts
npm run build
npm run deploy:files
```

빌드 결과 `source/dist/`를 검증한 뒤 `deploy:files`로 저장소 루트에 반영합니다. `node_modules/`와 생성 중간 파일은 추적하지 않습니다. Starlight와 Pagefind의 라이선스는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 보관합니다. 게임 대사에는 해당 오픈소스 라이선스가 적용되지 않습니다.
