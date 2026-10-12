"""Read-only public compiled corroboration + current SQL/locale/native byte verification.

Standard library only. Requires the project's existing native verifier and the
adjacent compiled_native_fields.py wire reader. Writes only --report. Source
profile follows pinned CUE4Parse03e2339651f054b6d0e2940cc173a558593c680f
contracts; no game script executes and no source/owner/body is generated.
"""
from __future__ import annotations
import argparse,collections,copy,hashlib,importlib.util,json,pathlib,struct,sys,types
from html.parser import HTMLParser
from compiled_native_fields import Reader,nested_stops,Stop
SCHEMA='wuwa-compiled-sequence-references.v1'
EXPECTED={'states':23,'references':987,'proofs':987,'distinctTalkItems':261,'distinctNativeSections':987,'newKoreanRows':0,'newOwnerAttributions':0}
SECTION='/Script/SequenceDialogue.MovieSceneDialogueSection'
TEMPLATE='/Script/SequenceDialogue.MovieSceneDialogueSectionTemplate'
COMPILED='/Script/MovieScene.MovieSceneCompiledData'
def require(v,msg):
 if not v:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')
def load(path):return json.loads(path.read_text('utf8'))
def validate(data,native,m):
 m.sanitized(data);require(set(data)=={'schema','counts','sourceHashes','states','proofs','meaning'},'Compiled payload key schema differs');require(data['schema']==SCHEMA and data['counts']==EXPECTED,'Compiled declared schema/count differs');require(set(data['states'])<=set(native['states']),'Compiled state absent from originals');require(len(data['proofs'])==987,'Compiled proof count differs');items=set();sections=set();used=set();references=0
 for key,p in data['proofs'].items():
  require(set(p)=={'kind','source','uassetSha256','uexpSha256','compiledExportIndex','compiledClass','tracksUexpSpan','tracksBytesSha256','tracksFieldPointer','templatePointer','templateType','sourceSectionPointer','targetExportIndex','targetClass','fields','compiledTemplateFieldsEOF'},'Compiled proof key schema differs');require(sha(canonical(p))==key,'Compiled proof content hash differs');m.public_asset(p['source']);require(p['kind']=='COMPILED_MOVIESCENE_DIALOGUE_CORROBORATION'and p['compiledClass']==COMPILED and p['targetClass']==SECTION and p['templateType']==TEMPLATE and p['compiledTemplateFieldsEOF']is True,'Compiled typed domains differ')
  require(type(p['compiledExportIndex'])is int and p['compiledExportIndex']>0 and type(p['targetExportIndex'])is int and p['targetExportIndex']>0,'Compiled export index domain');require(p['templatePointer'].startswith('/entries/'),'Compiled map/template pointer domain');m.field_bytes(p['sourceSectionPointer']);sp=p['sourceSectionPointer'];require(sp['type']=='ObjectProperty'and struct.unpack('<i',m.field_bytes(sp))[0]==p['targetExportIndex']==sp['value']['packageIndex'],'Compiled SourceSectionPtr domain differs')
  require(set(p['fields'])=={'DialogueKey','DialogueID','SpeakerID'},'Compiled field key schema differs')
  for name,field in p['fields'].items():
   raw=m.field_bytes(field)
   if name=='SpeakerID':require(field['type']=='IntProperty'and type(field['value'])is int and len(raw)==4 and struct.unpack('<i',raw)[0]==field['value'],'Compiled speaker primitive differs')
   else:require(field['type']=='TextProperty'and m.native_ftext(raw)==field['value'],'Compiled FText framing/value differs')
 for sk,s in data['states'].items():
  base=native['states'][sk];require(set(s)=={'flowBlobSha256','compiledSequenceReferences'},'Compiled state key schema differs');require(s['flowBlobSha256']==base['flowBlobSha256'],'Compiled Flow state bytes differ');index={(r['talkItemPointer'],r['talkId'],r['speakerId'],r['textId'],r['nativeSectionProof']):r for r in base['nativeSequenceReferences']}
  for r in s['compiledSequenceReferences']:
   require(set(r)=={'talkItemPointer','talkId','speakerId','textId','rawKoreanSha256','nativeSectionProof','compiledProof'}and type(r['talkId'])is int and type(r['speakerId'])is int,'Compiled reference schema differs');rk=(r['talkItemPointer'],r['talkId'],r['speakerId'],r['textId'],r['nativeSectionProof']);require(rk in index and r['rawKoreanSha256']==index[rk]['rawKoreanSha256'],'Compiled ref does not match exact frozen native identity');p=data['proofs'][r['compiledProof']];np=native['proofs'][r['nativeSectionProof']];require(np['kind']=='WHOLE_NATIVE_DIALOGUE_SECTION_EOF'and p['source']==np['source']and p['targetExportIndex']==np['exportIndex']and p['uassetSha256']==np['uassetSha256']and p['uexpSha256']==np['uexpSha256']and p['sourceSectionPointer']['value']['object']==np['exportName'],'Compiled/native section identity differs');require(p['fields']['DialogueKey']['value']['source_string']==r['textId']and p['fields']['DialogueID']['value']['source_string']==str(r['talkId'])and p['fields']['SpeakerID']['value']==r['speakerId'],'Compiled Flow triple differs');used.add(r['compiledProof']);items.add((sk,r['talkItemPointer'],r['talkId'],r['speakerId'],r['textId']));sections.add((np['source'],np['exportIndex']));references+=1
 require(references==987 and len(data['states'])==23 and len(items)==261 and len(sections)==987 and used==set(data['proofs']),'Compiled reference/item/proof partition differs')
 return {'publicCompiledReferences':references,'publicDistinctTalkItems':len(items),'publicCompiledProofs':len(used)}
