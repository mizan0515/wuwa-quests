import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const hash=value=>createHash('sha256').update(value).digest('hex');
const jsonHash=value=>hash(JSON.stringify(value));
const assert=(condition,message)=>{if(!condition)throw Error(message);};
const bodyFields=new Set(['content','description','description_1','description_2']);
export function handbookReadingState(record){
 const bodies=record.values.filter(v=>bodyFields.has(v.field)&&v.status==='OK');
 if(!bodies.some(v=>v.text.trim()))return 'NO_KOREAN_BODY';
 const text=bodies.map(v=>v.text).join('\n').trim();
 if(/^(?:테스트|测试|test(?:ing)?)[.!。]?$/i.test(text))return 'TEST_CONTENT_ONLY';
 if(/(?<![A-Za-z])(?:xx+|XX+)(?![A-Za-z])/.test(text))return 'PLACEHOLDER_MARKER';
 return 'READABLE';
}
export async function loadHandbook(settings=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../settings')){
 const read=async name=>JSON.parse(await readFile(path.join(settings,name),'utf8'));
 const [index,manifest,provenance,relations]=await Promise.all(['index.json','manifest.json','handbook-provenance.json','source-relations.json'].map(read));
 const recordFiles=Object.keys(manifest.files).filter(n=>n.startsWith('records-'));
 const bundleList=await Promise.all(recordFiles.map(read));
 const records=Object.assign({},...bundleList);
 for(const [name,expected] of Object.entries(manifest.files)){
  const bytes=await readFile(path.join(settings,name)),input=manifest.hash_normalization?.[name]==='lf'?bytes.toString('utf8').replace(/\r\n/g,'\n'):bytes;
  assert(hash(input)===expected,'Settings manifest hash differs: '+name);
 }
 const preservedFiles=await Promise.all(Object.keys(provenance.preservation.record_files_sha256).map(async name=>[name,hash(await readFile(path.join(settings,name)))]));
 for(const [name,actual] of preservedFiles)assert(actual===provenance.preservation.record_files_sha256[name],'Original record bundle changed: '+name);
 // Intrinsic /Game/ texture tokens are preserved in raw Korean text. Host
 // filesystem paths are forbidden throughout the public JSON projection.
 for(const value of [index,manifest,provenance,relations,records])assert(!/[A-Za-z]:[\\/]|(?:\/Users\/|\/home\/|AppData[\\/])/.test(JSON.stringify(value)),'Host path in public settings');
 return {index,manifest,provenance,relations,records};
}
export function verifyHandbook({index,manifest,provenance,relations,records}){
 const preservation=provenance.preservation,count=preservation.baseline_reading_entries;
 const existing=index.entries.slice(0,count).map(({source_relations,...entry})=>entry);
 assert(jsonHash(existing)===preservation.entries_sha256,'Existing reading entry, source URL or alias membership changed');
 assert(jsonHash(index.aliases)===preservation.aliases_sha256,'Existing alias mapping changed');
 assert(jsonHash(index.curated_sources)===preservation.curated_sources_sha256,'Existing curated source mapping changed');
 const fresh=Object.values(records).filter(r=>r.reading_state),reading=index.entries.slice(count),diagnostics=index.diagnostic_entries||[];
 const all=new Map([...index.entries,...diagnostics].map(e=>[e.id,e]));
 assert(all.size===index.entries.length+diagnostics.length,'Duplicate reading/diagnostic ID');
 const readable=new Set(),diagnostic=new Set();
 for(const record of fresh){
  assert(record.reading_state===handbookReadingState(record),'Reading state differs: '+record.id);
  (record.reading_state==='READABLE'?readable:diagnostic).add(record.id);
  assert(all.get(record.id)?.reading_state===record.reading_state,'Reading entry state differs: '+record.id);
  assert(all.get(record.id)?.chunk&&all.get(record.id)?.page==='/library.html#/source/'+record.id,'Original source route missing: '+record.id);
  assert(/^[0-9a-f]{64}$/.test(record.source_bin_sha256),'Source blob hash missing');
 }
 assert(readable.size===reading.length&&reading.every(e=>readable.has(e.id)),'Default reading inclusion differs');
 assert(diagnostic.size===diagnostics.length&&diagnostics.every(e=>diagnostic.has(e.id)),'Diagnostic source access differs');
 assert(fresh.length===provenance.added_records&&reading.length===provenance.added_reading_entries,'Expansion count differs');
 assert(index.reading_entries===index.entries.length&&manifest.reading_entries===index.entries.length,'Reading count differs');
 assert(index.source_records===preservation.baseline_source_records+fresh.length&&manifest.original_records===index.source_records,'Source record count differs');
 const expected=new Map(),canonical=id=>index.aliases[id]||id;
 function attach(id,relation){assert(all.has(id),'Relation target missing: '+id);if(!expected.has(id))expected.set(id,[]);expected.get(id).push(relation);}
 const counts={};
 for(const relation of relations.relations){
  counts[relation.kind]=(counts[relation.kind]||0)+1;
  const source=relation.source;
  assert(/^[0-9a-f]{64}$/.test(source.source_bin_sha256),'Relation row blob hash missing');
  if(relation.kind==='tutorial_pages'){
   assert(source.db==='db_guide_new.db'&&source.table==='guidetutorial'&&source.pages_field_index===3,'Tutorial source schema differs');
   assert(source.type_semantics==='UNVERIFIED','Runtime type inference adopted');
   assert(relation.pages.length===source.page_ids.length,'Tutorial page omitted');
   relation.pages.forEach((page,i)=>{
    assert(page.order===i&&page.id==='튜토리얼_페이지:guidetutorialpage:'+source.page_ids[i],'Tutorial page ID/order inferred');
    assert(records[page.id]?.reading_state===page.reading_state&&records[page.id]?.title===page.title,'Tutorial page projection differs');
    attach(page.id,relation);
   });
  }else if(relation.kind==='cooking_formula'){
   assert(source.db==='db_cook.db'&&source.table==='cookformula','Cooking source schema differs');
   assert(source.field_indices.formula_item_id===1&&source.field_indices.food_item_id===2,'Cooking fields differ');
   assert(relation.formula_id===canonical('아이템_배경:iteminfo:'+source.formula_item_id)&&relation.food_id===canonical('아이템_배경:iteminfo:'+source.food_item_id),'Cooking references inferred');
   attach(relation.formula_id,relation);attach(relation.food_id,relation);
  }else if(relation.kind==='handbook_classification'){
   const record=records[relation.source_id];
   assert(record?.table==='monsterhandbook'&&record.entry_id===source.entry_id&&record.source_bin_sha256===source.source_bin_sha256,'Monster classification source differs');
   assert(source.field_index===2&&record.handbook_type_id===source.literal_value,'Monster classification field differs');
   assert(relation.classification_id==='도감_분류:monsterhandbooktype:'+source.literal_value,'Monster classification inferred');
   if(all.has(relation.source_id)){attach(relation.source_id,relation);assert(all.has(relation.classification_id),'Classification target missing');}
  }else if(relation.kind==='item_handbook'){
   assert(source.db==='db_handbook.db'&&source.table==='itemhandbook'&&source.type_field_index===1,'Item roster schema differs');
   assert(relation.item_id===canonical('아이템_배경:iteminfo:'+source.entry_id)&&relation.classification_id==='도감_분류:itemhandbooktype:'+source.type_id,'Item roster relation inferred');
   assert(source.title.field_index===2&&source.title.status==='OK','Item roster Korean title missing');
   attach(relation.item_id,relation);assert(all.has(relation.classification_id),'Item classification missing');
  }else if(relation.kind==='weapon_handbook'){
   assert(source.db==='db_handbook.db'&&source.table==='weaponhandbook','Weapon roster schema differs');
   assert(relation.weapon_id===canonical('무기_배경:weaponconf:'+source.entry_id),'Weapon roster reference inferred');
   attach(relation.weapon_id,relation);
  }else throw Error('Unknown source relation: '+relation.kind);
 }
 for(const entry of all.values())assert(JSON.stringify(entry.source_relations||[])===JSON.stringify(expected.get(entry.id)||[]),'Sidecar/index relationships differ: '+entry.id);
 assert(relations.unresolved.length===0,'Unresolved literal source relation');
 assert(provenance.installed_client_match==='UNVERIFIED'&&provenance.first_release_version==='UNVERIFIED','Unsupported version/first release claim');
 return {originalRecords:fresh.length,readingEntries:reading.length,diagnosticRoutes:diagnostics.length,relations:counts,preservedEntries:count};
}
