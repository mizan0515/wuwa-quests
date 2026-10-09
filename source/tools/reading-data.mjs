import {createHash} from 'node:crypto';
import {writeFile,mkdir,readFile} from 'node:fs/promises';
import path from 'node:path';
import {createReadingGraph,resolveCluster} from '../src/lib/reading-kit/graph.mjs';
import {writeReadingGraph} from '../src/lib/reading-kit/write.mjs';
const hash=s=>createHash('sha256').update(s).digest('hex');
export function claimAttribution(item){
 const speaker=item.speaker||[...new Set((item.refs||[]).map(r=>r.speaker).filter(Boolean))].join(' · ');
 return {kind:item.kind==='reading'?'inference':speaker?'attributed':'explicit',speaker};
}
export const readingReferences=(rs,aliases={})=>(rs||[]).map(r=>r.quest_id?{sourceId:'quest-'+r.quest_id,anchor:'scene-'+r.scene,quote:r.quote,title:r.title||r.label,speaker:r.speaker||''}:{sourceId:aliases[r.id]||r.id,field:r.field,quote:r.excerpt,title:r.label,sourceSha256:r.source_text_sha256,speaker:r.speaker||''});
// A node's role in one record can be more specific than its canonical class.
// These are existing editorial labels, not classifications inferred from names.
const kindFamilies=new Map([
 ['인물',['인물','야귀군 지휘자','단장','타오르는 벚꽃의 무녀','성녀','출신 인물','간부','회장','변형된 인간']],
 ['지역',['지역','장소','주','상위 지역','도시','중심지','시련의 땅','천연 장벽','지하 오아시스','체류 지역','지표 지역']],
 ['세력',['세력','가문','조직','군대','용병 조직','연구 부서','병합된 조직','교육·연구']],
 ['수호신',['수호신']],
 ['세계관',['세계관','큰 설정','세계','개념','명식','잔상','재앙','재난','현상']]
].flatMap(([family,labels])=>labels.map(label=>[label,family])));
export function entityKindIndex({index,atlas,book}){
 const canonical=new Map(),declared=new Map();
 const addCanonical=(name,kind)=>{
  const old=canonical.get(name);
  if(old&&old!==kind){
   // A profile and a guardian dossier describe the same named source subject.
   if(new Set([old,kind]).has('인물')&&new Set([old,kind]).has('수호신')){canonical.set(name,'인물');return;}
   throw Error('Conflicting canonical entity kinds: '+name+' / '+old+' / '+kind);
  }
  canonical.set(name,kind);
 };
 for(const p of index.characters)addCanonical(p.name,'인물');
 for(const [group,kind] of [['people','인물'],['regions','지역'],['cosmology','세계관'],['factions','세력'],['sentinels','수호신']])
  for(const c of atlas[group]||[])addCanonical(c.title.split(' · ')[0],kind);
 for(const group of ['people','regions','cosmology','factions','sentinels'])for(const c of atlas[group]||[])
  for(const n of c.nodes||[]){
   if(!n.name||typeof n.kind!=='string'||!n.kind.trim())throw Error('Entity node lacks a declared kind: '+c.id);
   if(!declared.has(n.name))declared.set(n.name,new Set());
   declared.get(n.name).add(n.kind);
  }
 const resolved=new Map(canonical);
 for(const [name,labels] of declared){
  const families=new Set([...labels].map(kind=>kindFamilies.get(kind)||kind));
  const known=canonical.get(name);
  if(known){
   const explicit=[...labels].map(kind=>kindFamilies.get(kind)).filter(Boolean);
   const allowed=known==='인물'?new Set(['인물','수호신']):new Set([known]);
   if(explicit.some(kind=>!allowed.has(kind)))throw Error('Declared entity kind conflicts with canonical source: '+name+' / '+known+' / '+[...labels].join(', '));
   if(known==='세계관'&&labels.size===1&&families.has('세계관'))resolved.set(name,[...labels][0]);
  }else{
   if(families.size!==1)throw Error('Conflicting declared entity kinds: '+name+' / '+[...labels].join(', '));
   // Keep a named creature or phenomenon's specific declared type. The
   // family is used to detect incompatible categories, not to erase its label.
   resolved.set(name,families.has('세계관')&&labels.size===1?[...labels][0]:[...families][0]);
  }
 }
 for(const alias of atlas.entityAliases||[]){
  if(!resolved.has(alias.targetName))throw Error('Entity kind alias lacks a canonical target: '+alias.name);
  const kind=resolved.get(alias.targetName),old=resolved.get(alias.name);
  if(old&&old!==kind)throw Error('Conflicting entity kind alias: '+alias.name);
  resolved.set(alias.name,kind);
 }
 // The glossary is another explicit reading registry. Fill subjects without
 // an authored entity class; an organization discussed there keeps its class.
 const conceptNames=new Set();
 for(const concept of book?.concepts||[]){
  if(!concept.name||conceptNames.has(concept.name))throw Error('Missing or duplicate canonical concept name: '+concept.name);
  conceptNames.add(concept.name);
  if(!resolved.has(concept.name))resolved.set(concept.name,'개념');
 }
 return resolved;
}
export function clusterNodeKinds(c){
 const nodes=new Map();
 for(const n of c.nodes||[]){
  if(nodes.has(n.name)&&nodes.get(n.name)!==n.kind)throw Error('Conflicting local node roles: '+c.id+' / '+n.name);
  nodes.set(n.name,n.kind);
 }
 return [...nodes].map(([name,kind])=>({name,kind}));
}
export function localClusterKinds(model){
 const kinds=new Map((model.nodeKinds||[]).map(n=>[n.name,n.kind]));
 const endpoint=n=>kinds.has(n.name)?{...n,canonicalKind:n.kind,kind:kinds.get(n.name)}:n;
 return {...model,relations:model.relations.map(r=>({...r,from:endpoint(r.from),to:endpoint(r.to)}))};
}
export async function buildReadingData({source,index,records,atlas,book,entityLinks}){
 const atlasPeople=atlas.people||[];
 const entityKinds=entityKindIndex({index,atlas,book});
 const kindFor=name=>entityKinds.get(name)||'설정 대상';
 const base='/wuwa-quests',entities=[...entityLinks].map(([name,url])=>({id:'entity-'+hash(name).slice(0,16),name,url:base+url,kind:kindFor(name)})),byName=new Map(entities.map(e=>[e.name,e]));
 const sources=index.entries.map(e=>{const r=records[e.id];if(!r)throw Error('Missing reading record '+e.id);return {id:e.id,title:e.title,kind:e.category_label,url:base+e.page,blocks:r.values.filter(v=>v.status==='OK'&&v.text).map(v=>({id:v.field,field:v.field,text:v.text,sha256:hash(v.raw),url:base+e.page+(e.page.includes('#')?'':'#field-'+encodeURIComponent(v.field)),locator:{recordId:e.id,field:v.field,textId:v.text_id}}))};});
 const dialogueRefs=[];
 function gatherDialogueRefs(value){
  if(Array.isArray(value)){value.forEach(gatherDialogueRefs);return;}
  if(!value||typeof value!=='object')return;
  if(value.quest_id&&value.quote&&Number.isInteger(value.scene))dialogueRefs.push(value);
  Object.values(value).forEach(gatherDialogueRefs);
 }
 gatherDialogueRefs([...atlas.regions,...atlas.cosmology,...atlas.sentinels,...atlas.factions,...atlasPeople]);
 for(const questId of new Set(dialogueRefs.map(q=>q.quest_id))){
  const bytes=await readFile(path.join(source,'../originals',questId+'.txt')),raw=bytes.toString('utf8');
  const sceneStarts=[...raw.matchAll(/^장면 (\d+):/gm)];
  sources.push({id:'quest-'+questId,title:dialogueRefs.find(q=>q.quest_id===questId).title,kind:'퀘스트 대사',url:base+'/quests/'+questId+'.html',blocks:sceneStarts.map((m,i)=>{const text=raw.slice(m.index,sceneStarts[i+1]?.index||raw.length),anchor='scene-'+m[1];return {id:anchor,anchor,field:'dialogue',text,sha256:hash(text),url:base+'/quests/'+questId+'.html#'+anchor,locator:{questId,scene:Number(m[1]),originalSha256:hash(bytes)}};})});
 }
 const graph=createReadingGraph({game:'wuwa',sources,entities}),clusters=[],relations=[],events=[];
 const refs=rs=>readingReferences(rs,index.aliases);
 for(const [group,rows] of [['regions',atlas.regions],['cosmology',atlas.cosmology],['sentinels',atlas.sentinels],['factions',atlas.factions],['people',atlasPeople]])for(const c of rows){const id=group+'/'+c.id,sections=[];
  for(const [i,s] of (c.sections||[]).entries())sections.push({id:'section-'+i,title:s.title,deck:s.deck||'',claimIds:[graph.claim(s.text,refs(s.refs),claimAttribution(s))]});
  for(const [i,q] of (c.dialogue||[]).entries())sections.push({id:'dialogue-'+i,title:q.label,claimIds:[graph.claim(q.quote,refs([q]),claimAttribution({...q,refs:[q]}))]});
  if(c.paragraphs?.length)sections.push({id:'context',title:'관련 기록과 사건',claimIds:c.paragraphs.map(p=>graph.claim(p.text,refs(p.refs),claimAttribution(p)))});
  for(const [i,r] of (c.edges||[]).entries()){const a=byName.get(r.a),b=byName.get(r.b);if(!a||!b)throw Error('Unresolved entity '+r.a+' / '+r.b);const attribution=claimAttribution(r);relations.push({id:id+'/relation-'+i,clusterId:id,from:a.id,to:b.id,label:r.verb,kind:attribution.kind,...(r.structure?{structure:r.structure}:{}),reasonClaimId:graph.claim(r.reason,refs(r.refs),attribution)});}
  for(const [i,t] of (c.timeline?.items||[]).entries())events.push({id:id+'/event-'+i,clusterId:id,title:t.title,when:t.when||'',claimId:graph.claim(t.text,refs(t.refs),claimAttribution(t)),order:i});
  const comparisons=(c.comparison||[]).map(p=>({title:p.title,claimId:graph.claim(p.text,refs(p.refs),claimAttribution(p))}));
  const process=(c.process||[]).map(p=>({title:p.title,claimId:graph.claim(p.text,refs(p.refs),claimAttribution(p))}));
  const topologyData=t=>({...t,edges:t.edges.map(e=>{const {refs:rawRefs,text,...edge}=e;return {...edge,claimId:graph.claim(text,refs(rawRefs),claimAttribution(e))};})});
  const topology=c.topology?topologyData(c.topology):null,views=(c.views||[]).map(topologyData);
  clusters.push({id,entityId:byName.get(c.title.split(' · ')[0]).id,title:c.title,url:base+'/'+id+'.html',question:c.question,overview:c.summary,nodeKinds:clusterNodeKinds(c),focusKind:group==='sentinels'?'수호신':kindFor(c.title.split(' · ')[0]),sections,topology,views,comparisons,process,processKind:c.process_kind||'steps',processTitle:c.process_title||'',returnLabel:c.process_kind==='cycle'?'새로운 에코가 분해·제련으로 이어진다':'',containment:c.containment?{...c.containment,children:c.containment.children.map(name=>{const target=byName.get(name),sourceEntry=index.entries.find(e=>e.id===(index.aliases[c.containment.refs[0].id]||c.containment.refs[0].id));return {name,url:target?.url||base+sourceEntry.page};}),evidenceIds:c.containment.refs.map(r=>graph.evidence(refs([r])[0]))}:null,timeNote:c.timeline?.note||'',timeOrdered:!!c.timeline});
 }
 const data=graph.output({clusters,relations,events});const dir=path.join(source,'public/reading-data');await writeReadingGraph(data,dir);
 console.log(JSON.stringify({readingGraph:'PASS',sources:data.sources.length,entities:entities.length,claims:data.claims.length,evidence:data.evidence.length,clusters:clusters.length}));return {data,cluster:id=>resolveCluster(data,id)};
}
