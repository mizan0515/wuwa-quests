export function createReadingSections({H,text,refs}){
 const sections=c=>(c.facts?`<dl class="setting-facts">${c.facts.map(([k,v])=>`<div><dt>${H(k)}</dt><dd>${text(v)}</dd></div>`).join('')}</dl>`:'')+(c.sections?`<div class="setting-sections">${c.sections.map((s,i)=>`<section id="section-${i}"><h2>${H(s.title)}</h2><p>${text(s.text)}</p>${refs(s.refs)}</section>`).join('')}</div>`:'')+(c.process?`<h2>${H(c.process_title||'에코를 이용하는 과정')}</h2><ol class="setting-process ${c.process_kind==='cycle'?'setting-cycle':''}">${c.process.map(s=>`<li><h3>${H(s.title)}</h3><p>${text(s.text)}</p>${refs(s.refs)}</li>`).join('')}</ol>${c.process_kind==='cycle'?'<p class="setting-cycle-return">새로운 에코 → 분해·제련으로 이어지는 순환</p>':''}`:'')+(c.containment?`<h2>${H(c.containment.title)}</h2><div class="setting-containment"><strong>${text(c.containment.parent)}</strong><ul>${c.containment.children.map(n=>`<li>${text(n)}</li>`).join('')}</ul>${refs(c.containment.refs)}</div>`:'');

 return sections;
}
