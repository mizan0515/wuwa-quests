#requires -Version 7.0
param([string]$Root=(Split-Path $PSScriptRoot -Parent),[int]$MaxTotalSeconds=600,[int]$ChildTimeoutSeconds=90)
$ErrorActionPreference='Stop'
Push-Location (Join-Path $Root 'source')
try {
  & npm.cmd run build
  if($LASTEXITCODE -ne 0){throw 'Reading build failed'}
  & npm.cmd run qa:reading
  if($LASTEXITCODE -ne 0){throw 'Reading data QA failed'}
  & npm.cmd run qa:seo
  if($LASTEXITCODE -ne 0){throw 'Page metadata, canonical sitemap and story footer SEO QA failed'}
  & python -B -X utf8 tools/verify_editorial_sources.py --self-test
  if($LASTEXITCODE -ne 0){throw 'Whole editorial original and source meaning QA failed'}
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
  & python tools/verify_published_site.py
  if($LASTEXITCODE -ne 0){throw 'Published files differ from build; run npm run deploy:files and include the generated output'}
  Write-Output 'RESULT: PASS'
} finally {Pop-Location}
