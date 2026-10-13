import {readdir,cp,stat,rm} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
const source=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');const site=path.resolve(source,'..');
const dist=path.join(source,'dist');
if(!(await stat(path.join(dist,'index.html'))).isFile())throw new Error('Build output missing');
execFileSync('python',['-B','-X','utf8','tools/share_publication_ui.py'],{cwd:source,stdio:'inherit'});
// The existing branch publisher applies _config.yml exclusions to build inputs.
await rm(path.join(site,'.nojekyll'),{force:true});
// Replace only generated asset directories so obsolete hashed bundles do not accumulate.
for(const name of ['_astro','pagefind','_shared-ui']){
 const target=path.resolve(site,name);
 if(!target.startsWith(site+path.sep)||path.dirname(target)!==site)throw new Error('Unexpected export target');
 await rm(target,{recursive:true,force:true});
}
for(const entry of await readdir(dist))await cp(path.join(dist,entry),path.join(site,entry),{recursive:true});
console.log('Exported static Starlight site to repository root');
