import {readerFrame} from '../src/lib/reading-kit/reader.mjs';

// An editorial directory references existing dossiers and exact original fields.
// Its groups are reading entrances, rather than invented in-world affiliations.
export function resolveDirectories(data,atlas) {
 if(data.schema!=='wuwa-directory-discovery.v1')throw Error('Unknown directory schema');
 const entries=new Map();
 for(const e of data.entries){
  if(!/^[a-z][a-z0-9-]+$/.test(e.id)||!['factions','cosmology'].includes(e.category)||!e.refs?.length||entries.has(e.category+'/'+e.id))throw Error('Invalid source-backed directory entry '+e.id);
  entries.set(e.category+'/'+e.id,e);
 }
 const pages={};
 for(const [category,page] of Object.entries(data.pages)){
  const all=new Map(atlas[category].map(c=>[c.id,{id:c.id,name:c.title,kind:category==='factions'?'조직 본문':'설정 본문',summary:c.summary,url:'/wuwa-quests/'+category+'/'+c.id+'.html'}]));
  for(const e of data.entries.filter(e=>e.category===category)){
   if(all.has(e.id))throw Error('Duplicate directory subject '+e.id);
   all.set(e.id,e);
  }
  const seen=new Set(),groups=page.groups.map(g=>{
   if(!g.title||!g.summary||!g.entryIds.length)throw Error('Directory group lacks a reading purpose');
   const items=g.entryIds.map(id=>{
    if(!all.has(id)||seen.has(id))throw Error('Unresolved or repeated directory entry '+category+'/'+id);
    seen.add(id);return all.get(id);
   });return {...g,items};
  });
  if(seen.size!==all.size)throw Error('Directory subjects omitted from groups: '+[...all.keys()].filter(id=>!seen.has(id)).join(', '));
  pages[category]={...page,groups,total:all.size};
 }
 return pages;
}

