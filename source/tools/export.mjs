import {readdir,cp,stat} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const source=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');const site=path.resolve(source,'..');
const dist=path.join(source,'dist');
if(!(await stat(path.join(dist,'index.html'))).isFile())throw new Error('Build output missing');
for(const entry of await readdir(dist))await cp(path.join(dist,entry),path.join(site,entry),{recursive:true});
console.log('Exported static Starlight site to repository root');
