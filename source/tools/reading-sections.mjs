import {readerFrame} from '../src/lib/reading-kit/reader.mjs';
export function createReadingSections({H,text,kit,model,claim,evidenceMap}){
 return c=>{const m=model(c);
  const explained=new Set(m.sections.filter(s=>!s.id.startsWith('dialogue-')).flatMap(s=>s.items.flatMap(i=>i.evidence.map(e=>e.id))));
  const visible=m.sections.filter(s=>!s.id.startsWith('dialogue-')||!s.items.every(i=>i.evidence.every(e=>explained.has(e.id))));
  return (c.facts?readerFrame(`<dl class="setting-facts">${c.facts.map(([k,v])=>`<div><dt>${H(k)}</dt><dd>${text(v)}</dd></div>`).join('')}</dl>`,{variant:'record',className:'setting-facts-reader'}):'')+visible.map(kit.section).join('')+((!m.topology||c.show_process)&&m.process.length?kit.process(m.process.map(p=>({...p,...claim(p.claimId)})),{kind:m.processKind,label:m.processTitle||'함께 읽는 흐름',returnLabel:m.returnLabel}):'');};
}
