import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {claimAttribution,readingReferences,entityKindIndex,clusterNodeKinds,localClusterKinds} from './reading-data.mjs';
import {clusterGameMedia} from './generate-atlas.mjs';
import {createReadingGraph,resolveCluster} from '../src/lib/reading-kit/graph.mjs';
import {createReadingKit,escapeHtml} from '../src/lib/reading-kit/render.mjs';
import {createReadingSections} from './reading-sections.mjs';

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

const json=file=>JSON.parse(readFileSync(path.join(site,file),'utf8'));
const atlas=json('settings/atlas.json'),index=json('settings/index.json'),book=json('settings/editorial.json');
atlas.people.push(...json('settings/npc-people.json').people);
const groups=['regions','sentinels','cosmology','factions','people'];
const clusters=groups.flatMap(group=>atlas[group].map(c=>({group,c})));
const kindIndex=entityKindIndex({index,atlas,book});

test('전체 등록부의 분류와 관계마다 원문에 기록한 역할을 보존한다',()=>{
 let endpoints=0;
 const prior=json('source/public/reading-data/graph.json');
 for(const e of prior.entities){assert(kindIndex.has(e.name),e.name+' has no source registry class');assert.notEqual(kindIndex.get(e.name),'설정 대상');}
 for(const concept of book.concepts)assert(kindIndex.has(concept.name));
 for(const {group,c} of clusters){
  const nodeKinds=clusterNodeKinds(c),declared=new Map(c.nodes.map(n=>[n.name,n.kind]));
  assert.deepEqual(nodeKinds,c.nodes.map(n=>({name:n.name,kind:n.kind})));
  for(const n of c.nodes)assert.notEqual(kindIndex.get(n.name),'설정 대상',group+'/'+c.id+' / '+n.name);
  const relations=c.edges.map(e=>({from:{name:e.a,kind:kindIndex.get(e.a)},to:{name:e.b,kind:kindIndex.get(e.b)}}));
  const local=localClusterKinds({nodeKinds,relations});
  for(const [i,r] of local.relations.entries())for(const end of ['from','to']){
   const name=r[end].name;
   assert.equal(r[end].kind,declared.get(name)||kindIndex.get(name));
   assert.equal(relations[i][end].kind,kindIndex.get(name));
   endpoints++;
  }
 }
 assert.equal(endpoints,clusters.reduce((n,{c})=>n+c.edges.length*2,0));
 for(const c of atlas.sentinels){
  const name=c.title.split(' · ')[0];
  assert.equal(kindIndex.get(name),index.characters.some(p=>p.name===name)?'인물':'수호신');
 }
 // Independent examples cover places, organizations and named creatures;
 // local role labels remain available separately from the shared class.
 assert.equal(kindIndex.get('라군나'),'지역');
 assert.equal(kindIndex.get('승소산'),'지역');
 assert.equal(kindIndex.get('레비아탄'),'명식');
 assert.equal(kindIndex.get('임페라토르'),'수호신');
 assert.equal(kindIndex.get('에리스'),'인물');
 assert.equal(kindIndex.get('자원과'),'세력');
 for(const name of ['잔향','잔상','에코','공명자','오버클럭','수호신'])assert.equal(kindIndex.get(name),'개념');
 assert.equal(kindIndex.get('스타토치 아카데미'),'세력');
});

test('서로 다른 분류와 미확인 역할 충돌을 이름만으로 합치지 않는다',()=>{
 const copy=()=>structuredClone(atlas);
 let a=copy();a.people[0].nodes.find(n=>n.name==='스카').kind='세력';
 assert.throws(()=>entityKindIndex({index,atlas:a}),/conflicts with canonical/);
 a=copy();a.people[0].nodes.find(n=>n.name==='스카').kind='명식';
 assert.throws(()=>entityKindIndex({index,atlas:a}),/conflicts with canonical/);
 a=copy();a.regions[0].nodes.push({name:'새 대상',kind:'지역'});a.factions[0].nodes.push({name:'새 대상',kind:'인물'});
 assert.throws(()=>entityKindIndex({index,atlas:a}),/Conflicting declared/);
 a=copy();a.regions[0].nodes.push({name:'미확인 대상',kind:'미확인 역할 A'});a.factions[0].nodes.push({name:'미확인 대상',kind:'미확인 역할 B'});
 assert.throws(()=>entityKindIndex({index,atlas:a}),/Conflicting declared/);
 a=copy();a.factions.push({...a.factions[0],title:index.characters[0].name});
 assert.throws(()=>entityKindIndex({index,atlas:a}),/Conflicting canonical/);
 assert.throws(()=>clusterNodeKinds({id:'duplicate',nodes:[{name:'대상',kind:'인물'},{name:'대상',kind:'간부'}]}),/Conflicting local/);
 a=copy();a.regions.push({...a.regions[0],title:'임페라토르'});
 assert.throws(()=>entityKindIndex({index,atlas:a,book}),/Conflicting canonical/);
 const duplicateBook=structuredClone(book);duplicateBook.concepts.push({...duplicateBook.concepts[0]});
 assert.throws(()=>entityKindIndex({index,atlas,book:duplicateBook}),/duplicate canonical concept/);
});

