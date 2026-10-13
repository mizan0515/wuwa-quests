/** Derive reading routes from exact existing source relations, never ID/name guesses. */
import {createHash} from 'node:crypto';
export const stateAnchor=key=>'state-'+createHash('sha256').update(key).digest('hex').slice(0,16);
export function deriveQuestReadingContext(attribution,catalog,questScenes={}){
 const quests=Object.fromEntries(catalog.map(q=>[String(q.id),{id:String(q.id),title:q.title,version:q.version,type:q.type,url:'quests/'+q.id+'.html',scenes:questScenes[q.id]||[],relatedSources:[]} ]));
 const eligible=Object.entries(attribution.owners).filter(([,o])=>o.kind==='quest'&&o.title?.trim()&&o.type!==100&&!quests[String(o.id)]);
 const owners=Object.fromEntries(eligible.map(([key,o])=>[key,{key,id:String(o.id),title:o.title,type:o.type,url:'quest-sources/'+o.id+'.html',states:[]} ]));
 const groups={};
 for(const g of attribution.groups){
  const allOwnerKeys=[...new Set(g.states.flatMap(k=>Object.keys(attribution.states[k].owners)))];
  const namedOwners=allOwnerKeys.filter(k=>owners[k]);
  const searchableOwners=allOwnerKeys.map(k=>attribution.owners[k]).filter(o=>o.kind==='quest'&&o.title?.trim()&&o.type!==100);
  const existing=g.existing_scenes||[],relatedQuests=[];
  for(const edge of existing){
   const quest=quests[String(edge.quest_id)];if(!quest)throw Error('Same-source quest absent from manifest');
   let entry=quest.relatedSources.find(s=>s.id===g.id);
   if(!entry){entry={id:g.id,title:g.title,url:'dialogue-sources/'+g.id+'.html',relation:'SAME_SOURCE_CONTEXT',scenes:[]};quest.relatedSources.push(entry);}
   entry.scenes.push({number:edge.scene,stateKey:edge.state_key,url:quest.url+'#scene-'+edge.scene});
   let inverse=relatedQuests.find(q=>q.id===quest.id);
   if(!inverse){inverse={id:quest.id,title:quest.title,url:quest.url,relation:'SAME_SOURCE_CONTEXT',scenes:[]};relatedQuests.push(inverse);}
   inverse.scenes.push({number:edge.scene,url:quest.url+'#scene-'+edge.scene});
  }
  const nodes=g.states.map(key=>{
   const state=attribution.states[key],keys=Object.keys(state.owners).filter(k=>owners[k]);
   const speakers=[...new Set(state.rows.filter(r=>r.status==='OK'&&r.kind==='대사').map(r=>r.speaker))];
   const title=speakers.slice(0,2).join(' · ')||'화면 문구와 기록';
   const first=state.rows.find(r=>r.status==='OK'&&r.text?.trim()),excerpt=first?Array.from(first.text.replace(/\s+/g,' ')).slice(0,42).join(''):'';
   const label=excerpt?`${first.speaker&&first.speaker!=='화자 미지정'?first.speaker+' · ':''}${excerpt}${Array.from(first.text.replace(/\s+/g,' ')).length>42?'…':''}`:title;
   const rowIndices=state.rows.flatMap((r,i)=>r.status==='OK'?[i]:[]);
   for(const ownerKey of keys){if(!Array.isArray(state.owners[ownerKey].proof)||!state.owners[ownerKey].proof.length)throw Error('Owned state has no source chain');owners[ownerKey].states.push({key,groupId:g.id,anchor:stateAnchor(key),title,label,rowIndices,proof:state.owners[ownerKey].proof});}
   return {key,anchor:stateAnchor(key),title,label,owners:keys,rowIndices};
  });
  groups[g.id]={id:g.id,title:g.title,url:'dialogue-sources/'+g.id+'.html',states:nodes,owners:namedOwners,ownerTitles:searchableOwners.map(o=>o.title),ownerIds:searchableOwners.map(o=>String(o.id)),relatedQuests};
 }
 return {schema:'wuwa-quest-reading-navigation.v1',quests,groups,owners,counts:{quests:Object.keys(quests).length,groups:Object.keys(groups).length,owners:Object.keys(owners).length,sameSourcePairs:Object.values(quests).reduce((n,q)=>n+q.relatedSources.length,0),sameSourceSceneReferences:Object.values(quests).reduce((n,q)=>n+q.relatedSources.reduce((m,g)=>m+g.scenes.length,0),0)}};
}

export {safeReadingReturn} from './reading-return.mjs';
