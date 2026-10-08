import {createReadingSections} from './reading-sections.mjs';
import {buildReadingData,localClusterKinds} from './reading-data.mjs';
import {createReadingKit} from '../src/lib/reading-kit/render.mjs';
import {readerDisclosure,readerFrame} from '../src/lib/reading-kit/reader.mjs';
import {readFile,writeFile,unlink} from 'node:fs/promises';
import crypto from 'node:crypto';
import path from 'node:path';
export function clusterGameMedia(c,{index,records,imageManifest,base='/wuwa-quests'}){
 const refs=[];
 const gather=value=>{
  if(Array.isArray(value)){value.forEach(gather);return;}
  if(!value||typeof value!=='object')return;
  if(value.id&&value.source_text_sha256)refs.push(value);
  else Object.values(value).forEach(gather);
 };
 gather(c);
 const ids=new Set(refs.map(r=>index.aliases[r.id]||r.id)),images=[];
 for(const m of [...(imageManifest.monsters||[]),...(imageManifest.geography||[])]){
  if(!ids.has(m.sourceId))continue;
  const im=m.images.geography||m.images.icon||m.images.bossBanner;
  images.push({...im,alt:m.name+'의 게임 도감 이미지',caption:'게임 도감 이미지 · '+m.name,sourceUrl:base+'/game-images/provenance.json',bodyUrl:base+'/sources/'+crypto.createHash('sha256').update(m.sourceId).digest('hex').slice(0,16)+'.html'});
 }
 const npc=(imageManifest.npcPeople||[]).find(p=>p.id===c.id);
 if(npc)images.unshift({...npc.images.icon,alt:npc.name+'의 게임 UI 이미지',caption:'게임 UI 이미지 · '+npc.name,sourceUrl:base+'/game-images/provenance.json'});
 const name=c.title.split(' · ')[0],person=index.characters.find(p=>p.name===name);
 if(person){
  const profileId='인물_프로필_공명기록:favorroleinfo:'+person.id;
  if(ids.has(profileId)){
   const profile=records[profileId],asset=(imageManifest.people||[]).find(p=>String(p.id)===String(person.id));
   if(!profile||String(profile.role_id)!==String(person.id))throw Error('Focus image profile identity differs: '+name);
   for(const ref of refs.filter(r=>(index.aliases[r.id]||r.id)===profileId)){
    const value=profile.values.find(v=>v.field===ref.field&&v.status==='OK');
    if(!value||crypto.createHash('sha256').update(value.raw).digest('hex')!==ref.source_text_sha256||!ref.excerpt||!value.text.includes(ref.excerpt))throw Error('Focus image profile evidence differs: '+name);
   }
   if(asset){
    if(asset.name!==name||asset.mapping.table!=='roleinfo'||String(asset.mapping.id)!==String(person.id))throw Error('Focus image source mapping differs: '+name);
    if(asset.images.portrait)images.unshift({...asset.images.portrait,alt:name+'의 게임 인물 이미지',caption:'게임 인물 이미지 · '+name,sourceUrl:base+'/game-images/provenance.json',bodyUrl:base+'/people/'+person.id+'.html#field-info'});
   }
  }
 }
 return images;
}
export async function generateAtlas({site,content,book,index,records,doc,H,refs,related}){
 const base='/wuwa-quests',atlas=JSON.parse(await readFile(path.join(site,'settings/atlas.json'),'utf8'));
 const npcData=JSON.parse(await readFile(path.join(site,'settings/npc-people.json'),'utf8'));
 atlas.people=[...(atlas.people||[]),...npcData.people];
 const imageManifest=JSON.parse(await readFile(path.join(site,'source/public/game-images/provenance.json'),'utf8'));
 const peopleScriptVersion=crypto.createHash('sha256').update((await readFile(path.join(site,'source/public/lore/people.js'),'utf8')).replace(/\r\n/g,'\n')).digest('hex').slice(0,12);
 const gameImages=new Map([...imageManifest.people,...(imageManifest.npcPeople||[])].map(p=>[String(p.id),p]));
 const icon=p=>{const im=gameImages.get(String(p.id))?.images.icon;return im?`<img class="game-person-icon" src="${H(im.url)}" alt="" width="${im.width}" height="${im.height}" loading="lazy" decoding="async">`:'';};
 const portrait=p=>{const im=gameImages.get(String(p.id))?.images.portrait;return im?`<figure class="game-person-portrait"><img src="${H(im.url)}" alt="${H(p.name)}의 게임 인물 이미지" width="${im.width}" height="${im.height}" decoding="async"><figcaption>게임 인물 이미지 <a href="${base}/game-images/provenance.json">이미지 출처 ↗</a></figcaption></figure>`:'';};
 const personOverview=(raw,p)=>{const first=raw.match(/<section class="lore-field" id="field-info">/);let field='';if(first){const tokens=/<\/?section\b[^>]*>/g;tokens.lastIndex=first.index;let depth=0;for(const token of raw.matchAll(tokens)){depth+=token[0].startsWith('</')?-1:1;if(!depth){field=raw.slice(first.index,token.index+token[0].length);break;}}if(!field)throw Error('Unclosed person overview: '+p.id);}return field?{overview:`<div class="person-overview">${field}${portrait(p)}</div>`,rest:raw.replace(field,'')}:{overview:portrait(p),rest:raw};};
 const all=[...atlas.regions,...atlas.sentinels,...atlas.cosmology,...atlas.factions,...atlas.people];
 const groupFor=c=>atlas.regions.includes(c)?"regions":atlas.sentinels.includes(c)?"sentinels":atlas.factions.includes(c)?"factions":atlas.people.includes(c)?"people":"cosmology";
 function validate(x){if(Array.isArray(x)){x.forEach(validate);return;}if(!x||typeof x!=='object')return;if(x.source_text_sha256&&x.id){const v=records[x.id]?.values.find(v=>v.field===x.field&&v.status==='OK');if(!v||crypto.createHash('sha256').update(v.raw).digest('hex')!==x.source_text_sha256)throw Error('Atlas evidence changed: '+x.id);if(x.excerpt&&!v.text.includes(x.excerpt))throw Error('Atlas excerpt mismatch: '+x.id);}Object.values(x).forEach(validate);}
 validate(atlas);
 const questCache=new Map();
 for(const q of gather(all).filter(r=>r.quest_id)){
  if(!questCache.has(q.quest_id))questCache.set(q.quest_id,await readFile(path.join(site,'originals',q.quest_id+'.txt')));
  const bytes=questCache.get(q.quest_id),raw=bytes.toString('utf8'),starts=[...raw.matchAll(/^장면 (\d+):/gm)],position=starts.findIndex(m=>Number(m[1])===q.scene);
  const scene=position<0?'':raw.slice(starts[position].index,starts[position+1]?.index||raw.length);
  if(crypto.createHash('sha256').update(bytes).digest('hex')!==q.source_sha256||!scene.includes(q.quote))throw Error('Quest evidence or scene changed: '+q.quest_id+' / '+q.scene);
 }

 await unlink(path.join(content,'world/evidence.md')).catch(e=>{if(e.code!=='ENOENT')throw e;});
 const url=s=>base+s;
 const entityLinks=new Map(index.characters.map(p=>[p.name,'/people/'+p.id+'.html']));
 for(const c of all) entityLinks.set(c.title.split(' · ')[0],'/'+groupFor(c)+'/'+c.id+'.html');
 const canonicalAliases=atlas.entityAliases||[];
 for(const alias of canonicalAliases){
  if(!alias.refs?.length||entityLinks.get(alias.targetName)!==alias.targetUrl)throw Error('Unproved entity alias target: '+alias.name);
  if(entityLinks.has(alias.name)&&entityLinks.get(alias.name)!==alias.targetUrl)throw Error('Conflicting entity alias: '+alias.name);
  entityLinks.set(alias.name,alias.targetUrl);
 }
 for(const [i,c] of book.concepts.entries()) if(!entityLinks.has(c.name))entityLinks.set(c.name,'/concepts/'+i+'.html');
 const entitySources=new Map();
 for(const c of all)for(const n of c.nodes){
  if(entityLinks.has(n.name)){n.url=entityLinks.get(n.name);continue;}
  const sources=gather(c).filter(r=>(r.excerpt||r.quote||'').includes(n.name)||(r.label||r.title||'').includes(n.name));
  if(!sources.length)continue;
  const slug=crypto.createHash('sha256').update(n.name).digest('hex').slice(0,16);
  n.url='/entities/'+slug+'.html';entityLinks.set(n.name,n.url);entitySources.set(n.name,{slug,sources});
 }
 const namePattern=new RegExp([...entityLinks.keys()].filter(n=>n.length>1).sort((a,b)=>b.length-a.length).map(n=>n.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|'),'g');
 function text(s,excludeName=''){s=String(s).replace(/<br\s*\/?\s*>/gi,'\n').replace(/<\/?(?:te|color|size|b|i|u|ano|s)(?:[=\s][^>]*)?>/g,'');let out='',last=0;const seen=new Set();for(const m of s.matchAll(namePattern)){const at=m.index,after=at+m[0].length;if(at>0&&/[\p{L}\p{N}]/u.test(s[at-1]))continue;if(/[\p{L}\p{N}]/u.test(s[after]||'')&&!/^(?:은|는|이|가|을|를|의|에|에서|에게|와|과|도|로|으로|부터|까지|께서|씨(?:가|는|의|도|를)?)(?=$|[^\p{L}\p{N}])/u.test(s.slice(after)))continue;out+=H(s.slice(last,at));const name=m[0];if(name===excludeName||name==='구원'||seen.has(name)||seen.size>=3)out+=H(name);else{out+=`<a class="setting-entity-link" href="${url(entityLinks.get(name))}">${H(name)}</a>`;seen.add(name);}last=after;}return out+H(s.slice(last));}
 for(const c of all)for(const n of c.nodes)if(!entityLinks.has(n.name))entityLinks.set(n.name,n.url);
 for(const c of all)for(const n of [c.topology,...(c.views||[])].filter(Boolean).flatMap(t=>t.nodes))if(entityLinks.has(n.name))n.url=url(entityLinks.get(n.name));
 all.forEach(c=>refs(gather(c)));
 const normalized=await buildReadingData({source:path.join(site,'source'),index,records,atlas,book,entityLinks});
 const model=c=>localClusterKinds(normalized.cluster(normalized.data.clusters.find(x=>x.id.endsWith('/'+c.id)).id));
 const claimMap=new Map(normalized.data.claims.map(c=>[c.id,c])),evidenceMap=new Map(normalized.data.evidence.map(e=>[e.id,e]));
 const claim=id=>{const c=claimMap.get(id);return {...c,evidence:c.evidenceIds.map(id=>evidenceMap.get(id))};};
 const kit=createReadingKit({inline:text,evidence:rs=>rs.map(r=>`<span class="rw-attribution">원문 인용${r.speaker?' · '+H(r.speaker):''}</span><blockquote>${text(r.quote)}</blockquote><a href="${H(r.url)}">${H(r.title)} ↗</a>`).join('')});
 const proofFor=r=>{
  const sourceId=r.quest_id?'quest-'+r.quest_id:index.aliases[r.id]||r.id,blockId=r.quest_id?'scene-'+r.scene:r.field;
  const item=normalized.data.evidence.find(e=>e.sourceId===sourceId&&e.blockId===blockId&&e.quote===(r.quote||r.excerpt));
  if(!item)throw Error('Entity source proof missing: '+sourceId+' / '+blockId);
  return item;
 };
 for(const [name,{slug,sources}] of entitySources)await doc('entities/'+slug,name,`<p class="atlas-deck">${H(name)}에 관한 기록</p>${sources.map((r,i)=>kit.section({id:'entity-record-'+i,title:r.label||r.title,items:[{text:r.excerpt||r.quote,kind:'fact',speaker:r.speaker,evidence:[proofFor(r)]}]})).join('')}`,name+'의 원문 기록');
 const sections=createReadingSections({H,text,refs,kit,model,claim,evidenceMap});
 const clusterMedia=c=>{const images=clusterGameMedia(c,{index,records,imageManifest,base});return kit.media(images.slice(0,2))+(images.length>2?readerDisclosure('관련 게임 이미지 '+images.length+'개',kit.media(images.slice(2)),{className:'rw-media-more'}):'');};
 const intro=c=>`<div class="atlas-intro"><p class="lore-kicker">${H(c.question)}</p><p class="atlas-deck">${text(c.summary,c.title.split(' · ')[0])}</p></div>`;
 const directoryEntry=(c,group)=>({name:c.title,summary:[group==='regions'?'지역':group==='sentinels'?'수호신':group==='factions'?'세력':group==='people'?'인물':'세계의 원리',c.question,c.summary].join('\n'),url:url('/'+group+'/'+c.id+'.html')});
 const cards=(cs,group)=>kit.directory(cs.map(c=>directoryEntry(c,group)));
 const paragraphs=ps=>ps.map(p=>`<div class="atlas-reading ${p.kind==='reading'?'atlas-interpretation':''}"><span class="lore-kind">${p.kind==='reading'?'편집자의 해석':'원문 연결'}</span><p>${text(p.text)}</p>${refs(p.refs)}</div>`).join('');
 const relations=c=>kit.network(model(c).relations.filter(r=>c.edges.some(e=>e.a===r.from.name&&e.b===r.to.name)),{id:'relations-'+c.id,title:c.title+'의 관계',focusId:model(c).entityId});
 const supplementalRelations=c=>{const m=model(c);if(!m.topology)return '';const renderedClaims=new Set([m.topology,...m.views].flatMap(t=>t.edges.map(e=>e.claimId)));const missing=m.relations.filter(r=>!renderedClaims.has(r.reasonClaimId));return missing.length?kit.network(missing,{id:'supplemental-relations-'+c.id,title:'관련 관계와 함께 읽을 기록',focusId:m.entityId}):'';};
 const events=c=>c.timeline?`<h2 id="events">${H(c.timeline.title)}</h2>`+kit.timeline(model(c).events,{ordered:model(c).timeOrdered,note:model(c).timeNote}):'';
 const comparisons=c=>c.comparison?`<h2 id="perspectives">${H(c.comparison_title||'같은 대상을 보는 서로 다른 기록')}</h2>`+kit.comparison(model(c).comparisons.map(p=>({...p,...claim(p.claimId)}))):'';
 function gather(x,out=[]){if(Array.isArray(x))x.forEach(v=>gather(v,out));else if(x&&typeof x==='object'){if((x.source_text_sha256&&x.id)||(x.quest_id&&x.quote))out.push(x);else Object.values(x).forEach(v=>gather(v,out));}return [...new Map(out.map(r=>[r.quest_id?'quest-'+r.quest_id+'|'+r.scene+'|'+r.quote:r.id+'|'+r.field,r])).values()];}
 const evidence=c=>{
  const groups=new Map();
  for(const r of gather(c)){const key=r.quest_id?'quest-'+r.quest_id+'|'+r.scene+'|'+r.speaker:r.id+'|'+r.field;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);}
  return `<section class="atlas-evidence"><h2 id="evidence">이 페이지의 원문 근거</h2><p class="atlas-caption">원문 인용에는 자료명과 발언 주체를 표시합니다. 자료 제목을 누르면 해당 본문과 대사 장면을 읽을 수 있습니다.</p>${[...groups.values()].map(rs=>{const r=rs[0];return readerDisclosure(r.quest_id?'퀘스트 · '+r.title+' · 장면 '+r.scene+' · '+r.speaker:r.label+' · '+(r.field==='content'?'본문':r.field==='info'?'소개':r.field==='talent_document'?'공명 기록':'기록'),`<span class="rw-attribution">원문 인용${r.speaker?' · '+H(r.speaker):''}</span>${rs.map(q=>`<blockquote>${text(q.quote||q.excerpt)}</blockquote>`).join('')}${refs([r])}`,{className:'atlas-proof'});}).join('')}</section>`;
 };
 const people=ids=>`<div class="atlas-people">${ids.map(id=>index.characters.find(p=>p.id===id)).filter(Boolean).map(p=>`<a href="${url('/people/'+p.id+'.html')}"><strong>${H(p.name)}</strong><small>${H(p.influence)}</small></a>`).join('')}</div>`;
 const concepts=ids=>`<div class="lore-pills">${ids.map(i=>`<a href="${url('/concepts/'+i+'.html')}">${H(book.concepts[i].name)}</a>`).join('')}</div>`;
 const directory=(title,lead,cs,group)=>`<section class="rw-index-group"><header class="rw-index-heading"><h3>${H(title)}</h3><p>${H(lead)}</p></header>${cards(cs,group)}</section>`;
 await doc('world','설정집',`<p class="atlas-deck">솔라리스의 재앙과 힘, 지역의 생활과 역사, 인물의 기록을 함께 읽습니다.</p><nav class="atlas-jump" aria-label="설정집 탐색"><a href="#world-principles">세계의 원리</a><a href="#world-regions">지역</a><a href="#world-factions">세력</a><a href="${url('/people.html')}">인물</a><a href="${url('/library.html')}">원문 보관함</a></nav><div class="world-directory rw-index rw-index-groups"><div id="world-factions">${directory("세력","조직의 구성과 목적, 소속 인물과 지역에서의 활동을 함께 읽습니다.",atlas.factions,"factions")}</div><div id="world-principles">${directory('세계관의 큰 설정','세계의 변화 → 재앙과 생태 → 공명과 기술. 각 개념의 정의와 지역에 드러난 사례를 읽습니다.',atlas.cosmology,'cosmology')}</div><div id="world-regions">${directory('지역의 역사와 생활','지역의 개요와 주요 장소에서 시작해 제도·신앙·생활·사건으로 이어집니다.',atlas.regions,'regions')}</div>${directory('인물의 행적과 관계','주요 인물의 발언과 선택, 소속과 관계를 함께 읽습니다.',atlas.people,'people')}${directory('수호신과 문명','수호신의 기록과 권능, 지역과 인물에게 이어지는 관계를 읽습니다.',atlas.sentinels,'sentinels')}</div><div class="lore-actions"><a href="${url('/people.html')}">인물별 설정</a><a href="${url('/relationships.html')}">관계 따라 읽기</a><a href="${url('/events.html')}">사건과 전환점</a></div>`,'명조의 세계관·지역·인물과 원문 기록',false);
 for(const [group,title,lead,cs] of [['factions','세력','조직의 구성과 행동, 소속 인물과의 관계를 함께 읽습니다.',atlas.factions],['regions','지역별 설정','도시의 현재에서 출발해, 그 모습을 만든 보호·제도·사건을 읽습니다.',atlas.regions],['cosmology','세계관의 큰 설정','개념의 정의를 먼저 이해하고, 지역과 인물에 드러나는 구체적인 사례로 확장합니다.',atlas.cosmology],['people','인물','인물의 발언과 선택, 소속과 관계를 원문으로 함께 읽습니다.',atlas.people],['sentinels','수호신과 문명','무엇을 지키고, 어떤 힘으로 문명을 이끄는가. 수호신의 권능과 그 힘을 이어받거나 해석하는 사람들을 함께 읽습니다.',atlas.sentinels]]){
  if(group!=='people')await doc(group,title,`<p class="atlas-deck">${lead}</p>${cards(cs,group)}${group==='sentinels'?'<p class="lore-note">파수인은 검은 해안의 인물이며, 엑소스트라이더는 메카스카우트로 기록됩니다. 이 목록은 원문이 수호신으로 명시한 존재를 중심으로 구성했습니다.</p>':''}`,lead,false);
  for(const c of cs){let body=`<nav class="atlas-breadcrumb" aria-label="설정 위치"><a href="${url('/world.html')}">설정집</a><span aria-hidden="true">›</span><a href="${url('/'+group+'.html')}">${title}</a>${c.parent?`<span aria-hidden="true">›</span><span>리나시타의 도시 국가</span>`:''}</nav>${intro(c)}${clusterMedia(c)}<span id="overview-0"></span><nav class="atlas-jump" aria-label="이 설정에서 읽기"><a href="#overview-0">개요</a>${c.topology||c.edges.length?`<a href="#${H(c.topology?.id||'structure')}">핵심 구조</a>`:''}${(c.sections||[]).map((s,i)=>`<a href="#section-${i}">${H(s.title)}</a>`).join('')}${c.edges.length?'<a href="#relations">관계</a>':''}${c.timeline?'<a href="#events">사건</a>':''}${c.comparison?'<a href="#perspectives">기록 비교</a>':''}${(c.views||[]).map(v=>`<a href="#${H(v.id)}">${H(v.title)}</a>`).join('')}<a href="#next">이어 읽기</a></nav>${c.facts?readerFrame(`<dl class="setting-facts">${c.facts.map(([k,v])=>`<div><dt>${H(k)}</dt><dd>${text(v)}</dd></div>`).join('')}</dl>`,{variant:'record',className:'setting-facts-reader'}):''}${c.edges.length?'<span id="relations"></span>':''}${model(c).topology?kit.topology(model(c).topology):kit.network(model(c).relations,{id:'structure',title:'関係 한눈에'.replace('関係','관계'),focusId:model(c).entityId})}${model(c).views.map(kit.topology).join('')}${supplementalRelations(c)}${model(c).containment?`<section id="containment"><h2>${H(model(c).containment.title)}</h2>${kit.containment({...model(c).containment,evidence:model(c).containment.evidenceIds.map(id=>evidenceMap.get(id))})}</section>`:''}${sections({...c,facts:null})}${events(c)}${comparisons(c)}`;
   if(c.applications)body+=`<h2>이 원리가 지역에 드러나는 모습</h2>${cards(c.applications.map(id=>atlas.regions.find(r=>r.id===id)),'regions')}`;
   if(c.bridge)body+=kit.section({id:'bridge-'+c.id,title:c.bridge.title,items:[{text:c.bridge.text,kind:'inference',evidence:c.bridge.refs.map(proofFor)}]})+`<a href="${url(c.bridge.url)}">이 질문에서 이어 읽기 →</a>`;
   body+=`<h2 id="next">지금의 질문에서 더 깊이 읽기</h2>${c.region?`<div class="lore-actions"><a href="${url('/regions/'+c.region+'.html')}">관련 지역 →</a></div>`:''}${people(c.roles)}${group==='regions'?kit.directory(atlas.people.filter(p=>(p.regions||[p.region]).includes(c.id)).map(p=>({name:p.title,summary:p.summary,url:url('/people/'+p.id+'.html')}))):''}${kit.directory(all.filter(x=>x!==c&&x.edges.some(e=>e.a===c.title.split(' · ')[0]||e.b===c.title.split(' · ')[0])).map(x=>({name:x.title,summary:x.summary,url:url('/'+groupFor(x)+'/'+x.id+'.html')})))}${concepts(c.concepts)}${related(c.chapters)}${evidence(c)}`;
   await doc(group+'/'+c.id,c.title,body,c.question,false);
  }
 }
 await doc('factions/scar','스카',`<p><a href="${url('/people/scar.html')}">스카의 인물 자료와 관계 읽기 →</a></p><script>location.replace('/wuwa-quests/people/scar.html'+location.search+location.hash)</script>`,'스카의 인물 자료',false,false);
 // Resolve old automatic entity routes through the same canonical registry.
 const canonicalEntities=new Map(all.map(c=>[c.title.split(' · ')[0],{target:'/'+groupFor(c)+'/'+c.id+'.html'}]));
 for(const alias of canonicalAliases)canonicalEntities.set(alias.name,{target:alias.targetUrl,alias});
 for(const [name,entry] of canonicalEntities){
  const slug=crypto.createHash('sha256').update(name).digest('hex').slice(0,16),target=url(entry.target);
  const explanation=entry.alias?`<p>${H(entry.alias.targetName)} · ${H(entry.alias.relation)}</p>${refs(entry.alias.refs)}`:'';
  await doc('entities/'+slug,name,`${explanation}<p><a href="${H(target)}">${H(name)}의 본문과 원문 자료 읽기 →</a></p><script>location.replace(${JSON.stringify(target)}+location.search+location.hash)</script>`,name+'의 원문 자료',false,false);
 }
 await doc('relationships','관계 따라 읽기',`<p class="atlas-deck">같은 단어보다, 서로에게 하는 일을 따라갑니다.</p><nav class="atlas-jump" aria-label="지역 관계 바로가기">${[...atlas.people,...atlas.factions,...atlas.regions].map(c=>`<a href="#relation-${c.id}">${H(c.title.split(' · ')[0])}</a>`).join('')}</nav>${[...atlas.people,...atlas.factions,...atlas.regions].map(c=>`<h2 id="relation-${c.id}">${H(c.title)}</h2><p>${H(c.question)}</p>${relations(c)}<a class="lore-more" href="${url('/'+groupFor(c)+'/'+c.id+'.html#evidence')}">본문과 원문 근거 →</a>`).join('')}${evidence([...atlas.people,...atlas.factions,...atlas.regions].map(c=>c.edges))}`,'관계 이름과 원문 근거를 함께 읽는 세력·지역의 관계도');
 await doc('events','전환점 따라 읽기',`<p class="atlas-deck">인물의 결정과 문명의 변화가 맞물리는 순간을 읽습니다.</p><p class="atlas-caption">지역별 기록에 명시된 사건의 전후 관계를 따라 배열했습니다.</p>${atlas.regions.filter(c=>c.timeline).map(c=>`<h2>${H(c.title)}</h2>${events(c).replace('id="events"','id="events-'+c.id+'"')}<a class="lore-more" href="${url('/regions/'+c.id+'.html')}">관계와 배경을 함께 읽기 →</a>`).join('')}${evidence(atlas.regions.filter(c=>c.timeline).map(c=>c.timeline))}`,'원문이 확인하는 사건 흐름과 전환점');
 function regionFor(p){return atlas.regions.find(r=>r.roles.includes(p.id))?.id||(p.influence.includes('금주')?'jinzhou':p.influence.includes('검은 해안')||p.influence.includes('검은해안')?'black-shores':/라군나|몬텔리|피살리아|수도회|우인/.test(p.influence)?'rinascita':p.influence.includes('일곱 언덕')?'seven-hills':/스타토치|라하이|로야|스페이스 트렉/.test(p.influence)?'raha':p.influence.includes('몽주')?'mongju':'other');}
 await doc('people','인물별 설정',readerFrame(`<p class="atlas-deck">한 사람의 소개에서 시작해, 소속과 관계, 과거와 선택을 함께 읽습니다.</p><div class="lore-people-controls atlas-person-controls" role="search"><label for="lore-person-q">인물 찾기<input id="lore-person-q" type="search" placeholder="예: 스카, 크리스토포로, 금희" autocomplete="off"></label><label for="lore-person-region">활동 지역·소속<select id="lore-person-region"><option value="">모든 지역</option>${atlas.regions.map(r=>`<option value="${r.id}">${H(r.title.split(' · ')[0])}</option>`).join('')}<option value="other">그 밖의 소속·미확인</option></select></label><p id="lore-person-count" role="status" aria-live="polite">${index.characters.length+atlas.people.length}개 인물 자료</p></div><section class="atlas-person-group npc-directory"><h2>주요 인물의 행적과 관계</h2><div class="lore-person-grid">${atlas.people.map(p=>`<a class="lore-person-card npc-person-card" data-name="${H(p.title)}" data-region="${H(p.region||'other')}" data-regions="${H((p.regions||[p.region||'other']).join(' '))}" href="${url('/people/'+p.id+'.html')}">${icon(p)}<h3>${H(p.title)}</h3><p>${H(p.summary)}</p><small>행적·관계 · 원문 대사 ↗</small></a>`).join('')}</div></section>${[...atlas.regions.map(r=>[r.id,r.title.split(' · ')[0]]),['other','그 밖의 소속·미확인']].map(([id,label])=>`<section class="atlas-person-group" data-region="${id}"><h2>${H(label)}</h2><div class="lore-person-grid">${index.characters.filter(p=>regionFor(p)===id).map(p=>`<a class="lore-person-card" data-name="${H(p.name)}" data-region="${id}" href="${url('/people/'+p.id+'.html')}">${icon(p)}<h3>${H(p.name)}</h3><p>${H(p.influence)}</p><small>출신: ${H(p.country||'미확인')}<br>이야기 ${p.counts.stories||0} · 소장품 ${p.counts.goods||0}</small></a>`).join('')}</div></section>`).join('')}<p id="lore-person-empty" hidden>찾는 인물이 없습니다. 이름이나 지역 조건을 바꿔보세요.</p><p class="atlas-caption">활동 지역과 소속을 기준으로 묶고, 출신은 별도로 표시합니다. 미사용·테스트 자료가 포함될 수 있으며 실제 출시 여부를 확정하지 않습니다.</p><script src="${base}/lore/people.js?v=${peopleScriptVersion}" defer></script>`,{variant:'directory',className:'person-directory-reader'}),'소속·지역과 관계를 따라 찾아 읽는 인물 자료',false,false);

 for(const [i,c] of book.concepts.entries()){
  const file=path.join(content,'concepts/'+i+'.md'),raw=await readFile(file,'utf8');
  const connected=[...atlas.regions.map(c=>({c,group:'regions'})),...atlas.cosmology.map(c=>({c,group:'cosmology'})),...atlas.factions.map(c=>({c,group:'factions'}))].filter(x=>x.c.concepts.includes(i));
  const row=records[index.aliases[c.ref.id]||c.ref.id],v=row.values.find(v=>v.field===c.ref.field),exact={...c.ref,excerpt:v.text.slice(0,240)};
  await writeFile(file,raw+`<h2>이 개념이 삶과 지역에 드러나는 모습</h2>${kit.directory(connected.map(x=>directoryEntry(x.c,x.group)))}${evidence({refs:[exact]})}`);
 }
 // Insert semantic context above the existing complete profile/stories, without changing their primary text.
 for(const p of index.characters){const rid=regionFor(p),region=atlas.regions.find(r=>r.id===rid),file=path.join(content,'people/'+p.id+'.md'),raw=await readFile(file,'utf8'),end=raw.indexOf('\n---',4)+4,edges=region?.edges.filter(e=>e.a===p.name||e.b===p.name)||[];const lead=region?`\n\n<div class="atlas-person-context"><span class="lore-kicker">${H(region.title.split(' · ')[0])}에서 함께 읽기</span><a href="${url('/regions/'+rid+'.html')}">${H(region.question)} →</a>${edges.length?relations({...region,edges}):''}${p.id==='1304'?`<a class="lore-more" href="${url('/regions/jinzhou.html#events')}">금희가 시간 제어를 이어받기까지 →</a>`:''}</div>`:'';const sources=index.entries.filter(e=>String(e.role_id)===p.id&&['profile','stories','goods'].includes(e.chunk));const bottom=`<section class="atlas-evidence"><h2>이 페이지의 원문 자료</h2><p class="atlas-caption">위에 수록한 소개·기록·이야기·소장품의 원문입니다. 자료별 본문과 출처를 확인할 수 있습니다.</p>${kit.directory(sources.map(e=>({name:e.title,summary:e.category_label,url:url(e.page)})))}</section>`;const overview=personOverview(raw.slice(end),p);await writeFile(file,raw.slice(0,end)+'\n\n'+overview.overview+lead+atlas.factions.filter(c=>c.roles.includes(p.id)).map(c=>`<div class="atlas-person-context"><a href="${url('/factions/'+c.id+'.html')}">${H(c.title)}의 구성과 인물별 발언 →</a></div>`).join('')+atlas.cosmology.filter(c=>c.roles.includes(p.id)).map(c=>`<div class="atlas-person-context"><a href="${url('/cosmology/'+c.id+'.html')}">${H(c.title)} · 행적과 관련 원문 함께 읽기 →</a></div>`).join('')+overview.rest+'\n'+bottom);}
 let guide='# 명조 세계관 설정집\n\n지역·인물·세계의 큰 설정을 관계와 사건, 원문으로 이어 읽습니다.\n\n';
 for(const [name,group,cs] of [['인물','people',atlas.people],['세력','factions',atlas.factions],['지역','regions',atlas.regions],['수호신','sentinels',atlas.sentinels],['세계관의 큰 설정','cosmology',atlas.cosmology]]){guide+='## '+name+'\n\n';for(const c of cs){guide+='### '+c.title+'\n\n**질문:** '+c.question+'\n\n'+c.summary+'\n\n';for(const s of model(c).sections){guide+='#### '+s.title+'\n\n';for(const item of s.items)guide+=item.text+'\n\n'+item.evidence.map(e=>'['+e.title+'](https://mizan0515.github.io'+e.url+')').join(' · ')+'\n\n';}for(const e of c.edges)guide+='- '+e.a+' → **'+e.verb+'** → '+e.b+': '+e.reason+'\n';if(c.timeline){guide+='\n**'+c.timeline.title+'**\n\n';c.timeline.items.forEach((e,i)=>{guide+=(i+1)+'. **'+e.title+'** — '+e.text+'\n';});}guide+='\n[화면에서 관계·원문 함께 읽기](https://mizan0515.github.io'+base+'/'+group+'/'+c.id+'.html)\n\n';}}
 await writeFile(path.join(site,'settings/world-guide.md'),guide);
 console.log(JSON.stringify({atlasEvidence:'PASS',regions:atlas.regions.length,sentinels:atlas.sentinels.length,conceptClusters:atlas.cosmology.length,relations:atlas.regions.reduce((n,c)=>n+c.edges.length,0)}));
}
