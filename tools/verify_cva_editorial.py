"""Read-only whole-registry CVA/source acceptance checks for Wuwa.

This verifies actual built module payloads and executes the shipped dynamic
library renderer against every preserved reading entry. It is not browser QA.
"""
import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

sys.dont_write_bytecode = True
SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE/'source/tools'))
from verify_original_rendering import load_curated_sources, visible_text

BASE = '/wuwa-quests'
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
        'meta', 'param', 'source', 'track', 'wbr'}
EXCLUDED = {'name', 'title', 'type', 'birthday', 'sex', 'country', 'influence'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dynamic_source_route(actual, expected, return_to):
    """A return parameter may be added; the original path/ID/field stays exact."""
    got, original = urlsplit(actual), urlsplit(expected)
    require((got.scheme, got.netloc, got.path, got.query) ==
            (original.scheme, original.netloc, original.path, original.query),
            'dynamic source document path changed')
    got_path, _, got_query = got.fragment.partition('?')
    original_path, _, original_query = original.fragment.partition('?')
    require(unquote(got_path) == unquote(original_path), 'dynamic source ID/hash route changed')
    params, originals = parse_qsl(got_query, keep_blank_values=True), parse_qsl(original_query, keep_blank_values=True)
    require([p for p in params if p[0] != 'from'] == originals, 'dynamic original field/query params changed')
    require([v for k, v in params if k == 'from'] == [return_to], 'dynamic original list return route changed')


def dynamic_return_link(markup, expected):
    page = parse(markup)
    links = [n for n in page.nodes if n['tag'] == 'a' and ''.join(n['text']) == '← 원문 보관함']
    require(len(links) == 1 and links[0]['attrs'].get('href') == expected,
            'actual source-to-library link lost the original list route')
    return page


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.nodes, self.models, self.text = [], [], [], []
        self.active_model = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        parent = self.stack[-1] if self.stack else None
        node = {'tag': tag, 'attrs': a, 'parent': parent, 'text': []}
        self.nodes.append(node)
        if tag == 'script' and 'data-cva-model' in a:
            self.active_model = node
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i]['tag'] == tag:
                removed = self.stack[i:]
                del self.stack[i:]
                if self.active_model in removed:
                    self.models.append(json.loads(''.join(self.active_model['text'])))
                    self.active_model = None
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_data(self, value):
        if self.active_model is not None:
            self.active_model['text'].append(value)
        if not any(n['tag'] in {'script', 'style'} for n in self.stack):
            self.text.append(value)
            for node in self.stack:
                node['text'].append(value)

    @property
    def modules(self):
        return [m for document in self.models for m in document['modules']]

    def has_class(self, name):
        return [n for n in self.nodes if name in n['attrs'].get('class', '').split()]

    def within(self, node, attribute, value=None):
        while node is not None:
            if attribute in node['attrs'] and (value is None or node['attrs'][attribute] == value):
                return True
            node = node['parent']
        return False


def parse(value):
    page = Page()
    page.feed(value)
    return page


def contains(page, value, description):
    require(visible_text(value) in ''.join(page.text), 'visible text missing: '+description)


def module_texts(page):
    return [str(value) for m in page.modules for value in (
        [v for v in m['props'].values() if isinstance(v, str)] +
        [v for item in m['props'].get('items', []) for v in item.values() if isinstance(v, str)])]


def require_module(page, value, description):
    require(value in module_texts(page), 'actual CVA payload missing: '+description)


def require_visible_module(page, value, description, title=False):
    require_module(page, value, description)
    classes = {'cva-item-title', 'sc-item-title', 'cva-title'} if title else {'cva-body', 'cva-lead', 'cva-item-body', 'sc-item-body'}
    require(any(classes & set(n['attrs'].get('class', '').split())
                and ''.join(n['text']) == visible_text(value) for n in page.nodes),
            'actual visible CVA text missing or changed: '+description)


def link_in_module(page, target, label):
    candidates = [n for n in page.nodes if n['tag'] == 'a' and n['attrs'].get('href') == target]
    require(any(label in ''.join(n['text']) and page.within(n, 'data-cva') for n in candidates),
            'CVA body link missing: '+target+' / '+label)


