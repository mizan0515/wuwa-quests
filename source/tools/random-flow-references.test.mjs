import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import {validateRandomFlowReferences,randomFlowDisclosure} from '../src/lib/random-flow-references.mjs';

const site=new URL('../../',import.meta.url);
const load=async name=>JSON.parse(await readFile(new URL('settings/'+name,site),'utf8'));
const original=await load('dialogue-attribution.json'),overlay=await load('random-flow-references.json');
const originalBefore=JSON.stringify(original);

test('fixed conditional targets preserve originals and separate recipients from speakers',()=>{
 validateRandomFlowReferences(overlay,original);
 assert.equal(Object.keys(overlay.states).length,73);assert.equal(Object.keys(overlay.references).length,222);
 for(const [key,refs]of Object.entries(overlay.states)){
  const html=randomFlowDisclosure(overlay,key,original);
  assert.ok(html.includes('말풍선 연결 · 조건부'));
  assert.ok(html.includes('실제 플레이에서 표시된 시점은 미확인'));
  assert.ok(html.includes('원문 화자:'));assert.ok(html.includes('말풍선 표시 대상:'));
  assert.ok(html.includes('data-pagefind-ignore="all"'));
  for(const id of refs)assert.ok(html.includes(`data-random-flow-proof="${id}"`));
  for(const id of refs){const r=overlay.references[id],rate=['hit','monster'].includes(r.consumer)?r.conditions.find(c=>c.pointer.endsWith('/BubbleRate'))?.value:undefined;if(rate!==undefined)assert.ok(html.includes(`설정된 말풍선 확률: ${rate}%`));}
 }
 assert.equal(JSON.stringify(original),originalBefore);
 assert.equal(randomFlowDisclosure(overlay,'not-a-conditional-state',original),'');
});

for(const [name,change]of [
 ['live execution claim',r=>r.runtimeObserved=true],
 ['quest attribution',r=>r.questId=123],
 ['geographic attribution',r=>r.region='guessed'],
 ['speaker replacement',r=>r.speaker='recipient'],
 ['truthy exact state promoted',r=>r.input.StateId=1],
 ['unknown consumer',r=>r.consumer='bump'],
 ['missing original',r=>r.targets=['not-an-original']],
])test('rejects '+name,()=>{
 const changed=structuredClone(overlay);change(Object.values(changed.references)[0]);
 assert.throws(()=>validateRandomFlowReferences(changed,original));
});

test('recipient labels and original proof remain escaped HTML',()=>{
 const changed=structuredClone(overlay),[key,refs]=Object.entries(changed.states)[0];
 const r=changed.references[refs[0]],labels=structuredClone(original);
 labels.owners[`entity:${r.source.mapId}:${r.recipientEntityIds[0]}`]={title:'<img src=x onerror=alert(1)>'};
 const html=randomFlowDisclosure(changed,key,labels);
 assert.ok(!html.includes('<img src=x'));assert.ok(html.includes('&lt;img'));
});
