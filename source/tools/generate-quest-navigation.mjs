import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {deriveQuestReadingContext} from '../src/lib/quest-reading-context.mjs';
import {dialogueSourceRows,H} from '../src/lib/dialogue-source-rows.mjs';
import {readerFrame,readerDisclosure} from '../src/lib/reading-kit/reader.mjs';
export async function generateQuestNavigation({source,site,catalog,questScenes}){
 const attribution=JSON.parse(await readFile(path.join(site,'settings/dialogue-attribution.json'),'utf8'));
 const model=deriveQuestReadingContext(attribution,catalog,questScenes);
 const data=path.join(source,'src/data');await mkdir(data,{recursive:true});
 await writeFile(path.join(data,'quest-reading-navigation.json'),JSON.stringify(model)+'\n');
 const out=path.join(source,'src/content/docs/quest-sources');await mkdir(out,{recursive:true});
 const base='/wuwa-quests',owners=Object.values(model.owners),head=(title,description)=>`---\ntitle: ${JSON.stringify(title)}\ndescription: ${JSON.stringify(description)}\n---\n\n`;
 for(const owner of owners){
  let body=head(owner.title,owner.title+' 설정이 참조하는 한국어 원문을 한 공간에서 읽습니다.');
  body+=`<p class="lore-kicker">임무 소속 원문</p><p class="lore-lead">${H(owner.title)} 설정에서 명시적으로 참조하는 대화와 기록입니다.</p><nav class="lore-actions quest-actions" aria-label="원문 탐색" data-pagefind-ignore><a href="${base}/quest-sources.html">임무 소속 원문 목록</a><span>${owner.states.length}개 원문 상태</span></nav><aside class="quest-supplement-notice"><p>설정의 소유 참조를 확인한 원문입니다. 전체 임무가 수록되었는지, 실제 실행 조건과 진행 순서는 확인 중입니다.</p></aside>`;
  for(const node of owner.states){
   const state=attribution.states[node.key],group=model.groups[node.groupId];
   const coowners=node.key&&Object.keys(state.owners).filter(k=>model.owners[k]);
   let transcript=dialogueSourceRows(state,node.anchor);
   transcript+=`<nav class="lore-actions" aria-label="원래 자료와 함께 읽기" data-pagefind-ignore><a href="${base}/${group.url}#${node.anchor}" data-reading-context-link>원래 자료 묶음에서 읽기</a>${coowners.filter(k=>k!==owner.key).map(k=>`<a href="${base}/${model.owners[k].url}#${node.anchor}" data-reading-context-link>${H(model.owners[k].title)}의 참조</a>`).join('')}</nav>`;
   const allOwners=Object.entries(state.owners).map(([key,evidence])=>({owner:key,kind:attribution.owners[key].kind,title:attribution.owners[key].title||null,chain:evidence.proof}));
   transcript+=readerDisclosure('원문과 임무 소속 근거',`<p>설정의 명시적 참조로 연결한 상태입니다. 실제 발화 시점과 출시 판본은 확인 중입니다.</p><pre>${H(JSON.stringify({owner:owner.key,state:node.key,chain:node.proof,allOwners,source_databases:attribution.source_databases,rows:state.rows},null,2))}</pre>`,{className:'quest-scene-info',attributes:{'data-pagefind-ignore':'all'}});
   body+=`\n\n<div id="${node.anchor}" class="quest-section-anchor" aria-hidden="true"></div>\n\n## ${H(node.title)}\n\n<section data-dialogue-state="${H(node.key)}" data-quest-source-owner="${H(owner.key)}">${readerFrame(transcript,{variant:'transcript',className:'quest-reader'})}</section>`;
  }
  await writeFile(path.join(out,owner.id+'.md'),body+'\n');
 }
 const index=head('임무 소속 원문','설정의 소유 참조와 한국어 이름을 확인한 임무의 대화와 기록입니다.')+`<p class="lore-lead">설정에 기록된 임무의 이름에서 대화와 기록으로 이어집니다.</p><p>기존 퀘스트 목록 밖에서 소유 참조를 확인한 원문입니다. 전체 임무의 수록 여부와 진행 순서는 확인 중입니다.</p><nav class="lore-actions"><a href="${base}/index.html">퀘스트 목록</a><a href="${base}/dialogue-sources.html">현장 대화와 기록</a></nav><ul class="quest-owner-index">${owners.map(o=>`<li><a href="${base}/${o.url}">${H(o.title)}</a><span> · ${o.states.length}개 원문 상태</span></li>`).join('')}</ul>`;
 await writeFile(path.join(source,'src/content/docs/quest-sources.md'),index+'\n');
 return {model,attribution};
}