test('세계관 탐색 축에 독립 본문을 추가해도 원문의 대상 분류를 보존한다',()=>{
 for(const kind of ['명식','잔상','재난']){
  const a=structuredClone(atlas);
  a.cosmology.push({id:'source-class',title:'분류 검증 대상',nodes:[{name:'분류 검증 대상',kind}]});
  assert.equal(entityKindIndex({index,atlas:a,book}).get('분류 검증 대상'),kind);
 }
});

const records=Object.assign({},...readdirSync(path.join(site,'settings')).filter(f=>/^records-.*\.json$/.test(f)).map(f=>json('settings/'+f)));
const imageManifest=json('source/public/game-images/provenance.json');
const refs=value=>value&&typeof value==='object'&&!Array.isArray(value)&&value.id&&value.source_text_sha256?[value]:value&&typeof value==='object'?Object.values(value).flatMap(refs):[];

test('전체 클러스터의 초점 이미지는 같은 인물 프로필과 정확한 게임 이미지 매핑을 갖는다',()=>{
 let focused=0;
 for(const {c} of clusters){
  const person=index.characters.find(p=>p.name===c.title.split(' · ')[0]);
  const profile=person&&'인물_프로필_공명기록:favorroleinfo:'+person.id;
  const sourceRefs=refs(c).filter(r=>(index.aliases[r.id]||r.id)===profile);
  const asset=person&&imageManifest.people.find(p=>p.id===person.id);
  const images=clusterGameMedia(c,{index,records,imageManifest});
  const portraits=images.filter(im=>im.caption.startsWith('게임 인물 이미지 · '));
  if(!person||!sourceRefs.length||!asset?.images.portrait){assert.equal(portraits.length,0);continue;}
  assert.equal(portraits.length,1);
  assert.equal(portraits[0].url,asset.images.portrait.url);
  assert.equal(portraits[0].bodyUrl,'/wuwa-quests/people/'+person.id+'.html#field-info');
  assert.equal(asset.name,person.name);
  assert.equal(String(asset.mapping.id),person.id);
  const bytes=readFileSync(path.join(site,'source/public',portraits[0].url.replace('/wuwa-quests/','')));
  assert.equal(createHash('sha256').update(bytes).digest('hex'),asset.images.portrait.sha256);
  for(const ref of sourceRefs){
   const value=records[profile].values.find(v=>v.field===ref.field);
   assert.equal(createHash('sha256').update(value.raw).digest('hex'),ref.source_text_sha256);
   assert(value.text.includes(ref.excerpt));
  }
  focused++;
 }
 assert(focused>0);
});

test('같은 이름·관련 인물·손상된 식별자로 초점 이미지를 가져오지 않는다',()=>{
 const original=clusters.find(({c})=>index.characters.some(p=>p.name===c.title.split(' · ')[0])&&refs(c).some(r=>r.id.startsWith('인물_프로필_공명기록:'))).c;
 const person=index.characters.find(p=>p.name===original.title.split(' · ')[0]);
 let c=structuredClone(original);c.title='다른 초점';
 assert.equal(clusterGameMedia(c,{index,records,imageManifest}).filter(im=>im.caption.startsWith('게임 인물 이미지')).length,0);
 c={id:original.id,title:original.title,nodes:original.nodes};
 assert.equal(clusterGameMedia(c,{index,records,imageManifest}).filter(im=>im.caption.startsWith('게임 인물 이미지')).length,0);
 let manifest=structuredClone(imageManifest);manifest.people.find(p=>p.id===person.id).name='이름이 다른 인물';
 assert.throws(()=>clusterGameMedia(original,{index,records,imageManifest:manifest}),/source mapping differs/);
 let rows=structuredClone(records);rows['인물_프로필_공명기록:favorroleinfo:'+person.id].role_id=999999;
 assert.throws(()=>clusterGameMedia(original,{index,records:rows,imageManifest}),/profile identity differs/);
 c=structuredClone(original);const ref=refs(c).find(r=>r.id==='인물_프로필_공명기록:favorroleinfo:'+person.id);ref.source_text_sha256='0'.repeat(64);
 assert.throws(()=>clusterGameMedia(c,{index,records,imageManifest}),/profile evidence differs/);
});