def top_fields(pkg,index,m,span=None):
 require(0<index<=len(pkg.exports),'Compiled source export index domain');ex=pkg.exports[index-1];start,end=span if span else(ex['start'],ex['start']+ex['size']);r=m.Bytes(pkg.uexp,start,end);out=[]
 while True:
  tag=r.at;name=pkg.name(r)
  if name=='None':break
  typ=pkg.name(r);size=r.num('i');array=r.num('i');require(size>=0 and array>=0,'Compiled tag size domain');meta={}
  if typ=='StructProperty':meta['structType']=pkg.name(r);r.take(16)
  elif typ in('ArrayProperty','SetProperty'):meta['innerType']=pkg.name(r)
  elif typ=='MapProperty':meta['keyType']=pkg.name(r);meta['valueType']=pkg.name(r)
  elif typ in('ByteProperty','EnumProperty'):pkg.name(r)
  elif typ=='BoolProperty':require(r.num('B')in(0,1),'Tagged bool domain')
  guid=r.num('B');require(guid in(0,1),'Compiled tag GUID domain')
  if guid:r.take(16)
  at=r.at;raw=r.take(size);out.append({'name':name,'type':typ,'start':at,'end':r.at,'raw':raw,'tagStart':tag,**meta})
 require(r.at==end if span else(pkg.uexp[r.at:end]==b'\0'*4 or(r.at==end and ex['flags']&0x10)),'Compiled export/struct tail/profile unsupported')
 return ex,out
def select_field(pkg,index,path,m):
 ex,fields=top_fields(pkg,index,m);parts=path.split('/')[1:];field=fields[int(parts.pop(0))]
 while parts:
  require(parts.pop(0)=='properties'and field['type']=='StructProperty','Compiled tagged struct field pointer domain');_,fields=top_fields(pkg,index,m,(field['start'],field['end']));field=fields[int(parts.pop(0))]
 return ex,field
