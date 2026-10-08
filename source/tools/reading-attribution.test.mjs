import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {claimAttribution,readingReferences} from './reading-data.mjs';
import {createReadingGraph} from '../src/lib/reading-kit/graph.mjs';

const site=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');

test('아브의 정체에 관한 크리스토포로 발언은 인용 화자와 함께 남는다',()=>{
 const npc=JSON.parse(readFileSync(path.join(site,'settings/npc-people.json'),'utf8'));
 const edge=npc.people.find(p=>p.id==='ab').edges.find(e=>e.a==='크리스토포로');
 assert.equal(edge.speaker,undefined);
 const attribution=claimAttribution(edge);
 assert.deepEqual(attribution,{kind:'attributed',speaker:'크리스토포로'});
 const q=edge.refs[0],raw=readFileSync(path.join(site,'originals',q.quest_id+'.txt'),'utf8');
 const matches=[...raw.matchAll(/^장면 (\d+):/gm)],i=matches.findIndex(m=>Number(m[1])===q.scene);
 assert(i>=0);
 const scene=raw.slice(matches[i].index,matches[i+1]?.index||raw.length);
 assert(scene.split(/\r?\n/).some(line=>line.includes(q.speaker+':')&&line.includes(q.quote)));
 const graph=createReadingGraph({game:'wuwa',sources:[{id:'quest-'+q.quest_id,title:q.title,blocks:[{id:'scene-'+q.scene,anchor:'scene-'+q.scene,text:scene,url:'/quests/'+q.quest_id+'.html#scene-'+q.scene}]}]});
 graph.claim(edge.reason,readingReferences([q]),attribution);
 const output=graph.output({});
 assert.equal(output.claims[0].kind,'attributed');
 assert.equal(output.claims[0].speaker,'크리스토포로');
 assert.equal(output.evidence[0].speaker,'크리스토포로');
 assert.equal(output.evidence[0].quote,q.quote);
});

test('명시한 발언 주체와 여러 인용 화자를 각각 보존한다',()=>{
 assert.deepEqual(claimAttribution({speaker:'기염',refs:[{speaker:'화자ID 83'}]}),{kind:'attributed',speaker:'기염'});
 assert.equal(claimAttribution({refs:[{speaker:'양양'},{speaker:'양양'},{speaker:'파수인'}]}).speaker,'양양 · 파수인');
 assert.equal(readingReferences([{quest_id:'1',scene:2,quote:'본문',speaker:'화자ID 83'}])[0].speaker,'화자ID 83');
});

test('체포 선언과 화면 기록을 함께 인용하면 두 기록 주체가 남는다',()=>{
 const relation={refs:[{speaker:'금희',quote:'체포 선언'},{speaker:'화면 문구',quote:'체포 결과'}]};
 assert.deepEqual(claimAttribution(relation),{kind:'attributed',speaker:'금희 · 화면 문구'});
 assert.equal(readingReferences(relation.refs.map((r,i)=>({...r,quest_id:'1',scene:i+1})))[1].speaker,'화면 문구');
});

test('편집 연결과 화자 메타데이터가 없는 기록을 구분한다',()=>{
 assert.equal(claimAttribution({kind:'reading',refs:[{speaker:'양양'}]}).kind,'inference');
 assert.deepEqual(claimAttribution({refs:[{id:'기록',field:'본문'}]}),{kind:'explicit',speaker:''});
 assert.equal(readingReferences([{id:'기록',field:'본문',excerpt:'원문',speaker:'기록자'}])[0].speaker,'기록자');
});
