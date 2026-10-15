import {readerDisclosure} from './reading-kit/reader.mjs';
import {H} from './dialogue-source-rows.mjs';

const labels={ambient:'주변 대화',action:'행동에 연결된 대화',hit:'피격 반응',monster:'주변의 적에 대한 반응'};
export function validateRandomFlowReferences(data,original){
 if(data.schema!=='wuwa-random-flow-references.v1')throw Error('Unknown conditional Flow schema');
 const seen=new Set();
 for(const [key,refs]of Object.entries(data.states)){
  if(!original.states[key]?.readable||!refs.length||new Set(refs).size!==refs.length)throw Error('Invalid conditional original state');
  for(const id of refs){
   const r=data.references[id];
   if(!r||!labels[r.consumer]||r.runtimeObserved!==false||r.selection.mode!=='random-state'||r.input.StateId||!r.targets.includes(key))throw Error('Invalid conditional consumer relation');
   if(r.targets.some(t=>!original.states[t]?.readable))throw Error('Conditional reference has no original');
   if(r.owners||r.questId||r.speaker||r.region)throw Error('Conditional consumer inferred an owner or speaker');
   seen.add(id);
  }
 }
 if(seen.size!==Object.keys(data.references).length)throw Error('Unlinked conditional reference');
 return data;
}

export function randomFlowDisclosure(data,key,original){
 const ids=data.states[key];if(!ids?.length)return '';
 const state=original.states[key];
 const speakers=[...new Set(state.rows.filter(r=>r.status==='OK').map(r=>r.speaker).filter(Boolean))];
 const recipient=(r,id)=>original.owners[`entity:${r.source.mapId}:${id}`]?.title||`배치 ${id}`;
 const entry=id=>{
  const r=data.references[id],targets=r.recipientEntityIds.map(id=>recipient(r,id)).join(' · ');
  const rate=['hit','monster'].includes(r.consumer)?r.conditions.find(c=>c.pointer.endsWith('/BubbleRate'))?.value:undefined;
  const detail=`<p>원문 화자: ${H(speakers.join(' · ')||'미확인')}</p><p>말풍선 표시 대상: ${H(targets)}</p>${rate!==undefined?`<p>설정된 말풍선 확률: ${H(rate)}%</p>`:''}<p>대상 배치 번호: ${H(r.recipientEntityIds.join(' · '))}</p><pre data-random-flow-proof="${H(id)}">${H(JSON.stringify(r,null,2))}</pre>`;
  return `<li data-random-flow-reference="${H(id)}"><p><strong>${H(labels[r.consumer])}</strong> · ${H(targets)}</p>${readerDisclosure('설정의 조건과 원문 위치',detail,{attributes:{'data-pagefind-ignore':'all'}})}</li>`;
 };
 const first=ids.slice(0,5).map(entry).join(''),rest=ids.slice(5);
 const body=`<div data-random-flow-state="${H(key)}"><p>이 원문은 대화 상태를 골라 표시하는 말풍선 설정에 연결됩니다. 실제 표시는 행동·거리·진행 상태와 설정된 확률에 따라 달라집니다.</p><p>원문에 기록된 화자와 말풍선 표시 대상은 각각 보존했습니다. 실제 플레이에서 표시된 시점은 미확인입니다.</p><ul>${first}</ul>${rest.length?readerDisclosure(`다른 연결 설정 ${rest.length}개`, `<ul>${rest.map(entry).join('')}</ul>`):''}</div>`;
 return readerDisclosure('말풍선 연결 · 조건부',body,{className:'quest-scene-info',attributes:{'data-pagefind-ignore':'all'}});
}