def check_reader_fields(page, expected_ids, scope):
    fields = page.has_class('lore-field')
    ids = set()
    for field in fields:
        ids.add(field['attrs'].get('id'))
        for n in page.nodes:
            if n['attrs'].get('id', '').startswith('field-') and descendant(n, field):
                ids.add(n['attrs']['id'])
        readers = [n for n in page.nodes if n['attrs'].get('data-reading-template') == 'reader' and descendant(n, field)]
        require(readers and all({'rw-reader', 'not-content', 'cva-page'} <= set(n['attrs'].get('class', '').split())
                                and n['attrs'].get('data-cva-profile') == 'forma' and 'data-cva' in n['attrs']
                                for n in readers), 'original field reader scope missing: '+scope)
        disclosures = [n for n in page.nodes if n['tag'] == 'details' and descendant(n, field)]
        require(disclosures and all(n['attrs'].get('data-reading-template') == 'disclosure' for n in disclosures),
                'original field shared disclosure missing: '+scope)
    require(set(expected_ids) <= ids, 'original/alias field anchor missing: '+scope)


def descendant(node, parent):
    while node is not None:
        if node is parent:
            return True
        node = node['parent']
    return False


def check_field_value(page, field, value, scope):
    raw_nodes = [n for n in page.nodes if n['tag'] == 'pre' and descendant(n, field)]
    require(len(raw_nodes) == 1 and ''.join(raw_nodes[0]['text']) == value['raw'],
            'dynamic whole raw original changed: '+scope)
    visible = [n for n in page.has_class('lore-source-text') if descendant(n, field)]
    if value['status'] == 'OK':
        require(len(visible) == 1 and ''.join(visible[0]['text']) == html.unescape(visible_text(value['raw'])),
                'dynamic visible original changed: '+scope)
    else:
        require(not visible, 'dynamic non-OK field shows text')
    dd = [n for n in page.nodes if n['tag'] == 'dd' and descendant(n, field)]
    require(value['status'] in [''.join(n['text']) for n in dd], 'dynamic original status lost')
    require(any(n['tag'] == 'h2' and 'cva-title' in n['attrs'].get('class', '').split()
                and descendant(n, field) for n in page.nodes), 'dynamic actual CVA field heading missing')


FIXTURE_HARNESS = r"""
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context=vm.createContext({});context.window=context;context.CVA_LOCAL_MEDIA=[];context.CVA_LOCAL_SCENE_ITEMS=Array.from({length:3},(_,i)=>({id:'empty-source-'+i,title:'',body:'',label:'',image:''}));
for(const name of ['components.js','scene-catalog.js','modules.js'])vm.runInContext(fs.readFileSync(path.join(process.argv[1],name),'utf8'),context);
const values=new Set(),keys=new Set(['eyebrow','title','body','caption','cite','actionLabel','relationLabel','label','value']);
function gather(value){if(Array.isArray(value))value.forEach(gather);else if(value&&typeof value==='object')for(const [key,item] of Object.entries(value)){
 if(typeof item==='string'&&keys.has(key)&&item)values.add(item);else if(item&&typeof item==='object')gather(item);
}}
context.CVA_MODULES.definitions.filter(d=>d.type!=='forma-pattern').forEach(d=>gather(d.defaultProps));
context.CVA_SCENES.entries.forEach(d=>gather(d.props));
process.stdout.write(JSON.stringify([...values]));
"""


def canonical_fixtures(site):
    result = subprocess.run(['node', '-e', FIXTURE_HARNESS, str(site/'source/src/lib/reading-kit/cva/vendor')],
                            capture_output=True, text=True, encoding='utf-8', check=False)
    require(result.returncode == 0, 'canonical CVA fixture inspection failed: '+result.stderr[-1000:])
    values = json.loads(result.stdout)
    require(values and all(isinstance(v, str) and v for v in values), 'canonical CVA fixture set is empty')
    # Short generic words such as "용도" also label genuine source fields.
    # Compare every default exactly in actual module payloads; use distinctive
    # full phrases to inspect visible prose without treating those labels as
    # authored sample content.
    phrases = [v for v in values if len(v) >= 8 or re.fullmatch(r'[A-Z][A-Z /]{3,}', v)]
    return {'exact': set(values), 'pattern': re.compile('|'.join(re.escape(v) for v in sorted(phrases, key=len, reverse=True)))}


