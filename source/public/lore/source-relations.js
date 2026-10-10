/* Literal table relationships shared by generated and on-demand readers. */
export const stripOriginalAssetMarkup=raw=>raw.replace(/<texture\b[^>]*>/gi,'');
export function sourceRelations(record, {entry, url, escape: H}) {
 const links=(record.source_relations||[]).map(relation=>{
  if(relation.kind==='tutorial_pages'){
   const source=relation.source;
   const pages=relation.pages.map(page=>{
    const target=entry(page.id),state=page.reading_state==='READABLE'?'':' · 한국어 본문·상태 확인';
    return `<li>${target?`<a data-reading-link href="${H(url(target))}">${H(page.title)}${H(state)}</a>`:`${H(page.title)} · 페이지 기록 미확인`}</li>`;
   }).join('');
   return `<section class="lore-source-relations"><h2>${H(relation.title)} · 튜토리얼 페이지</h2><p class="lore-muted">같은 튜토리얼에 수록된 페이지의 자료 순서입니다.</p><ol>${pages}</ol><details class="lore-provenance rw-disclosure not-content" data-reading-template="disclosure"><summary>페이지 연결의 출처</summary><p>${H(source.db)} / ${H(source.table)} · ${H(source.entry_id)} · 페이지 배열 필드 ${H(source.pages_field_index)}</p></details></section>`;
  }
  if(relation.kind==='cooking_formula'){
   const formula=entry(relation.formula_id),food=entry(relation.food_id);
   if(!formula||!food)return '';
   return `<section class="lore-source-relations"><h2>레시피와 완성 요리</h2><p><a data-reading-link href="${H(url(formula))}">${H(formula.title)}</a> → <a data-reading-link href="${H(url(food))}">${H(food.title)}</a></p><details class="lore-provenance rw-disclosure not-content" data-reading-template="disclosure"><summary>조리 연결의 출처</summary><p>${H(relation.source.db)} / ${H(relation.source.table)} · ${H(relation.source.entry_id)} · 레시피 아이템 필드 1 / 완성 요리 필드 2</p></details></section>`;
  }
  if(relation.kind==='handbook_classification'){
   const target=entry(relation.classification_id);
   if(!target)return '';
   return `<section class="lore-source-relations"><h2>도감의 분류</h2><p><a data-reading-link href="${H(url(target))}">${H(target.title)}</a></p><details class="lore-provenance rw-disclosure not-content" data-reading-template="disclosure"><summary>분류 연결의 출처</summary><p>${H(relation.source.db)} / ${H(relation.source.table)} · ${H(relation.source.entry_id)} · 분류 필드 ${H(relation.source.field_index)}</p></details></section>`;
  }
  if(relation.kind==='item_handbook'){
   const target=entry(relation.classification_id),source=relation.source;
   if(!target)return '';
   return `<section class="lore-source-relations"><h2>아이템 도감의 분류</h2><p>${H(source.title.text)} · <a data-reading-link href="${H(url(target))}">${H(target.title)}</a></p><details class="lore-provenance rw-disclosure not-content" data-reading-template="disclosure"><summary>도감 수록의 출처</summary><p>${H(source.db)} / ${H(source.table)} · ${H(source.entry_id)} · 분류 필드 ${H(source.type_field_index)} / 표제 필드 2</p><p>${H(source.title.text_id)} · ${H(source.title.locale_db)}</p><pre>${H(source.title.raw)}</pre></details></section>`;
  }
  if(relation.kind==='weapon_handbook'){
   const source=relation.source;
   return `<details class="lore-provenance rw-disclosure not-content" data-reading-template="disclosure"><summary>무기 도감 수록의 출처</summary><p>${H(source.db)} / ${H(source.table)} · ${H(source.entry_id)}</p></details>`;
  }
  return '';
 });
 return links.join('');
}
