export function createReadingSections({H,text,kit,model,claim,evidenceMap}){
 return c=>{const m=model(c);return (c.facts?`<dl class="setting-facts">${c.facts.map(([k,v])=>`<div><dt>${H(k)}</dt><dd>${text(v)}</dd></div>`).join('')}</dl>`:'')+m.sections.map(kit.section).join('')+(!m.topology&&m.process.length?kit.process(m.process.map(p=>({...p,...claim(p.claimId)})),{kind:m.processKind,label:m.processTitle||'에코를 이용하는 과정',returnLabel:m.returnLabel}):'');};
}
