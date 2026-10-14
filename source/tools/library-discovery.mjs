import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import path from 'node:path';

// List rows and full source metadata have different loading lifetimes.
export function libraryProjection(index) {
 const fields=['id','entry_id','title','category','category_label','group','chunk','role_id','role_name','term_ids','excerpt','duplicate_count','page'];
 const row=entry=>Object.fromEntries(fields.filter(key=>key in entry).map(key=>[key,entry[key]]));
 const details={};
 for(const entry of [...index.entries,...(index.diagnostic_entries||[])]) (details[entry.chunk]??={})[entry.id]=entry;
 return {catalog:{entries:index.entries.map(row),aliases:index.aliases,categories:index.categories},diagnostics:(index.diagnostic_entries||[]).map(row),details};
}

export async function writeLibraryProjection(index,directory) {
 const projected=libraryProjection(index);
 await writeFile(path.join(directory,'library-index.json'),JSON.stringify(projected.catalog));
 await writeFile(path.join(directory,'library-diagnostics.json'),JSON.stringify(projected.diagnostics));
 for(const [chunk,entries] of Object.entries(projected.details)) await writeFile(path.join(directory,'library-details-'+chunk+'.json'),JSON.stringify(entries));
 return createHash('sha256').update(JSON.stringify(index)).digest('hex').slice(0,12);
}

export function originalSearchRecords(index,records,curated) {
 return index.entries.filter(e=>e.group!=='technical'&&!curated[e.id]).map(e=>{
  const record=records[e.id];
  if(!record)throw Error('Search source missing: '+e.id);
  const content=[e.title,...record.values.filter(v=>v.status==='OK').map(v=>v.text)].join('\n');
  return {url:e.page,content,language:'ko',meta:{title:e.title,category:e.category_label}};
 });
}
