import {readFile,readdir,rm} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import * as pagefind from 'pagefind';
import {originalSearchRecords} from './library-discovery.mjs';

const check=result=>{if(result.errors?.length)throw Error(result.errors.join('\n'));return result;};
export function originalSearchIntegration(){
 return {name:'wuwa-original-search',hooks:{'astro:build:done':async({dir,logger})=>{
  // The generated public projection contains the authoritative canonical targets.
  const publicSettings=path.join(fileURLToPath(dir),'settings');
  const read=async name=>JSON.parse(await readFile(path.join(publicSettings,name),'utf8'));
  const index=await read('index.json'),curated=(await read('curated-sources.json')).sources,records={};
  for(const name of await readdir(publicSettings))if(/^records-.+\.json$/.test(name))Object.assign(records,await read(name));
  const extra=originalSearchRecords(index,records,curated);
  try{
   const {index:search}=check(await pagefind.createIndex());
   check(await search.addDirectory({path:fileURLToPath(dir)}));
   for(const record of extra)check(await search.addCustomRecord(record));
   // Replace the generated index as one version; keep no orphaned old fragments.
   await rm(path.join(fileURLToPath(dir),'pagefind'),{recursive:true,force:true});
   check(await search.writeFiles({outputPath:path.join(fileURLToPath(dir),'pagefind')}));
   logger.info('Global search includes '+extra.length+' additional original records.');
  }finally{await pagefind.close();}
 }}};
}