def source_literals(site, index, records, book, atlas, curated):
    """Exact originals/proven quotes with their real source URL, for collisions."""
    entries = {e['id']: e for e in index['entries']}
    literals = {}
    def add(value, url):
        if value:
            literals.setdefault(value, set()).add(url)
    for id, row in records.items():
        source = BASE+'/sources/'+curated[id]+'.html' if id in curated else BASE+entries[id]['page']
        for v in row['values']:
            if v['status'] == 'OK':
                target = source+'#field-'+v['field'] if '#' not in source else source
                for value in (v['raw'], v['text'], visible_text(v['raw']), html.unescape(visible_text(v['raw']))):
                    add(value, target)
    def refs(value):
        if isinstance(value, list):
            return [r for v in value for r in refs(v)]
        if not isinstance(value, dict):
            return []
        if value.get('source_text_sha256') and value.get('id') or value.get('quest_id') and value.get('quote'):
            return [value]
        return [r for v in value.values() for r in refs(v)]
    quest_cache = {}
    for r in refs([book, atlas]):
        if 'quest_id' in r:
            id = str(r['quest_id'])
            if id not in quest_cache:
                quest_cache[id] = (site/'originals'/(id+'.txt')).read_bytes()
            raw = quest_cache[id]
            require(hashlib.sha256(raw).hexdigest() == r['source_sha256'], 'literal exception quest SHA changed')
            text = raw.decode('utf-8')
            starts = list(re.finditer(r'^장면 (\d+):', text, re.M))
            pos = next(i for i, m in enumerate(starts) if int(m[1]) == r['scene'])
            scene = text[starts[pos].start():starts[pos+1].start() if pos+1 < len(starts) else len(text)]
            require(r['quote'] in scene, 'literal exception quotation differs from its original scene')
            add(r['quote'], BASE+'/quests/'+id+'.html#scene-'+str(r['scene']))
        else:
            id = index.get('aliases', {}).get(r['id'], r['id'])
            v = next(v for v in records[id]['values'] if v['field'] == r['field'])
            require(hashlib.sha256(v['raw'].encode()).hexdigest() == r['source_text_sha256'], 'literal exception setting SHA changed')
            quote = r.get('quote') or r.get('excerpt', '')
            # Overview abbreviations with an editorial ellipsis are not an
            # exact original and cannot grant a fixture exception.
            if quote and quote in v['text']:
                add(quote, BASE+'/sources/'+curated[id]+'.html#field-'+r['field'] if id in curated else BASE+entries[id]['page'])
    return literals


def reject_fixtures(page, fixtures, literals, current_url='', stats=None):
    pattern = fixtures['pattern'] if isinstance(fixtures, dict) else fixtures
    hrefs = {n['attrs'].get('href', '').split('#')[0].split('?')[0] for n in page.nodes if n['tag'] == 'a'}
    def original(text):
        return any(url.split('#')[0].split('?')[0] in hrefs or
                   current_url and url.split('#')[0].split('?')[0] == current_url for url in literals.get(text, set()))
    if isinstance(fixtures, dict):
        for value in module_texts(page):
            if value in fixtures['exact']:
                require(original(value), 'canonical CVA default field leaked into reader model: '+value[:160])
    author_classes = {'cva-empty', 'sc-empty', 'sc-image-empty', 'sc-fallback'}
    for node in page.nodes:
        classes = set(node['attrs'].get('class', '').split())
        if not author_classes & classes and node['tag'] not in {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'cite', 'span', 'summary', 'dd', 'pre', 'blockquote'}:
            continue
        # Check leaf prose/heading containers, not a whole-page ancestor whose
        # text also includes an independently certified quotation elsewhere.
        if node['tag'] == 'div' and not classes & {'cva-body', 'cva-item-body', 'sc-item-body', 'lore-source-text'}:
            continue
        text = ''.join(node['text'])
        if not author_classes & classes and not pattern.search(text):
            continue
        require(original(text), 'CVA default fixture/authoring hint leaked into reader output: '+text[:160])
        if stats is not None:
            stats['exactOriginalFixtureCollisions'] += 1


