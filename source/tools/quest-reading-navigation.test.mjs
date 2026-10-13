import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {deriveQuestReadingContext} from '../src/lib/quest-reading-context.mjs';
import {safeReadingReturn} from '../src/lib/reading-return.mjs';
import {dialogueSourceRows} from '../src/lib/dialogue-source-rows.mjs';
const site=new URL('../../',import.meta.url),json=async rel=>JSON.parse(await readFile(new URL(rel,site),'utf8'));
const attribution=await json('settings/dialogue-attribution.json'),catalog=await json('content-manifest.json');
const model=deriveQuestReadingContext(attribution,catalog);
test('whole source context keeps ownership separate and covers all inverse pairs',()=>{
 assert.deepEqual(model.counts,{quests:766,groups:687,owners:14,sameSourcePairs:781,sameSourceSceneReferences:8146});
 for(const quest of Object.values(model.quests))for(const group of quest.relatedSources){assert.equal(group.relation,'SAME_SOURCE_CONTEXT');assert.ok(model.groups[group.id].relatedQuests.some(q=>q.id===quest.id));}
 for(const owner of Object.values(model.owners))for(const state of owner.states){assert.deepEqual(state.proof,attribution.states[state.key].owners[owner.key].proof);assert.ok(state.proof.length);}
 const native=JSON.parse(requireRaw('settings/native-sequence-references.json'));for(const key of Object.keys(native.states))assert.ok(!Object.values(model.owners).some(o=>o.states.some(s=>s.key===key)));
});
// Source native state inventory is synchronously read once by the test, never mutated.
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
function requireRaw(rel){return readFileSync(new URL(rel,site),'utf8');}
test('all actual owner names and IDs remain findable beyond a two-title group heading',()=>{
 const group=model.groups['2028bf0f73ed0151'];
 for(const id of ['184850006','184850007']){assert.ok(group.ownerIds.includes(id));assert.ok(group.ownerTitles.includes(model.owners['quest:'+id].title));}
 const split=model.owners['quest:165800015'];assert.equal(split.states.length,6);assert.equal(new Set(split.states.map(s=>s.groupId)).size,2);
});
test('unnamed/test roots and context similarity cannot create owner readers',()=>{
 const a={owners:{'quest:1':{kind:'quest',id:'1',title:'실제 소유',type:11},'quest:2':{kind:'quest',id:'2',title:'',type:11},'quest:3':{kind:'quest',id:'3',title:'시험',type:100}},states:{state:{owners:{'quest:1':{proof:['quest:1/Reference/0']},'quest:2':{proof:['quest:2/Reference/0']},'quest:3':{proof:['quest:3/Reference/0']}},rows:[{status:'OK',kind:'대사',speaker:'화자'}]}},groups:[{id:'g',title:'같은 이름',states:['state'],existing_scenes:[{quest_id:'9',scene:1,state_key:'different'}]}]};
 const m=deriveQuestReadingContext(a,[{id:'9',title:'기존 임무'}]);assert.deepEqual(Object.keys(m.owners),['quest:1']);assert.equal(m.quests['9'].relatedSources[0].relation,'SAME_SOURCE_CONTEXT');assert.equal(m.owners['quest:1'].states.length,1);
 a.states.state.owners['quest:1'].proof=[];assert.throws(()=>deriveQuestReadingContext(a,[{id:'9'}]),/source chain/);
});
test('return routes reject external/traversal/false identity and preserve actual source row anchors',()=>{
 const owner=model.owners['quest:165800015'],state=owner.states[0],origin='https://example.test',opts={origin,model,readersOnly:true};
 const valid='/wuwa-quests/'+owner.url+'#'+state.anchor+'-row-'+state.rowIndices[0];assert.equal(safeReadingReturn(valid,opts),valid);
 for(const bad of ['https://evil.test/wuwa-quests/'+owner.url,'//evil.test','/wuwa-quests/quests/../'+owner.url,'/wuwa-quests/%2e%2e/secret.html','/wuwa-quests/quest-sources/99999999.html','/wuwa-quests/'+owner.url+'#state-0000000000000000',valid.replace(/-row-\d+$/,'-row-999999')])assert.equal(safeReadingReturn(bad,opts),null,bad);
 assert.equal(safeReadingReturn('/wuwa-quests/'+owner.url+'?from=https%3A%2F%2Fevil.test',opts),'/wuwa-quests/'+owner.url);
});
test('shared row renderer retains choice, branch, source row index and escaped Korean originals',()=>{
 const state={rows:[{status:'MISSING',text:'미수록'},{status:'OK',kind:'선택지',speaker:'선택',text:'원문 <태그> & 그대로\n둘째 줄',text_id:'id',transition:'대화ID 7로 이동'}]};
 const html=dialogueSourceRows(state,'state-example');assert.ok(!html.includes('미수록'));assert.ok(html.includes('id="state-example-row-1"'));assert.ok(html.includes('data-reading-kind="choice"'));assert.ok(html.includes('data-reading-kind="branch"'));assert.ok(html.includes('원문 &lt;태그&gt; &amp; 그대로&#10;둘째 줄'));assert.ok(html.includes('대화ID 7로 이동'));
});
test('actual legacy context controller accepts local reading returns and rejects URL escapes',()=>{
 const code=requireRaw('source/public/lore/context.js');
 function run(from){
  const bars=[],element=tag=>({tag,children:[],append(...children){this.children.push(...children);},setAttribute(){}});
  const context={URL,URLSearchParams,location:{origin:'https://example.test',pathname:'/wuwa-quests/concepts/0.html',search:'?from='+encodeURIComponent(from)},sessionStorage:{getItem(){return null;}},document:{createElement:element,querySelector(){return{prepend(bar){bars.push(bar);}};}}};vm.runInNewContext(code,context);return bars;
 }
 for(const bad of ['https://evil.test/wuwa-quests/quests/1.html','/wuwa-quests/quests/../quests/1.html','/wuwa-quests/%2e%2e/private.html','/wuwa-quests/quests\\1.html'])assert.equal(run(bad).length,0);
 const bars=run('/wuwa-quests/quest-sources/165800015.html#state-abcdefabcdefabcd-row-1');assert.equal(bars.length,1);assert.equal(bars[0].children[0].href,'/wuwa-quests/quest-sources/165800015.html#state-abcdefabcdefabcd-row-1');
 const source='/wuwa-quests/dialogue-sources/2028bf0f73ed0151.html',original='/wuwa-quests/quests/121800000.html#scene-1';
 assert.equal(new URL(run(source+'?from='+encodeURIComponent(original))[0].children[0].href,'https://example.test').searchParams.get('from'),original);
 assert.equal(new URL(run(source+'?from='+encodeURIComponent('https://evil.test/'))[0].children[0].href,'https://example.test').searchParams.has('from'),false);
});
