import {rowAttributes,htmlAttributes} from './reading-kit/reader.mjs';
export const H=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])).replace(/\r/g,'&#13;').replace(/\n/g,'&#10;');
/** Exact original row renderer shared by source and owner readers. */
export function dialogueSourceRows(state,anchor){
 let body='';
 for(const [index,row] of state.rows.entries()){
  if(row.status!=='OK')continue;
  const attrs=rowAttributes(row.kind==='선택지'?'choice':'dialogue');
  attrs.class+=' quest-source-line '+(row.kind==='선택지'?'quest-choice':'quest-utterance');
  attrs.id=anchor+'-row-'+index;attrs['data-dialogue-source-key']=row.text_id;
  body+=`<p ${htmlAttributes(attrs)}><strong class="quest-speaker">${H(row.speaker)}</strong><span class="quest-speech rw-source-body">${H(row.text)}</span></p>`;
  if(row.transition){const branch=rowAttributes('branch');branch.class+=' quest-branch';body+=`<p ${htmlAttributes(branch)}>${H(row.transition)}</p>`;}
 }
 return body;
}