NODE_HARNESS = r"""
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const site=process.argv[1],components=process.argv[2],setting=path.join(site,'settings');
const read=name=>JSON.parse(fs.readFileSync(path.join(setting,name),'utf8'));
const index=read('index.json'),book=read('editorial.json');
const records={};for(const file of fs.readdirSync(setting).filter(n=>/^records-.+\.json$/.test(n)))Object.assign(records,read(file));
const curated=process.argv[3]?JSON.parse(fs.readFileSync(process.argv[3],'utf8')):{sources:index.curated_sources};
const root={dataset:{base:'/wuwa-quests'},innerHTML:'',focus(){}},heading={textContent:''},focused=[];
const context=vm.createContext({console,URLSearchParams,document:{getElementById:id=>id==='lore-reader'?root:id==='_top'?heading:id.startsWith('field-')?{scrollIntoView:()=>focused.push(id)}:null},fetch:async url=>({ok:true,json:async()=>read(url.slice(url.lastIndexOf('/')+1))}),location:{pathname:'/wuwa-quests/library.html',search:'',hash:'#/library'}});
context.window=context;vm.runInContext(fs.readFileSync(components,'utf8'),context);
let source=fs.readFileSync(path.join(site,'source/public/lore/library.js'),'utf8');
const bootstrap="window.addEventListener('hashchange',render);render();";
if(source.split(bootstrap).length!==2)throw Error('Dynamic library bootstrap changed; QA must inspect the actual entry point');
source=source.replace(bootstrap,"globalThis.__libraryQA={fields,row,current,render,libraryReturn,setData:(i,b,c)=>{index=i;book=b;curated=c;}};");
vm.runInContext(source,context);context.__libraryQA.setData(index,book,curated);
for(const e of index.entries){
 const row=records[index.aliases[e.id]||e.id];if(!row)throw Error('Reading record missing: '+e.id);
 process.stdout.write(JSON.stringify({id:e.id,fields:context.__libraryQA.fields(row),row:context.__libraryQA.row(e)})+'\n');
}
// Real branch logic: retained query parameters, named field focus and body-match
// snippets. These are chosen from the current preserved entries, not examples.
// Use a real uncurated original, its real fields and its real shared-term links.
(async()=>{
const chosen=index.entries.find(e=>!curated.sources[e.id]&&records[e.id].values.some(v=>v.status==='OK'&&v.text.length>180));
if(!chosen)throw Error('No actual dynamic original available for route canary');
const body=records[chosen.id].values.filter(v=>v.status==='OK').map(v=>v.text).join('\n');
const query=body.slice(55,66),field=records[chosen.id].values.find(v=>v.status==='OK'&&!['name','title','type','birthday','sex','country','influence'].includes(v.field)).field;
const listParams=new URLSearchParams({q:query,category:chosen.category,page:'3',body:'1',technical:'1',group:chosen.group});
if(chosen.role_id)listParams.set('role',String(chosen.role_id));if(chosen.term_ids[0])listParams.set('term',chosen.term_ids[0]);
const returnTo='#/library?'+listParams.toString();
context.location.hash='#/source/'+encodeURIComponent(chosen.id)+'?field='+encodeURIComponent(field)+'&from='+encodeURIComponent(returnTo);
const route={parts:[...context.__libraryQA.current().parts],params:[...context.__libraryQA.current().params]};
const renderedRow=context.__libraryQA.row(chosen,query,body);
// Adding an actual named field to a source route must not overwrite that field.
const fieldRow=context.__libraryQA.row({...chosen,page:chosen.page+(chosen.page.includes('?')?'&':'?')+'field='+encodeURIComponent(field)});
await context.__libraryQA.render();
const rendered=root.innerHTML,adjacent=index.entries.filter(x=>x.id!==chosen.id&&x.group!=='technical'&&x.term_ids.filter(t=>chosen.term_ids.includes(t)).length>=2).slice(0,6).filter(e=>!curated.sources[e.id]);
process.stdout.write(JSON.stringify({canary:true,id:chosen.id,body,query,field,returnTo,row:renderedRow,fieldRow,rendered,focused:[...focused],adjacent:adjacent.map(e=>({id:e.id,page:e.page})),route})+'\n');
for(const invalid of ['https://example.invalid/library','//example.invalid/library','#/source/'+encodeURIComponent(chosen.id),'#/library-extra','#/library?q=x#external','']){
 context.location.hash='#/source/'+encodeURIComponent(chosen.id)+'?field='+encodeURIComponent(field)+'&from='+encodeURIComponent(invalid);
 await context.__libraryQA.render();
 process.stdout.write(JSON.stringify({returnCanary:true,id:chosen.id,invalid,returnValue:context.__libraryQA.libraryReturn(invalid),row:context.__libraryQA.row(chosen),rendered:root.innerHTML})+'\n');
}
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


def dynamic_check(site, index, records, curated, components, stats, fixture_pattern, literals, curated_artifact=None):
    process = subprocess.Popen(['node', '-e', NODE_HARNESS, str(site), str(components), str(curated_artifact) if curated_artifact else ''],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
    entries = {e['id']: e for e in index['entries']}
    seen = set()
    try:
        for line in process.stdout:
            output = json.loads(line)
            e = entries[output['id']]
            page = parse(output['row'])
            reject_fixtures(page, fixture_pattern, literals, stats=stats)
            require(page.has_class('cva-panel'), 'dynamic row actual CVA panel missing: '+e['id'])
            contains(page, e['title'], e['id']+' title')
            source_path = BASE+'/sources/'+curated[e['id']]+'.html' if e['id'] in curated else BASE+e['page']
            row_links = [n['attrs'].get('href') for n in page.nodes if n['tag'] == 'a']
            require(row_links and urlsplit(row_links[0]).path == urlsplit(source_path).path,
                    'dynamic canonical source route changed: '+e['id'])
            if e['id'] not in curated:
                dynamic_source_route(row_links[0], source_path,
                                     output['returnTo'] if output.get('canary') else '#/library')
            if output.get('returnCanary'):
                require(output['returnValue'] == '#/library', 'external/non-library return route accepted')
                dynamic_return_link(output['rendered'], '#/library')
                stats['dynamicUnsafeReturnCanaries'] += 1
                continue
            if output.get('canary'):
                require(output['route']['parts'] == ['source', e['id']], 'dynamic source route decode changed')
                require(dict(output['route']['params']) == {'field': output['field'], 'from': output['returnTo']}, 'dynamic field/return params lost')
                field_links = [n['attrs'].get('href') for n in parse(output['fieldRow']).nodes if n['tag'] == 'a']
                dynamic_source_route(field_links[0], source_path+'?field='+output['field'], output['returnTo'])
                rendered = dynamic_return_link(output['rendered'], output['returnTo'])
                require('field-'+output['field'] in output['focused'], 'actual dynamic named field focus lost')
                for adjacent in output['adjacent']:
                    expected_path = BASE+adjacent['page']
                    links = [n['attrs'].get('href') for n in rendered.nodes if n['tag'] == 'a'
                             and 'lore-record' in n['attrs'].get('class', '').split()
                             and unquote(urlsplit(n['attrs'].get('href', '')).fragment.partition('?')[0]) ==
                             unquote(urlsplit(expected_path).fragment.partition('?')[0])]
                    require(len(links) == 1, 'actual adjacent source link absent: '+adjacent['id'])
                    dynamic_source_route(links[0], expected_path, output['returnTo'])
                    stats['dynamicAdjacentReturnCanaries'] += 1
                require(output['adjacent'], 'no actual adjacent dynamic routes exercised')
                body, q = output['body'], output['query']
                at = body.lower().find(q.lower())
                start = max(0, at-35)
                expected = ('…' if start else '') + re.sub(r'\s+', ' ', body[start:at+100]) + ('…' if at+100 < len(body) else '')
                contains(page, expected, 'dynamic body-match snippet')
                stats['dynamicRouteSnippetCanaries'] += 1
                continue
            require(e['id'] not in seen, 'duplicate dynamic reading entry')
            seen.add(e['id'])
            contains(page, e['excerpt'], e['id']+' exact retained snippet')
            field_page = parse(output['fields'])
            # Each dynamic source route is fixed by its actual preserved ID.
            reject_fixtures(field_page, fixture_pattern, literals, source_path.split('#')[0].split('?')[0], stats)
            row = records[index.get('aliases', {}).get(e['id'], e['id'])]
            values = [v for v in row['values'] if v['field'] not in EXCLUDED]
            check_reader_fields(field_page, ['field-'+v['field'] for v in values], e['id'])
            fields = field_page.has_class('lore-field')
            for value in values:
                anchor = 'field-'+value['field']
                field = next((f for f in fields if f['attrs'].get('id') == anchor or any(
                    n['attrs'].get('id') == anchor and descendant(n, f) for n in field_page.nodes)), None)
                require(field is not None, 'dynamic alias field missing: '+e['id']+' / '+anchor)
                check_field_value(field_page, field, value, e['id']+' / '+anchor)
                stats['dynamicFields'] += 1
            stats['dynamicReadingEntries'] += 1
        stderr = process.stderr.read()
        require(process.wait() == 0, 'actual dynamic renderer failed: '+stderr[-2500:])
        require(seen == set(entries), 'dynamic renderer did not cover all preserved reading entries')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def built_check(site, dist, index, records, book, atlas, curated, stats, fixture_pattern, literals):
    cache = {}
    def page(relative):
        if relative not in cache:
            path = dist/relative
            require(path.is_file(), 'built page missing: '+relative)
            cache[relative] = parse(path.read_text(encoding='utf-8'))
            reject_fixtures(cache[relative], fixture_pattern, literals, BASE+'/'+relative, stats)
        return cache[relative]
    groups = ['regions', 'factions', 'cosmology', 'people', 'sentinels']
    world = page('world.html')
    for group in groups:
        directory = page(group+'.html')
        for cluster in atlas[group]:
            target = BASE+'/'+group+'/'+cluster['id']+'.html'
            for entry_page in (world, directory):
                # People keeps its existing keyboard/filterable directory.
                link_in_module(entry_page, target, cluster['title'])
                contains(entry_page, cluster['summary'], cluster['id']+' directory summary')
            p = page(group+'/'+cluster['id']+'.html')
            require(p.models, 'cluster actual CVA modules missing: '+cluster['id'])
            contains(p, cluster['summary'], cluster['id']+' overview')
            contains(p, cluster['question'], cluster['id']+' question')
            stats['atlasClusters'] += 1
    graph = json.loads((dist/'reading-data/graph.json').read_text(encoding='utf-8'))
    claims = {c['id']: c for c in graph['claims']}
    proofs = {e['id']: e for e in graph['evidence']}
    seen_claims = set()
    for cluster in graph['clusters']:
        p = page(cluster['url'].removeprefix(BASE+'/'))
        claim_ids = [cid for section in cluster['sections'] for cid in section['claimIds']]
        claim_ids += [v['claimId'] for key in ('comparisons', 'process') for v in cluster[key]]
        claim_ids += [edge['claimId'] for view in [cluster.get('topology'), *cluster['views']] if view for edge in view['edges']]
        claim_ids += [r['reasonClaimId'] for r in graph['relations'] if r['clusterId'] == cluster['id']]
        claim_ids += [e['claimId'] for e in graph['events'] if e['clusterId'] == cluster['id']]
        for claim_id in set(claim_ids):
            seen_claims.add(claim_id)
            c = claims[claim_id]
            # Redundant dialogue is folded into the same quoted proof, so
            # require exact claim text OR all its actual quoted evidence.
            rendered = ''.join(p.text)
            require(visible_text(c['text']) in rendered or all(visible_text(proofs[e]['quote']) in rendered for e in c['evidenceIds']),
                    'cluster claim and its original proof absent: '+cluster['id']+' / '+claim_id)
            for eid in c['evidenceIds']:
                proof = proofs[eid]
                require(any(n['tag'] == 'a' and n['attrs'].get('href') == proof['url'] for n in p.nodes),
                        'cluster original proof link absent: '+cluster['id']+' / '+eid)
            stats['clusterClaimChecks'] += 1
    require(seen_claims == set(claims), 'normalized source-backed claims omitted from built coverage')
    stats['uniqueSourceBackedClaims'] = len(seen_claims)
    for chapter in book['chapters']:
        p = page('world/'+chapter['id']+'.html')
        require(any(m['type'] == 'scene-composition' and m['variant'] == 'quest-route' for m in p.modules),
                'editorial reading route absent: '+chapter['id'])
        contains(p, '함께 읽는 순서', chapter['id']+' route label')
        for step in chapter['flow']:
            require_visible_module(p, step['title'], chapter['id']+' step title', title=True)
            require_visible_module(p, step['detail'], chapter['id']+' step body')
        paragraphs = [q for section in chapter['sections'] for q in section['paragraphs']]
        if chapter.get('caution'):
            paragraphs.append(chapter['caution'])
        for q in paragraphs:
            require_visible_module(p, q['text'], chapter['id']+' editorial body')
            for ref in q['refs']:
                id = index.get('aliases', {}).get(ref['id'], ref['id'])
                value = next(v for v in records[id]['values'] if v['field'] == ref['field'])
                require(hashlib.sha256(value['raw'].encode()).hexdigest() == ref['source_text_sha256'], 'editorial source SHA changed')
                quote = ref.get('quote') or (ref.get('excerpt') if ref.get('excerpt') and ref['excerpt'] in value['text'] else value['text'])
                contains(p, quote, chapter['id']+' actual original quotation')
                target = BASE+'/sources/'+curated[id]+'.html#field-'+ref['field']
                require(any(n['tag'] == 'a' and n['attrs'].get('href') == target for n in p.nodes), 'editorial exact original field link absent')
        for q in chapter.get('quest_links', []):
            link_in_module(p, BASE+'/quests/'+q['id']+'.html', q['title'])
            require_visible_module(p, ' · '.join(q['terms'])+'\n'+q['snippet'], 'quest linked snippet')
        stats['editorialChapters'] += 1
    for person in index['characters']:
        p = page('people/'+str(person['id'])+'.html')
        profile = next((e for e in index['entries'] if str(e.get('role_id')) == str(person['id']) and e['chunk'] == 'profile'), None)
        if profile:
            row = records[profile['id']]
            check_reader_fields(p, ['field-'+v['field'] for v in row['values'] if v['field'] in {'info', 'talent_name', 'talent_document', 'talent_certification'}], person['name'])
        for source in [e for e in index['entries'] if str(e.get('role_id')) == str(person['id']) and e['chunk'] in {'profile', 'stories', 'goods'}]:
            target = BASE+'/sources/'+curated[source['id']]+'.html' if source['id'] in curated else BASE+source['page']
            link_in_module(p, target, source['title'])
            if source['chunk'] != 'profile':
                row = records[source['id']]
                prefix = source['chunk']+'-'+str(row['entry_id'])+'-'
                check_reader_fields(p, ['field-'+prefix+v['field'] for v in row['values'] if v['field'] not in {'name', 'title', 'type', 'birthday', 'sex'}], source['id'])
        stats['profiles'] += 1
    for id, slug in curated.items():
        row = records[index.get('aliases', {}).get(id, id)]
        p = page('sources/'+slug+'.html')
        check_reader_fields(p, ['field-'+v['field'] for v in row['values'] if v['field'] not in {'name', 'title', 'type', 'birthday', 'sex'}], id)
        stats['curatedOriginalPages'] += 1
    concepts = page('concepts.html')
    for i, concept in enumerate(book['concepts']):
        link_in_module(concepts, BASE+'/concepts/'+str(i)+'.html', concept['name'])
        p = page('concepts/'+str(i)+'.html')
        require(p.has_class('concept-original'), 'concept original wrapper absent')
        contains(p, concept['ref']['excerpt'], 'concept primary text')
        stats['conceptPages'] += 1
    stats['builtPagesChecked'] = len(cache)


def self_test():
    rejects = []
    raw_mutant = parse('<section class="lore-field" id="field-content"><h2 class="cva-title">본문</h2><div class="lore-source-text">original</div><details><dl><dd>OK</dd></dl><pre>lost original</pre></details></section>')
    fixture = '아래 값은 표현을 확인하기 위한 가상 예시입니다. 실제 결과를 주장하지 않습니다.'
    for name, check in (
        ('nonCvaDirectory', lambda: link_in_module(parse('<a href="/x">X</a>'), '/x', 'X')),
        ('rewrittenCvaBody', lambda: require_module(parse('<script data-cva-model>{"modules":[{"props":{"body":"changed"}}]}</script>'), 'original', 'mutated text')),
        ('rawReaderNotScoped', lambda: check_reader_fields(parse('<section class="lore-field" id="field-content"><pre>raw</pre></section>'), ['field-content'], 'mutated wrapper')),
        ('fieldAliasLost', lambda: check_reader_fields(parse('<section class="lore-field" id="field-content"><div class="rw-reader not-content cva-page" data-reading-template="reader" data-cva data-cva-profile="forma"><details data-reading-template="disclosure"></details></div></section>'), ['field-description'], 'mutated alias')),
        ('bodyLinkLabelChanged', lambda: link_in_module(parse('<div data-cva><a href="/x">changed</a></div>'), '/x', 'original')),
        ('rawOriginalLoss', lambda: check_field_value(raw_mutant, raw_mutant.has_class('lore-field')[0], {'raw': 'original', 'status': 'OK'}, 'mutated original')),
        ('visibleBodyDeletedModelRetained', lambda: require_visible_module(parse('<script data-cva-model>{"modules":[{"props":{"body":"original"}}]}</script>'), 'original', 'invisible body')),
        ('defaultFixtureLeak', lambda: reject_fixtures(parse('<p>'+fixture+'</p>'), re.compile(re.escape(fixture)), {})),
        ('authoringHintLeak', lambda: reject_fixtures(parse('<p class="sc-empty">항목을 추가하면 이 구도에서 내용을 이어 읽을 수 있습니다.</p>'), re.compile(re.escape(fixture)), {})),
        ('shortDefaultModelLeak', lambda: reject_fixtures(parse('<script data-cva-model>{"modules":[{"props":{"body":"공간"}}]}</script>'), {'pattern': re.compile(re.escape(fixture)), 'exact': {'공간'}}, {})),
        ('fixturePhraseElsewhereInOriginal', lambda: reject_fixtures(parse('<p>'+fixture+'</p><a href="/source">원문</a>'), re.compile(re.escape(fixture)), {'앞 문장. '+fixture+' 뒤 문장.': {'/source#field-content'}})),
        ('dynamicSourceIdChanged', lambda: dynamic_source_route(BASE+'/library.html#/source/changed?from=%23%2Flibrary', BASE+'/library.html#/source/original', '#/library')),
        ('dynamicFieldQueryLost', lambda: dynamic_source_route(BASE+'/library.html#/source/original?from=%23%2Flibrary', BASE+'/library.html#/source/original?field=info', '#/library')),
        ('dynamicReturnQueryLost', lambda: dynamic_return_link('<a href="#/library">← 원문 보관함</a>', '#/library?q=retained&category=profile&page=3&body=1')),
        ('dynamicExternalReturnAllowed', lambda: dynamic_return_link('<a href="https://example.invalid/">← 원문 보관함</a>', '#/library'))):
        try:
            check()
        except ValueError:
            rejects.append(name)
        else:
            raise ValueError('contamination accepted: '+name)
    # A phrase in the actual original is exempt only when the entire displayed
    # quotation matches the certified text and the real source link is present.
    reject_fixtures(parse('<p>'+fixture+'</p><a href="/source#field-content">원문</a>'),
                    re.compile(re.escape(fixture)), {fixture: {'/source#field-content'}})
    return rejects


def main(args):
    stats = Counter()
    site, dist = args.site.resolve(), args.dist.resolve()
    index = json.loads((site/'settings/index.json').read_text(encoding='utf-8'))
    book = json.loads((site/'settings/editorial.json').read_text(encoding='utf-8'))
    atlas = json.loads((site/'settings/atlas.json').read_text(encoding='utf-8'))
    atlas['people'] += json.loads((site/'settings/npc-people.json').read_text(encoding='utf-8'))['people']
    records = {}
    for file in (site/'settings').glob('records-*.json'):
        records.update(json.loads(file.read_text(encoding='utf-8')))
    manifest = json.loads((site/'settings/manifest.json').read_text(encoding='utf-8'))
    for name, digest in manifest['files'].items():
        raw = (site/'settings'/name).read_bytes()
        if manifest.get('hash_normalization', {}).get(name) == 'lf':
            raw = raw.decode('utf-8').replace('\r\n', '\n').encode('utf-8')
        require(hashlib.sha256(raw).hexdigest() == digest, 'preserved settings manifest SHA changed: '+name)
    curated = load_curated_sources(site, dist, index) if not args.dynamic_only else dict(index['curated_sources'])
    fixtures = canonical_fixtures(site)
    stats['canonicalDefaultFixtureStringsChecked'] = len(fixtures['exact'])
    literals = source_literals(site, index, records, book, atlas, curated)
    dynamic_check(site, index, records, curated, args.components.resolve(), stats, fixtures, literals,
                  None if args.dynamic_only else dist/'settings/curated-sources.json')
    if not args.dynamic_only:
        built_check(site, dist, index, records, book, atlas, curated, stats, fixtures, literals)
    rejects = self_test() if args.self_test else []
    print(json.dumps({'status': 'PASS', 'scope': 'whole-registry-source-preservation-and-actual-CVA-payloads',
                      'browserBehavior': 'NOT_TESTED', **stats, 'contaminationRejected': rejects}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=SITE)
    parser.add_argument('--dist', type=Path, default=SITE/'source/dist')
    parser.add_argument('--components', type=Path, default=SITE/'source/public/cva/components.js')
    parser.add_argument('--dynamic-only', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    try:
        main(parser.parse_args())
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(1)
