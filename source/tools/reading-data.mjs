import {createHash} from 'node:crypto';
import {writeFile,mkdir,readFile} from 'node:fs/promises';
import path from 'node:path';
import {createReadingGraph,resolveCluster} from '../src/lib/reading-kit/graph.mjs';
import {writeReadingGraph} from '../src/lib/reading-kit/write.mjs';
const hash=s=>createHash('sha256').update(s).digest('hex');
export async function buildReadingData({source,index,records,atlas,entityLinks}){
 const base='/wuwa-quests',entities=[...entityLinks].map(([name,url])=>({id:'entity-'+hash(name).slice(0,16),name,url:base+url,kind:index.characters.some(p=>p.name===name)?'인물':atlas.regions.some(c=>c.title.split(' · ')[0]===name)?'지역':atlas.cosmology.some(c=>c.title.split(' · ')[0]===name)?'세계관':'설정 대상'})),byName=new Map(entities.map(e=>[e.name,e]));
 const sources=index.entries.map(e=>{const r=records[e.id];if(!r)throw Error('Missing reading record '+e.id);return {id:e.id,title:e.title,kind:e.category_label,url:base+e.page,blocks:r.values.filter(v=>v.status==='OK'&&v.text).map(v=>({id:v.field,field:v.field,text:v.text,sha256:hash(v.raw),url:base+e.page+(e.page.includes('#')?'':'#field-'+encodeURIComponent(v.field)),locator:{recordId:e.id,field:v.field,textId:v.text_id}}))};});
 const dialogueRefs=[...atlas.regions,...atlas.cosmology,...atlas.sentinels,...atlas.factions].flatMap(c=>c.dialogue||[]);
 for(const questId of new Set(dialogueRefs.map(q=>q.quest_id))){
  const bytes=await readFile(path.join(source,'../originals',questId+'.txt')),raw=bytes.toString('utf8');
  const sceneStarts=[...raw.matchAll(/^장면 (\d+):/gm)];
  sources.push({id:'quest-'+questId,title:dialogueRefs.find(q=>q.quest_id===questId).title,kind:'퀘스트 대사',url:base+'/quests/'+questId+'.html',blocks:sceneStarts.map((m,i)=>{const text=raw.slice(m.index,sceneStarts[i+1]?.index||raw.length),anchor='scene-'+m[1];return {id:anchor,anchor,field:'dialogue',text,sha256:hash(text),url:base+'/quests/'+questId+'.html#'+anchor,locator:{questId,scene:Number(m[1]),originalSha256:hash(bytes)}};})});
 }
 const graph=createReadingGraph({game:'wuwa',sources,entities}),clusters=[],relations=[],events=[];
 const refs=rs=>rs.map(r=>({sourceId:index.aliases[r.id]||r.id,field:r.field,quote:r.excerpt,title:r.label,sourceSha256:r.source_text_sha256}));
 for(const [group,rows] of [['regions',atlas.regions],['cosmology',atlas.cosmology],['sentinels',atlas.sentinels],['factions',atlas.factions]])for(const c of rows){const id=group+'/'+c.id,sections=[];
  for(const [i,s] of (c.sections||[]).entries())sections.push({id:'section-'+i,title:s.title,deck:s.deck||'',claimIds:[graph.claim(s.text,refs(s.refs),{kind:s.kind==='reading'?'inference':s.speaker?'attributed':'explicit',speaker:s.speaker||''})]});
  for(const [i,q] of (c.dialogue||[]).entries())sections.push({id:'dialogue-'+i,title:q.label,claimIds:[graph.claim(q.quote,[{sourceId:'quest-'+q.quest_id,anchor:'scene-'+q.scene,quote:q.quote,title:q.title}],{kind:'attributed',speaker:q.speaker})]});
  if(c.paragraphs.length)sections.push({id:'context',title:'관련 기록과 사건',claimIds:c.paragraphs.map(p=>graph.claim(p.text,refs(p.refs),{kind:p.kind==='reading'?'inference':'explicit'}))});
  for(const [i,r] of c.edges.entries()){const a=byName.get(r.a),b=byName.get(r.b);if(!a||!b)throw Error('Unresolved entity '+r.a+' / '+r.b);relations.push({id:id+'/relation-'+i,clusterId:id,from:a.id,to:b.id,label:r.verb,kind:r.kind==='reading'?'inference':'explicit',reasonClaimId:graph.claim(r.reason,refs(r.refs),{kind:r.kind==='reading'?'inference':'explicit'})});}
  for(const [i,t] of (c.timeline?.items||[]).entries())events.push({id:id+'/event-'+i,clusterId:id,title:t.title,when:t.when||'',claimId:graph.claim(t.text,refs(t.refs)),order:i});
  const comparisons=(c.comparison||[]).map(p=>({title:p.title,claimId:graph.claim(p.text,refs(p.refs),{kind:'attributed',speaker:p.speaker||p.title})}));
  const process=(c.process||[]).map(p=>({title:p.title,claimId:graph.claim(p.text,refs(p.refs))}));
  const topology=c.topology?{...c.topology,edges:c.topology.edges.map(e=>{const {refs:rawRefs,text,...edge}=e;return {...edge,claimId:graph.claim(text,refs(rawRefs),{kind:e.speaker?"attributed":"explicit",speaker:e.speaker||""})};})}:null;
  clusters.push({id,entityId:byName.get(c.title.split(' · ')[0]).id,title:c.title,url:base+'/'+id+'.html',question:c.question,overview:c.summary,sections,topology,comparisons,process,processKind:c.process_kind||'steps',processTitle:c.process_title||'',returnLabel:c.process_kind==='cycle'?'새로운 에코가 분해·제련으로 이어진다':'',containment:c.containment?{...c.containment,children:c.containment.children.map(name=>{const target=byName.get(name),sourceEntry=index.entries.find(e=>e.id===(index.aliases[c.containment.refs[0].id]||c.containment.refs[0].id));return {name,url:target?.url||base+sourceEntry.page};}),evidenceIds:c.containment.refs.map(r=>graph.evidence(refs([r])[0]))}:null,timeNote:c.timeline?.note||'',timeOrdered:!!c.timeline});
 }
 const data=graph.output({clusters,relations,events});const dir=path.join(source,'public/reading-data');await writeReadingGraph(data,dir);
 console.log(JSON.stringify({readingGraph:'PASS',sources:data.sources.length,entities:entities.length,claims:data.claims.length,evidence:data.evidence.length,clusters:clusters.length}));return {data,cluster:id=>resolveCluster(data,id)};
}