export function createDirectoryRenderer({kit,H,proofFor,entityLinks,scriptVersion}) {
 const base='/wuwa-quests';
 const relatedName=url=>[...entityLinks].find(([,value])=>base+value===url)?.[0];
 const cardExtras=(items,group)=>items.map(e=>`<span hidden data-discovery-entry="${H(e.id)}" data-discovery-group="${H(group)}" data-discovery-search="${H(e.name+' '+e.kind+' '+e.summary)}"></span>`);
 const cards=(items,group)=>{const extras=cardExtras(items,group);return kit.directory(items).replaceAll(/(<article\b[^>]*data-cva-item-index="(\d+)"[^>]*>)/g,(opening,_,i)=>opening+extras[Number(i)]);};
 // Each group is capped below the canonical CVA module's 24-item limit.
 const directory=(page,category)=>{
  if(page.groups.some(g=>g.items.length>24))throw Error('Split large editorial directory groups');
  return readerFrame(`<div class="discovery-directory" data-discovery-directory><p class="atlas-deck">${H(page.lead)}</p><nav class="discovery-jump" aria-label="${H(page.title)} 주제별 바로가기">${page.groups.map(g=>`<a href="#group-${H(g.id)}"><strong>${H(g.title)}</strong><span>${g.items.length}개 본문 <span aria-hidden="true">↓</span></span></a>`).join('')}</nav><form class="discovery-controls" role="search"><label for="discovery-query">이름·내용 찾기<input type="search" id="discovery-query" name="q" placeholder="${category==='factions'?'예: 검은 해안, 스타토치, 치안':'예: 오버클럭, 명식, 소노라'}" autocomplete="off"></label><label for="discovery-group">주제<select id="discovery-group" name="group"><option value="">모든 주제</option>${page.groups.map(g=>`<option value="${H(g.id)}">${H(g.title)}</option>`).join('')}</select></label><button type="reset">초기화</button></form><p class="discovery-result" role="status" aria-live="polite" aria-atomic="true">${page.total}개 본문</p><p class="atlas-caption discovery-editorial-note">주제 묶음은 함께 읽기 위한 편집 분류입니다. 각 본문에서 원문과 근거를 확인할 수 있습니다.</p>${page.groups.map(g=>`<section class="discovery-group" id="group-${H(g.id)}" data-discovery-section="${H(g.id)}" tabindex="-1"><header><h2>${H(g.title)}</h2><p>${H(g.summary)}</p></header>${cards(g.items,g.id)}<a class="discovery-top" href="#discovery-query">이름·내용 찾기로 돌아가기 ↑</a></section>`).join('')}<p class="discovery-empty" hidden>검색 결과가 없습니다. 이름을 짧게 입력하거나 주제 조건을 바꿔보세요.</p><aside class="discovery-library"><h2>원문을 더 찾아 읽기</h2><p>문서·지역·인물·생태·아이템의 전체 원문은 보관함에서 이름과 본문으로 찾을 수 있습니다.</p><a href="${base}/library.html">원문 보관함 →</a><a href="${base}/index.html">퀘스트 대사 자료집 →</a></aside><script src="${base}/lore/directory.js?v=${scriptVersion}" defer></script></div>`,{variant:'directory',className:'discovery-reader'});
 };
 const dossier=e=>{
  const evidence=e.refs.map(proofFor);
  let body=`<nav class="atlas-breadcrumb" aria-label="설정 위치"><a href="${base}/world.html">설정집</a><span aria-hidden="true">›</span><a href="${base}/${e.category}.html">${e.category==='factions'?'세력':'세계관의 큰 설정'}</a></nav><p class="lore-kicker">${H(e.kind)}</p>`;
  body+=kit.section({id:'overview',title:e.name+'의 개요',items:[{text:e.summary,kind:'fact',evidence}]});
  if(e.id==='spacetrek-collective')body+=`<section id="organization"><h2>콜렉티브에 속한 교육·연구 기관</h2>${kit.containment({parent:'스페이스트렉 콜렉티브',children:[{name:'스타토치 아카데미',kind:'아카데미 도시',url:base+'/factions/startorch-academy.html'},{name:'스페이스트렉 콜렉티브 연구소',kind:'연구소',url:base+'/factions/spacetrek-institute.html'}],evidence:[evidence[0]]})}</section>`;
  if(e.id==='pangu-terminal')body+=`<section id="conversion"><h2>잔향을 에코로 바꾸는 과정</h2>${kit.process([{title:'잔상 처치',text:'잔상을 처치한다.',evidence},{title:'잔향 잔류',text:'일정 확률로 상응하는 잔향이 남는다.',evidence},{title:'에코 변환',text:'단말기의 데이터 스테이션을 통해 잔향을 에코로 변환한다.',evidence}],{kind:'steps',label:'에코 설명에 기록된 변환 과정'})}</section>`;
  if(e.id==='golden-shackles')body+=`<section id="mask-making"><h2>금쇄십계 마스크의 제작</h2>${kit.process([{title:'오계 · 연구와 설계',text:'악장이 얼굴을 잠식하는 원리를 연구하고 방호면의 설계안을 제시했다.',evidence:[evidence[1]]},{title:'이계 · 원형 제작',text:'방호면의 원형을 제작했다.',evidence:[evidence[1]]},{title:'사계 · 복제',text:'성능을 유지하며 복제해 열 개를 완성했다.',evidence:[evidence[1]]}],{kind:'steps',label:'마스크 원문에 기록된 제작 순서'})}</section>`;
  if(e.id==='sonoro-control')body+=`<section id="comparison"><h2>동명 보고서의 기록 비교</h2><p class="atlas-caption">자료 제목은 모두 제20차 연구 보고서입니다. 자료 식별자를 함께 표시해 각각의 기록을 대조합니다.</p>${kit.comparison(e.refs.slice(0,2).map((r,i)=>({title:r.label,text:r.excerpt,kind:'fact',evidence:[evidence[i]]})))}</section>`;
  body+=`<section class="atlas-evidence" id="evidence"><h2>원문으로 확인하기</h2>${e.refs.map((r,i)=>kit.section({id:'record-'+i,title:r.label,items:[{text:r.excerpt,kind:'fact',speaker:r.speaker||'',evidence:[evidence[i]]}]})).join('')}</section>`;
  const related=(e.relatedUrls||[]).map(url=>({name:relatedName(url),url,summary:''})).filter(n=>n.name);
  if(e.id==='sentinels')related.push(...['용의 별자리','임페라토르','여우의 별자리'].map(name=>({name,url:base+entityLinks.get(name),summary:'지역별 수호신의 기록과 권능'})));
  if(related.length)body+=`<section id="next"><h2>함께 읽는 인물과 지역</h2>${kit.directory(related)}</section>`;
  return body;
 };
 return {directory,dossier};
}