test('천연과 레비아탄의 본체 도감 이미지를 관련 창조물보다 먼저 보여준다',()=>{
 for(const name of ['천연','레비아탄']){
  const c=clusters.find(({c})=>c.title.split(' · ')[0]===name)?.c;
  assert(c,name+' has no authored original body');
  const manifest=structuredClone(imageManifest);
  manifest.monsters.reverse();
  const images=clusterGameMedia(c,{index,records,imageManifest:manifest});
  assert(images.length>1,name+' should also retain related subject images');
  assert(images[0].caption.startsWith('게임 도감 이미지 · '));
  assert(images[0].caption===('게임 도감 이미지 · '+name)||images[0].caption.endsWith(' · '+name));
  const original=imageManifest.monsters.find(m=>m.name===name||m.name.endsWith(' · '+name));
  assert.equal(images[0].url,original.images.icon.url);
  for(const image of images.slice(1))assert(image.caption.startsWith('관련 대상의 게임 도감 이미지 · '));
 }
});

test('알레프-원의 창조물 이미지는 실제 도감 이름으로 표시한다',()=>{
 const c=clusters.find(({c})=>c.id==='aleph-one').c;
 const images=clusterGameMedia(c,{index,records,imageManifest});
 assert(images.length>0);
 for(const image of images){
  assert(image.caption.startsWith('관련 대상의 게임 도감 이미지 · '));
  assert(image.caption.includes('허무의 신'));
  assert(!image.alt.startsWith('알레프-원'));
 }
 const unreferenced={id:c.id,title:c.title,nodes:c.nodes};
 assert.equal(clusterGameMedia(unreferenced,{index,records,imageManifest}).length,0);
});

test('관계도 유무와 함께 전체 원문 과정·순서·근거를 표시한다',()=>{
 const graph=json('source/public/reading-data/graph.json');
 const claims=new Map(graph.claims.map(c=>[c.id,c]));
 const evidence=new Map(graph.evidence.map(e=>[e.id,e]));
 const claim=id=>({...claims.get(id),evidence:claims.get(id).evidenceIds.map(id=>evidence.get(id))});
 let withRelations=0,steps=0;
 for(const cluster of graph.clusters.filter(c=>c.process?.length)){
  const m=resolveCluster(graph,cluster.id);
  const kit=createReadingKit({evidence:rs=>rs.map(e=>`<blockquote>${escapeHtml(e.quote)}</blockquote><a href="${escapeHtml(e.url)}">${escapeHtml(e.title)}</a>`).join('')});
  const render=createReadingSections({kit,model:()=>m,claim});
  const html=render({});
  assert.equal([...html.matchAll(/id="process"/g)].length,1,cluster.id+' lacks a stable process anchor');
  const models=[...html.matchAll(/<script[^>]*data-cva-model[^>]*>([\s\S]*?)<\/script>/g)].map(match=>JSON.parse(match[1]));
  const process=models.flatMap(d=>d.modules).filter(b=>b.id.startsWith('cva-process-'));
  assert.equal(process.length,1,cluster.id+' lacks its separate sourced process');
  assert.equal(process[0].variant,m.processKind==='cycle'?'feedback-ring':'quest-route');
  assert.deepEqual(process[0].props.items.map(i=>({title:i.title,body:i.body})),m.process.map(p=>({title:p.title,body:claim(p.claimId).text})));
  for(const p of m.process)for(const e of claim(p.claimId).evidence){assert(html.includes(escapeHtml(e.quote)));assert(html.includes(escapeHtml(e.url)));}
  if(m.topology)withRelations++;
  steps+=m.process.length;
 }
 assert(withRelations>=5);
 assert(steps>=16);
});
