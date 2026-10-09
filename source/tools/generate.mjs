import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import crypto from 'node:crypto';
import {readerFrame,readerDisclosure,rowAttributes} from '../src/lib/reading-kit/reader.mjs';

const source=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const site=path.resolve(source,'..');
const content=path.join(source,'src/content/docs');
const all=JSON.parse(await readFile(path.join(site,'content-manifest.json'),'utf8'));
const items=process.env.WUWA_SAMPLE_ONLY==='1'?all.filter(x=>['915000001','915000003','915000004'].includes(x.id)):all;
const base='/wuwa-quests';
const e=(s)=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/\r/g,'&#13;').replace(/\n/g,'&#10;');
const sourceDisclosure=(summary,body,className)=>readerDisclosure(summary,body,{className,attributes:{'data-pagefind-ignore':''}});
const display=(s)=>s.replace(/^기타임무_유형(\d+)$/,'기타임무 (유형 $1)').replace('버전미확인','버전 미확인').replace('버전혼합_','버전 혼합 ');
const readable=(s)=>s.replace(/<\/?(?:te|color|size|b|i|u|ano|s)(?:[=\s][^>]*)?>/g,'');
const extractionSequenceNote='원본 대화 순서가 없는 대화 항목을 참조합니다. 실제 항목만 수록했으며 누락 참조는 대화순서_참조누락.csv에 기록했습니다.';
const extractionReadingNote='이 장면에는 순서 정보가 확인되지 않은 대화 항목이 포함되어 있다.';
const versions=[...new Set(items.map(x=>x.version))].sort((a,b)=>/^\d\.\d$/.test(a)&&/^\d\.\d$/.test(b)?parseFloat(b)-parseFloat(a):/^\d\.\d$/.test(a)?-1:/^\d\.\d$/.test(b)?1:a.localeCompare(b,'ko'));
const groups=new Map();for(const x of items){const key=x.version+'|'+x.type;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(x);}for(const group of groups.values())group.sort((a,b)=>Number(a.id)-Number(b.id));
await mkdir(path.join(content,'quests'),{recursive:true});await mkdir(path.join(source,'public/originals'),{recursive:true});
const catalog=[];
for(const x of items){
 const original=path.join(site,'originals',x.id+'.txt');const bytes=await readFile(original);
 if(crypto.createHash('sha256').update(bytes).digest('hex')!==x.source_sha256)throw new Error('Source SHA mismatch: '+x.id);
 const text=bytes.toString('utf8').replace(/^\uFEFF/,'').replace(/\r\n?/g,'\n');
 const matches=[...text.matchAll(/^장면 \d+: [^\n]+/gm)];
 const intro=matches.length?text.slice(0,matches[0].index):text;
 const same=groups.get(x.version+'|'+x.type),pos=same.findIndex(y=>y.id===x.id);
 let md=`---\ntitle: ${JSON.stringify(x.title)}\ndescription: ${JSON.stringify(display(x.version)+' '+display(x.type)+' · '+x.title+' 한국어 대사와 선택지')}\n---\n\n`;
 md+=`<div class="quest-context" data-pagefind-ignore><a href="${base}/index.html?version=${encodeURIComponent(x.version)}">${e(display(x.version))}</a><span>›</span><a href="${base}/index.html?version=${encodeURIComponent(x.version)}&amp;type=${encodeURIComponent(x.type)}">${e(display(x.type))}</a></div>\n\n`;
 md+=`<p class="quest-id">퀘스트 <span data-pagefind-meta="퀘스트">${x.id}</span></p>\n\n`;
 md+=`<div class="quest-actions" data-pagefind-ignore><span>${matches.length}개 장면</span><a href="${base}/originals/${x.id}.txt" download>원본 TXT</a><button id="line-toggle" type="button" aria-pressed="false">대사 번호 보기</button></div>\n\n`;
 md+=sourceDisclosure('퀘스트 설명 · 수록 안내',`<pre>${e(intro)}</pre>`,'quest-info')+'\n\n';
 for(let i=0;i<matches.length;i++){
  const match=matches[i],segment=text.slice(match.index+match[0].length,i+1<matches.length?matches[i+1].index:text.length);
  md+=`<div id="scene-${i+1}" class="quest-section-anchor" aria-hidden="true"></div>\n\n## ${e(match[0])}\n\n`;
  const metadata=[];let sceneBody='',extractionNoteShown=false;
  for(const raw of segment.split('\n')){
   if(!raw.trim())continue;
   if(raw.trim()===extractionSequenceNote){
    if(!extractionNoteShown)sceneBody+=`<p class="quest-reading-note" role="note" data-pagefind-ignore>${e(extractionReadingNote)}</p>`;
    extractionNoteShown=true;continue;
   }
   if(/^(순서 근거:|대화 ID:|대화 묶음)/.test(raw.trim())||/^─+$/.test(raw.trim())){metadata.push(raw);continue;}
   const line=readable(raw).trim();const cls=line.startsWith('선택 ')?'quest-choice':line.startsWith('→')?'quest-branch':'quest-utterance';
   const m=line.match(/^(\[대화ID [^\]]+\])\s*([^:：]+):\s*(.*)$/);
   const body=m?`<span class="line-id">${e(m[1])} </span><strong class="quest-speaker">${e(m[2])}</strong><span class="quest-speech rw-source-body"><span class="speaker-colon">: </span>${e(m[3])}</span>`:e(line);
   const attrs=rowAttributes(cls==='quest-choice'?'choice':cls==='quest-branch'?'branch':'dialogue');
   attrs.class=`quest-source-line ${cls} ${attrs.class}`;
   sceneBody+=`<p ${Object.entries(attrs).map(([key,value])=>`${key}="${e(value)}"`).join(' ')}>${body}</p>`;
  }
  if(metadata.length)sceneBody+=sourceDisclosure('장면 자료 정보',`<pre>${e(metadata.join('\n'))}</pre>`,'quest-scene-info');
  md+=readerFrame(sceneBody,{variant:'transcript',className:'quest-reader'})+'\n\n';
 }
 md+='<nav class="quest-pager" aria-label="같은 분류의 퀘스트" data-pagefind-ignore>';
 for(const [other,label] of [[same[pos-1],'← 이전 퀘스트'],[same[pos+1],'다음 퀘스트 →']])md+=other?`<a href="${base}/quests/${other.id}.html"><small>${label}</small><strong>${e(other.title)}</strong><span>${other.id}</span></a>`:'<span></span>';
 md+='</nav>\n';
 await writeFile(path.join(content,'quests',x.id+'.md'),md);await copyFile(original,path.join(source,'public/originals',x.id+'.txt'));
 catalog.push({...x,scenes:matches.length});
}
const sidebar=[{label:'퀘스트 목록',link:'/index.html'},{label:'자료 안내',link:'/about.html'}];
for(const version of versions){const types=[...new Set(items.filter(x=>x.version===version).map(x=>x.type))].sort((a,b)=>a==='메인임무'?-1:b==='메인임무'?1:a.localeCompare(b,'ko'));
 sidebar.push({label:display(version),collapsed:true,items:types.map(type=>({label:display(type),collapsed:true,items:groups.get(version+'|'+type).map(x=>({label:x.title,link:'/quests/'+x.id+'.html',badge:{text:x.id,variant:'note'}}))}))});
}
catalog.sort((a,b)=>versions.indexOf(a.version)-versions.indexOf(b.version)||Number(b.type==='메인임무')-Number(a.type==='메인임무')||a.type.localeCompare(b.type,'ko')||Number(a.id)-Number(b.id));
await writeFile(path.join(source,'generated-sidebar.json'),JSON.stringify(sidebar));await writeFile(path.join(source,'generated-catalog.json'),JSON.stringify(catalog));
await writeFile(path.join(content,'index.mdx'),`---\ntitle: 퀘스트 목록\npagefind: false\ntableOfContents: false\n---\n\nimport QuestCatalog from '../../components/QuestCatalog.astro';\n\n<QuestCatalog />\n`);
await writeFile(path.join(content,'about.md'),`---\ntitle: 자료 안내\n---\n\n## 수록 범위\n\n한국어 제목과 대사가 있는 퀘스트 ${all.length}개를 수록했습니다. 원본 데이터 ${1901}개 중 내부 테스트와 식별이 불분명한 항목 등을 제외했습니다. 원본 TXT 다운로드에는 게임 내부 태그와 변수, 선택지 및 분기 정보가 보존되어 있습니다.\n\n## 버전과 임무 분류\n\n버전은 대화 식별자 등 추출 자료를 근거로 분류했습니다. 최초 출시 버전을 보장하지 않습니다. 확인할 수 없는 경우 ‘버전 미확인’ 표시를 유지합니다. 원본의 ‘조수 임무’는 ‘메인임무’로 표시합니다. 이름을 확인하지 못한 임무 종류는 원본 유형 번호를 함께 표시합니다.\n\n## 장면 순서\n\n장면은 추출 자료의 순서입니다. 같은 분류의 이전·다음 퀘스트는 ID 순서이며 이야기의 시간 순서를 뜻하지 않습니다. 여러 퀘스트에 같은 제목이 있을 수 있으므로 ID를 함께 표시합니다.\n\n## 출처와 권리\n\n이 사이트는 비공식 자료집입니다. 대사와 게임 콘텐츠의 권리는 KURO GAMES 등 해당 권리자에게 있습니다. 공개 접근 가능 여부는 재게시 이용허락을 의미하지 않습니다. 원문 전체의 재게시를 명시적으로 허용하는 이용허락은 확인되지 않았으며 게임 콘텐츠에 오픈 라이선스를 부여하지 않았습니다.\n\n[KURO GAMES 팬 콘텐츠 가이드라인](https://wutheringwaves.kurogames.com/p/en/produce.html)\n\n## 재사용한 문서 도구\n\n문서 레이아웃·목차·검색은 [Starlight](https://starlight.astro.build/)와 [Pagefind](https://pagefind.app/)를 사용합니다. 도구 코드는 해당 오픈소스 라이선스를 따르며 게임 대사의 권리와는 별개입니다.\n`);
await writeFile(path.join(source,'public/.nojekyll'),'');await writeFile(path.join(source,'public/robots.txt'),'User-agent: *\nAllow: /\n');
console.log(JSON.stringify({generated:items.length,sourceSha256:'PASS'}));