def adapter(pkg):
 return types.SimpleNamespace(names=pkg.names,imports=[{'class_package':x[0],'class_name':x[1],'outer_index':x[2],'object_name':x[3]}for x in pkg.imports],exports=[{'object_name':x['name']}for x in pkg.exports])
def locate(sources,roots,m):
 found={}
 for root in roots:
  require(root.is_dir(),'Extraction root absent')
  for p in root.rglob('*.uasset'):
   s=p.as_posix();marker='Client/Content/'
   if marker not in s:continue
   virtual=marker+s.split(marker,1)[1]
   if virtual not in sources:continue
   if virtual in found:require(sha(p.read_bytes())==sha(found[virtual].read_bytes())and sha(p.with_suffix('.uexp').read_bytes())==sha(found[virtual].with_suffix('.uexp').read_bytes()),'Ambiguous actual source pairs')
   else:found[virtual]=p
 require(set(found)==sources,'Exact compiled source packages absent')
 return found
def actual_replay(data,native,roots,m):
 found=locate({p['source']for p in data['proofs'].values()},roots,m);packages={};tracks={};sections={};count=0
 for key,p in data['proofs'].items():
  source=p['source']
  if source not in packages:
   pkg=m.NativePackage(found[source]);packages[source]=pkg;require(sha(pkg.uasset)==p['uassetSha256']and sha(pkg.uexp)==p['uexpSha256'],'Actual compiled source hash differs')
  pkg=packages[source];cachekey=(source,p['compiledExportIndex'])
  if cachekey not in tracks:
   ex,field=select_field(pkg,p['compiledExportIndex'],p['tracksFieldPointer'],m);require(pkg.resolve(ex['classIndex'])==COMPILED,'Actual compiled export class differs');require(field['name']=='Tracks'and field['type']=='MapProperty'and field['keyType']=='StructProperty'and field['valueType']=='StructProperty','Actual Tracks map metadata differs');a=adapter(pkg);r=Reader(field['raw'],a.names,a.imports,a.exports,field['start']);value=r.decode('MapProperty',None,'Tracks',field);r.eof();require(not nested_stops(value),'Actual compiled nested serializer STOP');tracks[cachekey]=(field,value)
  field,value=tracks[cachekey];require([field['start'],field['end']]==p['tracksUexpSpan']and sha(field['raw'])==p['tracksBytesSha256'],'Actual Tracks field span/hash differs');template=m.pointer(value,p['templatePointer']);require(template['typeName']==TEMPLATE,'Actual selected template type differs');props={x['name']:x for x in template['properties']};require(props['SourceSectionPtr']['value']['packageIndex']==p['targetExportIndex'],'Actual compiled SourceSectionPtr differs')
  for name,public in [('SourceSectionPtr',p['sourceSectionPointer'])]+list(p['fields'].items()):
   actual=props[name];require(actual['type']==public['type']and actual['status']=='FIELD_EOF_PASS'and [actual['bodyOffset'],actual['bodyOffset']+actual['bytes']]==public['uexpSpan'],'Actual compiled field tag/span differs');require(pkg.uexp[actual['bodyOffset']:actual['bodyOffset']+actual['bytes']]==m.field_bytes(public),'Actual compiled field bytes differ')
  sk=(source,p['targetExportIndex'])
  if sk not in sections:
   ex,props,start,end=pkg.export_fields(p['targetExportIndex']);require(pkg.resolve(ex['classIndex'])==SECTION,'Actual selected section class differs');sections[sk]=(ex,props,start,end)
  count+=1
 return {'actualCompiledProofs':count,'actualCompiledPackages':len(packages),'actualTracksBodiesEOF':len(tracks),'actualTypedSectionTargets':len(sections)}
