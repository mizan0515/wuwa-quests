import test from 'node:test';
import assert from 'node:assert/strict';
import {createDirectoryRenderer} from './directory-discovery.mjs';

const profile='/wuwa-quests/people/1311.html',sentinel='/wuwa-quests/sentinels/fox.html';
const renderer=()=>createDirectoryRenderer({
  kit:{section:()=>'',directory:items=>JSON.stringify(items)},H:String,proofFor:()=>({}),
  entityLinks:new Map([['여우의 별자리','/sentinels/fox.html']]),
  entityNamesByUrl:new Map([[profile,'여우의 별자리'],[sentinel,'여우의 별자리']]),scriptVersion:'fixture',
});
const subject={id:'jitian',category:'factions',name:'제천감',kind:'조직',summary:'원문 요약',refs:[],relatedUrls:[profile]};

test('authored profile URL survives a different automatic destination for the same name',()=>{
  const html=renderer().dossier(subject);
  assert.ok(html.includes(profile));
  assert.ok(html.includes('여우의 별자리'));
  assert.equal((html.match(/people\/1311\.html/g)||[]).length,1);
});
test('an unlabelled authored related URL stops generation rather than dropping the link',()=>{
  assert.throws(()=>renderer().dossier({...subject,relatedUrls:['/wuwa-quests/people/unknown.html']}),/Unresolved authored related URL/);
});
