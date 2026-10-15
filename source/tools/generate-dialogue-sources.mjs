import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {readerFrame,readerDisclosure} from '../src/lib/reading-kit/reader.mjs';
import {dialogueSourceRows} from '../src/lib/dialogue-source-rows.mjs';
import {validateRandomFlowReferences,randomFlowDisclosure} from '../src/lib/random-flow-references.mjs';

const source=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),site=path.dirname(source),base='/wuwa-quests';
const data=JSON.parse(await readFile(path.join(site,'settings/dialogue-attribution.json'),'utf8'));
const native=JSON.parse(await readFile(path.join(site,'settings/native-sequence-references.json'),'utf8'));
const compiled=JSON.parse(await readFile(path.join(site,'settings/compiled-sequence-references.json'),'utf8'));
const randomFlows=validateRandomFlowReferences(JSON.parse(await readFile(path.join(site,'settings/random-flow-references.json'),'utf8')),data);
const reading=JSON.parse(await readFile(path.join(source,'src/data/quest-reading-navigation.json'),'utf8'));
const content=path.join(source,'src/content/docs'),out=path.join(content,'dialogue-sources');
await mkdir(out,{recursive:true});await mkdir(path.join(source,'public/dialogue-sources'),{recursive:true});
const H=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])).replace(/\r/g,'&#13;').replace(/\n/g,'&#10;');
const labels={quest:'목록 밖 임무',level:'탐색·전투',entity:'현장 상호작용',config:'공용 상호작용',unreferenced:'연결 미확인'};
const heading=(title,description)=>`---\ntitle: ${JSON.stringify(title)}\ndescription: ${JSON.stringify(description)}\n---\n\n`;
function compiledDisclosure(stateKey,reference){
 const matches=(compiled.states[stateKey]?.compiledSequenceReferences||[]).filter(ref=>ref.nativeSectionProof===reference.nativeSectionProof&&ref.talkItemPointer===reference.talkItemPointer&&ref.talkId===reference.talkId&&ref.speakerId===reference.speakerId&&ref.textId===reference.textId);
 if(matches.length>1)throw Error('Repeated compiled/native reference identity');
 if(!matches.length)return '';
 const ref=matches[0],proof=compiled.proofs[ref.compiledProof],section=native.proofs[reference.nativeSectionProof];
 if(!proof||proof.source!==section.source||proof.targetExportIndex!==section.exportIndex||proof.targetClass!==section.class||proof.fields.DialogueKey.value.source_string!==reference.textId||proof.fields.DialogueID.value.source_string!==String(reference.talkId)||proof.fields.SpeakerID.value!==reference.speakerId)throw Error('Compiled/native source identity differs');
 const body=`<div data-compiled-proof="${H(ref.compiledProof)}" data-compiled-native-section="${H(ref.nativeSectionProof)}" data-compiled-flow-talk="${H(ref.talkId)}" data-compiled-flow-text="${H(ref.textId)}"><p>같은 자료 키·대사 ID·화자를 담은 컴파일 템플릿이 위 대사 구간을 가리킵니다.</p><p><strong>${H(proof.source.split('/').at(-1))}</strong> · 템플릿 ${H(proof.compiledExportIndex)} · 대사 구간 ${H(proof.targetExportIndex)}</p><pre>${H(JSON.stringify(proof,null,2))}</pre></div>`;
 return readerDisclosure('컴파일된 연출 자료',body,{className:'quest-scene-info',attributes:{'data-pagefind-ignore':'all'}});
}
for(const group of data.groups){
 const title=group.title+' · 대화와 기록';
 let body=heading(title,group.title+'의 대사·선택지와 '+group.states.length+'개 대화 상태의 원문 기록');
 body+=`<p class="lore-kicker">${H(group.kinds.map(k=>labels[k]).join(' · '))}</p><p class="lore-lead">${H(group.excerpt)}</p>`;
 body+=`<nav class="lore-actions" aria-label="원문 탐색" data-pagefind-ignore><a href="${base}/dialogue-sources.html">현장 대화 목록으로</a><span>${group.states.length}개 대화 상태 · ${group.rows}개 원문 행</span></nav>`;
 const readingGroup=reading.groups[group.id];
 if(readingGroup.owners.length)body+=`<nav class="lore-actions" aria-label="임무 소속으로 읽기" data-pagefind-ignore>${readingGroup.owners.map(k=>`<a href="${base}/${reading.owners[k].url}" data-reading-context-link>${H(reading.owners[k].title)} · 임무 소속 원문</a>`).join('')}</nav>`;
 body+=`<div class="quest-actions" data-pagefind-ignore><a href="${base}/quest-sources.html">임무 소속 원문 목록</a></div>`;
 body+=`<aside class="quest-supplement-notice" data-pagefind-ignore><p>선택과 진행 상태에 따른 원문을 함께 읽습니다. 아래 수록 순서는 실제 플레이 순서와 다를 수 있습니다.${group.kinds.includes('unreferenced')?' 호출 대상을 확인하지 못한 대화에는 연결 미확인 표시가 있습니다.':''}${group.review?' 원자료에 시험 표기가 포함된 자료입니다. 실제 사용 여부는 확인되지 않았습니다.':''}</p></aside>`;
 for(const key of group.states){
  const state=data.states[key],anchor='state-'+crypto.createHash('sha256').update(key).digest('hex').slice(0,16);
  const speakers=[...new Set(state.rows.filter(r=>r.status==='OK'&&r.kind==='대사').map(r=>r.speaker))].slice(0,2);
  const named=Object.keys(state.owners).map(k=>data.owners[k]).filter(o=>o.kind==='quest'&&o.title&&o.type!==100);
  const sectionTitle=named.length?named[0].title:speakers.join(' · ')||'화면 문구와 기록';
  body+=`\n\n<div id="${anchor}" class="quest-section-anchor" aria-hidden="true"></div>\n\n## ${H(sectionTitle)}\n\n`;
  let transcript=`<p class="quest-reading-note" data-pagefind-ignore>${H(labels[state.classification])}</p>`;
  transcript+=dialogueSourceRows(state,anchor);
  const ownerList=Object.entries(state.owners).map(([owner,evidence])=>{
   const info=data.owners[owner];
   const typed=info.encoding==='typed_fields'?`<p>이 설정은 아래 필드의 값으로 대화 상태를 참조합니다.</p><pre>${H(JSON.stringify({fields:info.schema_fields,values:info.native_values,encoding:info.reference_encoding,schema:info.schema_source,schema_sha256:info.schema_sha256,source_sha256:info.blob_sha256,...(info.consumer?{consumer:info.consumer.file,consumer_sha256:info.consumer.sha256,reference:info.consumer.required_expression}:{})},null,2))}</pre>`:'';
   return `<li>${H(info.title||({quest:'이름 미확인 임무',level:'이름 미확인 탐색 콘텐츠',entity:'인물·사물 배치',config:'공용 상호작용 설정'}[info.kind]))}${info.published?` · <a href="${base}/quests/${info.id}.html">퀘스트 본문</a>`:''}<pre>${H(owner+'\n'+evidence.proof.join('\n→ '))}</pre>${typed}</li>`;
  }).join('');
  const rows=state.rows.map(row=>({text_id:row.text_id,locale_db:row.source,kind:row.kind,speaker_id:row.speaker_id,talk_id:row.talk_id,option:row.option,action_path:row.action_path,status:row.status,raw:row.raw}));
  const nativeState=native.states[key];
  const nativeDisclosure=nativeState?readerDisclosure('네이티브 연출의 원문 참조',`<div data-native-sequence-state="${H(key)}"><p>연출 파일의 대사 ID·화자 ID·문자열 키가 이 원문과 일치합니다. 이 연출을 호출하는 임무·지역은 확인되지 않았습니다.</p><pre>${H(JSON.stringify({sequenceDataAsset:nativeState.sequenceDataAsset,sourceActionPointer:nativeState.sourceActionPointer,sourceFieldPointer:nativeState.sourceFieldPointer,flowBlobSha256:nativeState.flowBlobSha256},null,2))}</pre><ul>${nativeState.nativeSequenceReferences.map(ref=>`<li data-native-section="${H(ref.nativeSectionProof)}" data-native-flow-talk="${H(ref.talkId)}" data-native-flow-text="${H(ref.textId)}"><p>대사 ${H(ref.talkId)} · ${H(ref.textId)}</p><pre>${H(JSON.stringify({reference:ref,section:native.proofs[ref.nativeSectionProof],objectChain:ref.nativeObjectPointerChain.map(k=>native.proofs[k])},null,2))}</pre>${compiledDisclosure(key,ref)}</li>`).join('')}</ul></div>`,{className:'quest-scene-info',attributes:{'data-pagefind-ignore':'all'}}):'';
  const connectionNote=state.owners&&Object.keys(state.owners).length?'설정의 명시 참조와 대화 호출로 연결된 자료입니다. 실행 조건과 출시 시점은 확인되지 않았습니다.':randomFlows.states[key]?'조건부 말풍선 연결은 위에 표시했습니다. 실제 실행과 임무·지역 소속은 미확인입니다.':'원문과 문자열 키를 확인했으며 호출 대상은 확인되지 않았습니다.';
  const proof=`<p>${connectionNote}</p><pre>${H(key)}</pre><ul>${ownerList}</ul><pre>${H(JSON.stringify(rows,null,2))}</pre>`;
  transcript+=nativeDisclosure;
  transcript+=randomFlowDisclosure(randomFlows,key,data);
  transcript+=readerDisclosure('원문·연결 근거',proof,{className:'quest-scene-info',attributes:{'data-pagefind-ignore':'all'}});
  body+=`<section data-dialogue-state="${H(key)}">${readerFrame(transcript,{variant:'transcript',className:'quest-reader'})}</section>`;
 }
 if(group.existing_scenes?.length)body+=`\n\n## 같은 대화 자료의 기존 장면\n\n<p>같은 원자료 묶음에서 확인한 퀘스트 장면입니다. 대화의 앞뒤와 다른 진행 상태를 함께 읽을 수 있습니다.</p><ul>${group.existing_scenes.map(scene=>`<li><a href="${base}/quests/${scene.quest_id}.html#scene-${scene.scene}">${H(scene.title)} · 장면 ${scene.scene}</a></li>`).join('')}</ul>`;
 await writeFile(path.join(out,group.id+'.md'),body+'\n');
}
const catalog=data.groups.map(group=>({...group,ownerTitles:reading.groups[group.id].ownerTitles,ownerIds:reading.groups[group.id].ownerIds,ownerReaders:reading.groups[group.id].owners.map(k=>({id:reading.owners[k].id,title:reading.owners[k].title,page:`${base}/${reading.owners[k].url}`})),page:`${base}/dialogue-sources/${group.id}.html`}));
const catalogRaw=JSON.stringify(catalog),version=crypto.createHash('sha256').update(catalogRaw).digest('hex').slice(0,12);
await writeFile(path.join(source,'public/dialogue-sources/catalog.json'),catalogRaw+'\n');
const script=await readFile(path.join(source,'public/dialogue-sources/catalog.js'),'utf8');
const scriptVersion=crypto.createHash('sha256').update(script).digest('hex').slice(0,12);
const intro=heading('현장 대화와 기록','지역의 인물·사물, 탐색·전투, 목록 밖 임무에 연결된 한국어 대사와 선택지를 찾아 읽습니다.')+`<p class="lore-lead">지역의 인물과 사물, 탐색과 전투, 목록 밖 임무에 남아 있는 대화와 기록입니다.</p><p>이름과 첫 문장으로 찾아 읽거나, 상단 검색에서 본문 전체를 찾을 수 있습니다. 임무의 실행 순서와 실제 사용 여부는 확인된 범위에서 표시합니다.</p><div id="dialogue-catalog" data-catalog="${base}/dialogue-sources/catalog.json?v=${version}" data-pagefind-ignore><div class="dialogue-source-filters"><label>임무·인물·첫 문장<input id="dialogue-query" type="search" placeholder="임무·인물 이름 또는 문구" /></label><label>자료 종류<select id="dialogue-kind"><option value="connected">연결을 확인한 자료</option><option value="quest">목록 밖 임무</option><option value="level">탐색·전투</option><option value="entity">현장 상호작용</option><option value="config">공용 상호작용</option><option value="unreferenced">연결 미확인</option><option value="all">모든 자료</option></select></label><label class="dialogue-source-check"><input id="dialogue-hide-review" type="checkbox" checked />시험 표기 자료 숨기기</label><button id="dialogue-reset" type="button">초기화</button></div><p id="dialogue-status" role="status" aria-live="polite">원문 목록을 불러오는 중입니다.</p><div id="dialogue-results" class="dialogue-source-results"></div><button id="dialogue-more" type="button" hidden>더 보기</button></div><noscript><ul>${catalog.map(g=>`<li><a href="${g.page}">${H(g.title)}</a> · ${H(g.excerpt)}${g.ownerReaders.length?`<ul>${g.ownerReaders.map(o=>`<li><a href="${o.page}">${H(o.title)}</a></li>`).join('')}</ul>`:''}</li>`).join('')}</ul></noscript><script src="${base}/dialogue-sources/catalog.js?v=${scriptVersion}" defer></script>\n`;
await writeFile(path.join(content,'dialogue-sources.md'),intro);
console.log('Dialogue original sources: '+data.groups.length+' groups / '+data.summary.readable_rows+' readable rows');