def negatives(data,native,m):
 tests=[]
 def key_mismatch(p):
  f=p['fields']['DialogueKey'];v=f['value']['source_string'];f['value']['source_string']=v[:-1]+('Z'if v[-1:]!='Z'else'Y');b=bytes.fromhex(f['nativeBytesHex']);b=b[:-2]+f['value']['source_string'][-1:].encode('ascii')+b'\0';f['nativeBytesHex']=b.hex();f['nativeBytesSha256']=sha(b)
 def ptr_mismatch(p):
  p['targetExportIndex']=0;f=p['sourceSectionPointer'];f['value']['packageIndex']=0;f['nativeBytesHex']='00000000';f['nativeBytesSha256']=sha(bytes(4))
 for name,mutation in [('compiledKey',key_mismatch),('sourceSectionDomain',ptr_mismatch),('sourceSectionClass',lambda p:p.__setitem__('targetClass','/Script/CoreUObject.Function'))]:
  d=copy.deepcopy(data);old=next(iter(d['proofs']));p=d['proofs'].pop(old);mutation(p);new=sha(canonical(p));d['proofs'][new]=p
  for state in d['states'].values():
   for ref in state['compiledSequenceReferences']:
    if ref['compiledProof']==old:ref['compiledProof']=new
  try:validate(d,native,m);raise RuntimeError('Invalid compiled proof accepted')
  except ValueError:tests.append(name)
 d=copy.deepcopy(data);r=next(iter(d['states'].values()))['compiledSequenceReferences'][0];r['talkId']+=1
 try:validate(d,native,m);raise RuntimeError('Invalid compiled item identity accepted')
 except ValueError:tests.append('frozenItemIdentity')
 return tests
