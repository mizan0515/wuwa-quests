// Publish the requested settings addition while keeping existing quest HTML and
// its hashed assets available. The full export remains the normal rebuild path.
import {cp,stat,unlink} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const source=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),site=path.dirname(source),dist=path.join(source,'dist');
for(const name of ['entities','regions.html','regions','cosmology.html','cosmology','sentinels.html','sentinels','relationships.html','events.html','quests','world.html','world','people.html','people','concepts.html','concepts','library.html','sources','lore','settings','index.html','about.html','_astro','pagefind','sitemap-index.xml','sitemap-0.xml']){
 const from=path.resolve(dist,name),to=path.resolve(site,name);
 if(!from.startsWith(dist+path.sep)||!to.startsWith(site+path.sep))throw Error('Export target outside repository');
 await stat(from);await cp(from,to,{recursive:true});
}
await unlink(path.join(site,'world/evidence.html')).catch(e=>{if(e.code!=='ENOENT')throw e;});
console.log('Exported settings, main entry and unified search. Existing quests and hashed bundles preserved.');
