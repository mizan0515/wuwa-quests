import test from 'node:test';
import assert from 'node:assert/strict';
import {loadHandbook,verifyHandbook,handbookReadingState} from './handbook-originals.mjs';
import {sourceRelations,stripOriginalAssetMarkup} from '../public/lore/source-relations.js';
const model=await loadHandbook();
test('public handbook projection and all sidecar/index relationships preserve originals',()=>assert.ok(verifyHandbook(model).readingEntries>0));
test('normal test wording is readable; isolated test/placeholder bodies remain accessible',()=>{
 for(const id of ['튜토리얼_페이지:guidetutorialpage:50002','튜토리얼_페이지:guidetutorialpage:3601802','게임_도움말:helptext:91'])assert.equal(handbookReadingState(model.records[id]),'READABLE');
 assert.equal(handbookReadingState(model.records['게임_도움말:helptext:1']),'TEST_CONTENT_ONLY');
 assert.equal(handbookReadingState(model.records['게임_도움말:helptext:16']),'PLACEHOLDER_MARKER');
});
test('intrinsic texture markup is hidden in display and its exact original remains preserved',()=>{
 const value=model.records['게임_도움말:helptext:503'].values.find(v=>v.field==='content');
 assert.match(value.raw,/<texture=\/Game\//);assert.doesNotMatch(value.text,/<texture|\/Game\//);
 const display=stripOriginalAssetMarkup(value.raw);assert.doesNotMatch(display,/<texture|\/Game\//);
 assert.ok(display.includes('달그림자를 거스르는 고리'));
});
test('tutorial reader follows source array IDs in source order with links to every page',()=>{
 const source=model.index.entries.find(e=>e.id==='튜토리얼_페이지:guidetutorialpage:1');
 const rel=source.source_relations.find(r=>r.source.entry_id==='30001');
 assert.deepEqual(rel.source.page_ids,[1,3000102]);
 const entries=new Map([...model.index.entries,...model.index.diagnostic_entries].map(e=>[e.id,e]));
 const markup=sourceRelations({source_relations:[rel]},{entry:id=>entries.get(id),url:e=>'/wuwa-quests'+e.page,escape:s=>String(s)});
 assert.deepEqual([...markup.matchAll(/guidetutorialpage:(\d+)/g)].map(m=>Number(m[1])),[1,3000102]);
 assert.match(markup,/data-reading-link/);assert.match(markup,/페이지 배열 필드 3/);assert.doesNotMatch(markup,/guidetutorialpage:1000001/);
});
test('meaningful public mutations fail the same full projection verifier',()=>{
 const mutations=[
  m=>m.index.entries[0].page='/wrong.html',
  m=>m.index.aliases.fake='fake',
  m=>m.index.entries.find(e=>e.id==='게임_도움말:helptext:91').reading_state='TEST_CONTENT_ONLY',
  m=>m.records['게임_도움말:helptext:91'].reading_state='TEST_CONTENT_ONLY',
  m=>m.index.diagnostic_entries.pop(),
  m=>m.relations.relations.find(r=>r.kind==='tutorial_pages'&&r.source.entry_id==='30001').pages.reverse(),
  m=>m.relations.relations.find(r=>r.kind==='tutorial_pages'&&r.source.entry_id==='30001').pages[0].id='튜토리얼_페이지:guidetutorialpage:1000001',
  m=>m.relations.relations.find(r=>r.kind==='cooking_formula').food_id='아이템_배경:iteminfo:9999999',
  m=>m.relations.relations.find(r=>r.kind==='handbook_classification').classification_id='도감_분류:monsterhandbooktype:9999',
  m=>m.relations.relations.find(r=>r.kind==='item_handbook').source.title.field_index=1,
  m=>m.relations.relations.find(r=>r.kind==='weapon_handbook').weapon_id='fake',
  m=>m.index.entries.find(e=>e.source_relations?.length).source_relations=[],
  m=>m.provenance.installed_client_match='VERIFIED',
 ];
 for(const mutate of mutations){const copy=structuredClone(model);mutate(copy);assert.throws(()=>verifyHandbook(copy));}
});
