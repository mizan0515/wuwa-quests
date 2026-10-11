(() => {
 const host=document.getElementById('dialogue-catalog');if(!host)return;
 const query=document.getElementById('dialogue-query'),kind=document.getElementById('dialogue-kind'),hide=document.getElementById('dialogue-hide-review'),reset=document.getElementById('dialogue-reset'),status=document.getElementById('dialogue-status'),results=document.getElementById('dialogue-results'),more=document.getElementById('dialogue-more');
 const labels={quest:'목록 밖 임무',level:'탐색·전투',entity:'현장 상호작용',config:'공용 상호작용',unreferenced:'연결 미확인'};
 let data=[],limit=24;
 const params=new URLSearchParams(location.search);query.value=params.get('q')||'';if([...kind.options].some(o=>o.value===params.get('kind')))kind.value=params.get('kind');hide.checked=params.get('review')!=='1';
 function render(){
  const value=query.value.trim().toLocaleLowerCase();
  const matching=data.filter(row=>(!hide.checked||!row.review)&&(kind.value==='all'||kind.value==='connected'?kind.value==='all'||row.kinds.some(k=>k!=='unreferenced'):row.kinds.includes(kind.value))&&(!value||[row.title,row.excerpt,...row.speakers,...row.regions].join(' ').toLocaleLowerCase().includes(value)));
  results.replaceChildren();
  for(const row of matching.slice(0,limit)){
   const article=document.createElement('article');article.className='dialogue-source-card';const h=document.createElement('h2'),link=document.createElement('a');link.href=row.page;link.textContent=row.title;h.append(link);
   const tags=document.createElement('p');tags.className='dialogue-source-meta';tags.textContent=[...row.kinds.map(k=>labels[k]),...row.regions,`${row.states.length}개 대화 상태`].join(' · ');
   const text=document.createElement('p');text.textContent=row.excerpt;article.append(tags,h,text);results.append(article);
  }
  status.textContent=`${matching.length}개 원문 묶음 · ${Math.min(limit,matching.length)}개 표시`;more.hidden=limit>=matching.length;
  const state=new URLSearchParams();if(query.value)state.set('q',query.value);if(kind.value!=='connected')state.set('kind',kind.value);if(!hide.checked)state.set('review','1');history.replaceState(null,'',location.pathname+(state.size?'?'+state:'')+location.hash);
 }
 function change(){limit=24;render();}
 query.addEventListener('input',change);kind.addEventListener('change',change);hide.addEventListener('change',change);more.addEventListener('click',()=>{limit+=24;render();});reset.addEventListener('click',()=>{query.value='';kind.value='connected';hide.checked=true;change();query.focus();});
 fetch(host.dataset.catalog).then(r=>{if(!r.ok)throw Error('catalog');return r.json();}).then(rows=>{data=rows;render();}).catch(()=>{status.textContent='목록을 불러오지 못했습니다. 페이지를 새로고침해 주세요.';});
})();
