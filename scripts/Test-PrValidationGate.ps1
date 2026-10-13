#requires -Version 7.0
param([string]$Root=(Split-Path $PSScriptRoot -Parent),[int]$MaxTotalSeconds=600,[int]$ChildTimeoutSeconds=90,[switch]$PrePublish)
$ErrorActionPreference='Stop'
Push-Location (Join-Path $Root 'source')
try {
  & node tools/generate.mjs
  if($LASTEXITCODE -ne 0){throw 'Current quest navigation source generation failed'}
  & node --test tools/quest-reading-navigation.test.mjs
  if($LASTEXITCODE -ne 0){throw 'Quest connected reader semantic QA failed'}
  & python -B -X utf8 tools/verify_quest_reading_navigation.py
  if($LASTEXITCODE -ne 0){throw 'Quest source navigation and original preservation QA failed'}
  & python -B -X utf8 tools/verify_native_sequence_references.py --self-test
  if($LASTEXITCODE -ne 0){throw 'Native source consumer and independent negative QA failed'}
  & python -B -X utf8 tools/verify_compiled_sequence_references.py --project-root $Root --public-only
  if($LASTEXITCODE -ne 0){throw 'Compiled source overlay and semantic negative QA failed'}
  & python -B -X utf8 tools/test_quest_recovery.py
  if($LASTEXITCODE -ne 0){throw 'Quest source ownership regression QA failed'}
  & python -B -X utf8 tools/verify_quest_recovery.py
  if($LASTEXITCODE -ne 0){throw 'Recovered quest original and coverage QA failed'}
  & python -B -X utf8 tools/verify_dialogue_attribution.py
  if($LASTEXITCODE -ne 0){throw 'Unassigned dialogue source inventory QA failed'}
  & npm.cmd run build
  if($LASTEXITCODE -ne 0){throw 'Reading build failed'}
  & python -B -X utf8 tools/verify_quest_reading_navigation.py --dist dist
  if($LASTEXITCODE -ne 0){throw 'Whole rendered quest source navigation QA failed'}
  & python -B -X utf8 tools/verify_native_sequence_references.py --dist dist
  if($LASTEXITCODE -ne 0){throw 'Native consumer evidence and preserved static original QA failed'}
  & python -B -X utf8 tools/verify_compiled_sequence_references.py --project-root $Root --public-only --dist dist
  if($LASTEXITCODE -ne 0){throw 'Compiled source disclosure identity and rendered source QA failed'}
  & python -B -X utf8 tools/verify_dialogue_attribution.py --dist dist
  if($LASTEXITCODE -ne 0){throw 'Whole attributed dialogue original rendering QA failed'}
  & npm.cmd run qa:reading
  if($LASTEXITCODE -ne 0){throw 'Reading data QA failed'}
  & npm.cmd run qa:seo
  if($LASTEXITCODE -ne 0){throw 'Page metadata, canonical sitemap and story footer SEO QA failed'}
  & python -B -X utf8 tools/verify_editorial_sources.py --self-test
  if($LASTEXITCODE -ne 0){throw 'Whole editorial original and source meaning QA failed'}
  & python -B -X utf8 tools/verify_directory_discovery.py --self-test
  if($LASTEXITCODE -ne 0){throw 'Grouped directories, individual dossier originals and discovery QA failed'}
  & python -B -X utf8 tools/verify_directory_discovery.py
  if($LASTEXITCODE -ne 0){throw 'Rendered grouped directory and original dossier QA failed'}
  & python tools/verify_reading_site.py
  if($LASTEXITCODE -ne 0){throw 'Source and link QA failed'}
  & python -B -X utf8 ../tools/verify_cva_editorial.py --self-test
  if($LASTEXITCODE -ne 0){throw 'Whole CVA editorial and original reader QA failed'}
  & python tools/verify_original_rendering.py
  if($LASTEXITCODE -ne 0){throw 'Rendered original text QA failed'}
  & python tools/verify_people_catalog.py
  if($LASTEXITCODE -ne 0){throw 'People classification and original evidence QA failed'}
  & python tools/verify_game_images.py --dist dist
  if($LASTEXITCODE -ne 0){throw 'Game image source QA failed'}
  & python tools/verify_threnodian_site.py --dist dist
  if($LASTEXITCODE -ne 0){throw 'Threnodian source and relation QA failed'}
  if($PrePublish){
    Write-Output 'RESULT: PRE_PUBLISH_PASS (publication surface comparison pending)'
  } else {
    & python -B -X utf8 -m unittest discover -s tools -p test_pages_artifact.py
    if($LASTEXITCODE -ne 0){throw 'Actual Pages artifact inventory and original byte QA failed'}
    & python -B -X utf8 -m unittest tools/test_share_publication_ui.py
    if($LASTEXITCODE -ne 0){throw 'Shared publication UI boundary and inverse QA failed'}
    & python -B -X utf8 tools/share_publication_ui.py
    if($LASTEXITCODE -ne 0){throw 'Shared publication UI and exact original inverse failed'}
    & python tools/verify_published_site.py
    if($LASTEXITCODE -ne 0){throw 'Published files differ from build; run npm run deploy:files and include the generated output'}
    Write-Output 'RESULT: PASS'
  }
} finally {Pop-Location}