class CompiledHTML(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.stack=[];self.markers=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs);parent=self.stack[-1]if self.stack else(None,None,None,None,None);state=a.get('data-dialogue-state',parent[1]);section=a.get('data-native-section',parent[2]);talk=a.get('data-native-flow-talk',parent[3]);text=a.get('data-native-flow-text',parent[4])
  if 'data-compiled-proof'in a:
   require(state is not None and section is not None,'Compiled marker outside original native section');require(a.get('data-compiled-native-section')==section and a.get('data-compiled-flow-talk')==talk and a.get('data-compiled-flow-text')==text,'Compiled rendered state/native identity differs');self.markers.append((state,section,a['data-compiled-proof'],talk,text))
  if tag not in('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):self.stack.append((tag,state,section,talk,text))
 def handle_endtag(self,tag):
  positions=[i for i,x in enumerate(self.stack)if x[0]==tag]
  if positions:del self.stack[positions[-1]:]
def dist_replay(data,original,dist):
 expected=collections.Counter((sk,r['nativeSectionProof'],r['compiledProof'],str(r['talkId']),r['textId'])for sk,s in data['states'].items()for r in s['compiledSequenceReferences']);actual=collections.Counter();bearing=0
 for group in original['groups']:
  p=dist/'dialogue-sources'/(group['id']+'.html');require(p.is_file(),'Rendered original group absent');parser=CompiledHTML();parser.feed(p.read_text('utf8'));parser.close();actual.update(parser.markers);bearing+=bool(parser.markers)
 require(actual==expected,'Rendered compiled references absent/duplicated or wrong section/item identity')
 return {'renderedCompiledReferences':sum(actual.values()),'renderedCompiledOriginalGroups':bearing,'checkedOriginalGroups':len(original['groups'])}
def html_negatives():
 good='<section data-dialogue-state="state"><li data-native-section="native" data-native-flow-talk="1" data-native-flow-text="text"><details><summary>Compiled</summary><div data-compiled-proof="compiled" data-compiled-native-section="native" data-compiled-flow-talk="1" data-compiled-flow-text="text"></div></details></li></section>';p=CompiledHTML();p.feed(good);require(len(p.markers)==1,'Compiled HTML positive canary failed');tests=[]
 for name,bad in [('renderedSectionMismatch',good.replace('data-compiled-native-section="native"','data-compiled-native-section="other"')),('renderedTextMismatch',good.replace('data-compiled-flow-text="text"','data-compiled-flow-text="other"')),('renderedOutsideSection',good.replace('data-native-section="native"',''))]:
  try:p=CompiledHTML();p.feed(bad);raise RuntimeError('Invalid rendered compiled proof accepted')
  except ValueError:tests.append(name)
 return tests
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project-root',required=True,type=pathlib.Path);ap.add_argument('--overlay',type=pathlib.Path);ap.add_argument('--expected-overlay-sha256');ap.add_argument('--configdb',type=pathlib.Path);ap.add_argument('--extracted-roots',nargs='+',type=pathlib.Path);ap.add_argument('--public-only',action='store_true',help='Explicit payload/dist validation without source input replay');ap.add_argument('--dist',type=pathlib.Path);ap.add_argument('--report',type=pathlib.Path);a=ap.parse_args();require(a.public_only or(a.configdb and a.extracted_roots),'Default source verification requires --configdb and --extracted-roots');require(not a.public_only or(not a.configdb and not a.extracted_roots),'Source arguments require default source verification mode');root=a.project_root.resolve();tool=root/'source/tools/verify_native_sequence_references.py';spec=importlib.util.spec_from_file_location('project_native_verifier',tool);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);settings=root/'settings';manifest=load(settings/'manifest.json');path=a.overlay or settings/'compiled-sequence-references.json';raw=path.read_bytes();pin=a.expected_overlay_sha256 or manifest['files'].get('compiled-sequence-references.json');require(pin is not None and sha(raw)==pin,'Compiled overlay byte pin absent/different');nb=(settings/'native-sequence-references.json').read_bytes();ob=(settings/'dialogue-attribution.json').read_bytes();require(sha(nb)==manifest['files']['native-sequence-references.json']and sha(ob)==manifest['files']['dialogue-attribution.json'],'Original/native public manifest byte pin differs');data=json.loads(raw);native=json.loads(nb);original=json.loads(ob);require(data['sourceHashes']['nativeSequenceReferences']==sha(nb)and data['sourceHashes']['dialogueAttribution']==sha(ob)and data['sourceHashes']['flowDB']==native['sourceHashes']['flowDB']and data['sourceHashes']['localeDBs']==native['sourceHashes']['localeDBs'],'Compiled source pins differ from originals');m.validate_payload(native,original);counts=validate(data,native,m)
 if not a.public_only:counts.update(m.configdb_replay(native,original,a.configdb.resolve()));counts.update(actual_replay(data,native,[x.resolve()for x in a.extracted_roots],m))
 if a.dist:counts.update(dist_replay(data,original,a.dist.resolve()))
 tests=negatives(data,native,m)+html_negatives();out={'schema':'wuwa-compiled-sequence-source-verification.v1','status':'PASS','overlaySha256':sha(raw),'counts':counts,'negativeCasesRejected':tests,'verifiedSurfaces':{'publicOverlay':True,'originalAndNativePins':True,'actualSQLLocale':not a.public_only,'actualCompiledSourceBytes':not a.public_only,'renderedHTML':bool(a.dist)},'limits':['Compiled source corroboration of existing originals; no owner attribution or new Korean body.','Native compiled source selected by typed map/template/SourceSectionPtr identity. Runtime invocation is not claimed.']}
 if a.report:
  report=a.report.resolve();protected=[settings.resolve()]+([a.configdb.resolve()if a.configdb.is_dir()else a.configdb.resolve().parent]if a.configdb else[])+[x.resolve()for x in(a.extracted_roots or[])];require(report.suffix=='.json'and report not in{path.resolve(),tool.resolve(),pathlib.Path(__file__).resolve()}and not any(report.is_relative_to(x)for x in protected),'Report cannot overwrite source/config/extraction input');report.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf8')
 print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':
 try:main()
 except(ValueError,KeyError,IndexError,UnicodeError,struct.error,OSError,Stop)as e:print('Compiled source verification FAIL: '+str(e),file=sys.stderr);sys.exit(1)
