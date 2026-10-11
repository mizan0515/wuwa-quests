import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {readerFrame,readerDisclosure,rowAttributes,htmlAttributes} from '../src/lib/reading-kit/reader.mjs';

const source=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),site=path.dirname(source),base='/wuwa-quests';
const data=JSON.parse(await readFile(path.join(site,'settings/dialogue-attribution.json'),'utf8'));
const content=path.join(source,'src/content/docs'),out=path.join(content,'dialogue-sources');
await mkdir(out,{recursive:true});await mkdir(path.join(source,'public/dialogue-sources'),{recursive:true});
const H=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])).replace(/\r/g,'&#13;').replace(/\n/g,'&#10;');
const labels={quest:'목록 밖 임무',level:'탐색·전투',entity:'현장 상호작용',config:'공용 상호작용',unreferenced:'연결 미확인'};
const heading=(title,description)=>`---\ntitle: ${JSON.stringify(title)}\ndescription: ${JSON.stringify(description)}\n---\n\n`;
for(const group of data.groups){
 const title=group.title+' · 대화와 기록';
 let body=heading(title,group.title+'의 대사·선택지와 '+group.states.length+'개 대화 상태의 원문 기록');
 body+=`<p class="lore-kicker">${H(group.kinds.map(k=>labels[k]).join(' · '))}</p><p class="lore-lead">${H(group.excerpt)}</p>`;
 body+=`<nav class="lore-actions" aria-label="원문 탐색" data-pagefind-ignore><a href="${base}/dialogue-sources.html">현장 대화 목록으로</a><span>${group.states.length}개 대화 상태 · ${group.rows}개 원문 행</span></nav>`;
 body+=`<aside class="quest-supplement-notice" data-pagefind-ignore><p>선택과 진행 상태에 따른 원문을 함께 읽습니다. 아래 수록 순서는 실제 플레이 순서와 다를 수 있습니다.${group.kinds.includes('unreferenced')?' 호출 대상을 확인하지 못한 대화에는 연결 미확인 표시가 있습니다.':''}${group.review?' 원자료에 시험 표기가 포함된 자료입니다. 실제 사용 여부는 확인되지 않았습니다.':''}</p></aside>`;
 for(const key of group.states){
  const state=data.states[key],anchor='state-'+crypto.createHash('sha256').update(key).digest('hex').slice(0,16);
  const speakers=[...new Set(state.rows.filter(r=>r.status==='OK'&&r.kind==='대사').map(r=>r.speaker))].slice(0,2);
  const named=Object.keys(state.owners).map(k=>data.owners[k]).filter(o=>o.kind==='quest'&&o.title&&o.type!==100);
  const sectionTitle=named.length?named[0].title:speakers.join(' · ')||'화면 문구와 기록';
  body+=`\n\n<div id="${anchor}" class="quest-section-anchor" aria-hidden="true"></div>\n\n## ${H(sectionTitle)}\n\n`;
  let transcript=`<p class="quest-reading-note" data-pagefind-ignore>${H(labels[state.classification])}</p>`;
  for(const [index,row] of state.rows.entries()){
   if(row.status!=='OK')continue;
   const attrs=rowAttributes(row.kind==='선택지'?'choice':'dialogue');
   attrs.class+=' quest-source-line '+(row.kind==='선택지'?'quest-choice':'quest-utterance');
   attrs.id=anchor+'-row-'+index;attrs['data-dialogue-source-key']=row.text_id;
   transcript+=`<p ${htmlAttributes(attrs)}><strong class="quest-speaker">${H(row.speaker)}</strong><span class="quest-speech rw-source-body">${H(row.text)}</span></p>`;
   if(row.transition){const branch=rowAttributes('branch');branch.class+=' quest-branch';transcript+=`<p ${htmlAttributes(branch)}>${H(row.transition)}</p>`;}
  }
  const ownerList=Object.entries(state.owners).map(([owner,evidence])=>{
   const info=data.owners[owner];return `<li>${H(info.title||({quest:'이름 미확인 임무',level:'이름 미확인 탐색 콘텐츠',entity:'인물·사물 배치',config:'공용 상호작용 설정'}[info.kind]))}${info.published?` · <a href="${base}/quests/${info.id}.html">퀘스트 본문</a>`:''}<pre>${H(owner+'\n'+evidence.proof.join('\n→ '))}</pre></li>`;
  }).join('');
  const rows=state.rows.map(row=>({text_id:row.text_id,locale_db:row.source,kind:row.kind,speaker_id:row.speaker_id,talk_id:row.talk_id,option:row.option,action_path:row.action_path,status:row.status,raw:row.raw}));
  const proof=`<p>${state.owners&&Object.keys(state.owners).length?'설정의 명시 참조와 대화 호출로 연결된 자료입니다. 실행 조건과 출시 시점은 확인되지 않았습니다.':'원문과 문자열 키를 확인했으며 호출 대상은 확인되지 않았습니다.'}</p><pre>${H(key)}</pre><ul>${ownerList}</ul><pre>${H(JSON.stringify(rows,null,2))}</pre>`;
  transcript+=readerDisclosure('원문·연결 근거',proof,{className:'quest-scene-info',attributes:{'data-pagefind-ignore':'all'}});
  body+=`<section data-dialogue-state="${H(key)}">${readerFrame(transcript,{variant:'transcript',className:'quest-reader'})}</section>`;
 }
 if(group.existing_scenes?.length)body+=`\n\n## 같은 대화 자료의 기존 장면\n\n<p>같은 원자료 묶음에서 확인한 퀘스트 장면입니다. 대화의 앞뒤와 다른 진행 상태를 함께 읽을 수 있습니다.</p><ul>${group.existing_scenes.map(scene=>`<li><a href="${base}/quests/${scene.quest_id}.html#scene-${scene.scene}">${H(scene.title)} · 장면 ${scene.scene}</a></li>`).join('')}</ul>`;
 await writeFile(path.join(out,group.id+'.md'),body+'\n');
}
const catalog=data.groups.map(group=>({...group,page:`${base}/dialogue-sources/${group.id}.html`}));
const catalogRaw=JSON.stringify(catalog),version=crypto.createHash('sha256').update(catalogRaw).digest('hex').slice(0,12);
await writeFile(path.join(source,'public/dialogue-sources/catalog.json'),catalogRaw+'\n');
const script=await readFile(path.join(source,'public/dialogue-sources/catalog.js'),'utf8');
const scriptVersion=crypto.createHash('sha256').update(script).digest('hex').slice(0,12);
const intro=heading('현장 대화와 기록','지역의 인물·사물, 탐색·전투, 목록 밖 임무에 연결된 한국어 대사와 선택지를 찾아 읽습니다.')+`<p class="lore-lead">지역의 인물과 사물, 탐색과 전투, 목록 밖 임무에 남아 있는 대화와 기록입니다.</p><p>이름과 첫 문장으로 찾아 읽거나, 상단 검색에서 본문 전체를 찾을 수 있습니다. 임무의 실행 순서와 실제 사용 여부는 확인된 범위에서 표시합니다.</p><div id="dialogue-catalog" data-catalog="${base}/dialogue-sources/catalog.json?v=${version}" data-pagefind-ignore><div class="dialogue-source-filters"><label>이름·첫 문장<input id="dialogue-query" type="search" placeholder="인물 이름 또는 문구" /></label><label>자료 종류<select id="dialogue-kind"><option value="connected">연결을 확인한 자료</option><option value="quest">목록 밖 임무</option><option value="level">탐색·전투</option><option value="entity">현장 상호작용</option><option value="config">공용 상호작용</option><option value="unreferenced">연결 미확인</option><option value="all">모든 자료</option></select></label><label class="dialogue-source-check"><input id="dialogue-hide-review" type="checkbox" checked />시험 표기 자료 숨기기</label><button id="dialogue-reset" type="button">초기화</button></div><p id="dialogue-status" role="status" aria-live="polite">원문 목록을 불러오는 중입니다.</p><div id="dialogue-results" class="dialogue-source-results"></div><button id="dialogue-more" type="button" hidden>더 보기</button></div><noscript><ul>${catalog.map(g=>`<li><a href="${g.page}">${H(g.title)}</a> · ${H(g.excerpt)}</li>`).join('')}</ul></noscript><script src="${base}/dialogue-sources/catalog.js?v=${scriptVersion}" defer></script>\n`;
await writeFile(path.join(content,'dialogue-sources.md'),intro);
console.log('Dialogue original sources: '+data.groups.length+' groups / '+data.summary.readable_rows+' readable rows');
