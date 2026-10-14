import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {libraryProjection,originalSearchRecords} from './library-discovery.mjs';
const read=name=>JSON.parse(readFileSync(new URL('../../settings/'+name,import.meta.url),'utf8'));
const index=read('index.json'),records={};
for(const name of readdirSync(new URL('../../settings/',import.meta.url)))if(/^records-.+\.json$/.test(name))Object.assign(records,read(name));
test('split list and detail preserve every canonical record, diagnostic, alias and relation',()=>{
 const {catalog,details,diagnostics}=libraryProjection(index);
 assert.deepEqual(catalog.entries.map(e=>e.id),index.entries.map(e=>e.id));
 assert.deepEqual(catalog.aliases,index.aliases);
 assert.deepEqual(diagnostics.map(e=>e.id),(index.diagnostic_entries||[]).map(e=>e.id));
 for(const e of [...index.entries,...(index.diagnostic_entries||[])])assert.deepEqual(details[e.chunk][e.id],e);
 assert(Buffer.byteLength(JSON.stringify(catalog))<Buffer.byteLength(JSON.stringify(index))*.85);
});
test('global search covers all uncurated readable originals with exact title, Korean body and route',()=>{
 const curated=index.curated_sources,extra=originalSearchRecords(index,records,curated),byUrl=new Map(extra.map(e=>[e.url,e]));
 for(const e of index.entries.filter(e=>e.group!=='technical'&&!curated[e.id])){
  const result=byUrl.get(e.page);assert(result,e.id);
  assert.equal(result.meta.title,e.title);
  for(const v of records[e.id].values.filter(v=>v.status==='OK'))assert(result.content.includes(v.text));
 }
 assert(!extra.some(e=>e.meta.category==='환경설정 UI'));
 const whisper=extra.find(e=>e.meta.title==='뭇별의 속삭임');assert(whisper);
 assert(whisper.url.endsWith('/source/게임_도움말:helptext:420'));
 assert(whisper.content.includes('시그리카와 함께 첫 번째 수수께끼'));
 assert.throws(()=>originalSearchRecords(index,{},curated),/Search source missing/);
});
