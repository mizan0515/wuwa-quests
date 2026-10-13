/** Local document return URL; reader identity requires the supplied source model. */
export function safeReadingReturn(value,{origin,base='/wuwa-quests',model,readersOnly=false}={}){
 if(typeof value!=='string'||!value.startsWith(base+'/')||/[\\\u0000-\u001f]/.test(value))return null;
 try{
  if(decodeURIComponent(value.split(/[?#]/)[0]).split('/').some(p=>p==='..'||p==='.'))return null;
  const url=new URL(value,origin);if(url.origin!==origin||!url.pathname.startsWith(base+'/'))return null;
  const rel=decodeURIComponent(url.pathname.slice(base.length+1));
  if(rel.split('/').some(p=>p==='..'||p==='.')||rel.includes('\\')||!/^[-A-Za-z0-9_/]+\.html$/.test(rel))return null;
  const match=rel.match(/^(quests|quest-sources|dialogue-sources)\/([A-Za-z0-9_-]+)\.html$/);
  if(readersOnly&&!match)return null;
  if(match){
   const [,,id]=match,kind=match[1],record=kind==='quests'?model?.quests[id]:kind==='quest-sources'?Object.values(model?.owners||{}).find(o=>o.id===id):model?.groups[id];
   if(model&&!record)return null;
   const hash=decodeURIComponent(url.hash.slice(1));
   if(hash){
    if(!/^(?:scene-\d+|state-[a-f0-9]{16}(?:-row-\d+)?)$/.test(hash))return null;
    if(record&&kind==='quests'&&!record.scenes.some(s=>'scene-'+s.number===hash))return null;
    if(record&&kind!=='quests'&&!record.states.some(s=>hash===s.anchor||s.rowIndices?.some(i=>hash===s.anchor+'-row-'+i)))return null;
   }
  }
  url.searchParams.delete('from');return url.pathname+url.search+url.hash;
 }catch{return null;}
}
