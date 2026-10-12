"""Bounded, independently written UE4.26 field reader; no raw-ID attribution."""
import struct, hashlib

class Stop(ValueError):
 def __init__(self,offset,reason):self.offset=offset;self.reason=reason;super().__init__(f'{reason}@{offset}')

class Reader:
 def __init__(self,data,names,imports,exports,base=0):
  self.b=data;self.p=0;self.base=base;self.names=names;self.imports=imports;self.exports=exports
 def get(self,fmt):
  n=struct.calcsize('<'+fmt)
  if self.p+n>len(self.b):raise Stop(self.base+self.p,'FIELD_READ_BOUNDS')
  v=struct.unpack_from('<'+fmt,self.b,self.p)[0];self.p+=n;return v
 def skip(self,n):
  if n<0 or self.p+n>len(self.b):raise Stop(self.base+self.p,'FIELD_SKIP_BOUNDS')
  self.p+=n
 def fname(self):
  at=self.p;i=self.get('i');n=self.get('i')
  if i<0 or i>=len(self.names) or n<0:raise Stop(self.base+at,'FNAME_DOMAIN')
  return self.names[i]+('_'+str(n-1)if n else'')
 def string(self):
  at=self.p;n=self.get('i');size=n if n>=0 else -n*2
  if size>len(self.b)-self.p:raise Stop(self.base+at,'FSTRING_BOUNDS')
  raw=self.b[self.p:self.p+size];self.p+=size
  if n==0:return''
  tail=1 if n>0 else 2
  if raw[-tail:]!=bytes(tail):raise Stop(self.base+self.p-tail,'FSTRING_TERMINATOR')
  try:return raw[:-tail].decode('utf8'if n>0 else'utf-16-le')
  except UnicodeError:raise Stop(self.base+at,'FSTRING_ENCODING')
 def count(self,stride=1):
  at=self.p;n=self.get('i')
  if n<0 or n>(len(self.b)-self.p)//stride:raise Stop(self.base+at,'ARRAY_COUNT_BOUNDS')
  return n
 def object(self):
  at=self.p;i=self.get('i')
  if i>len(self.exports)or -i>len(self.imports):raise Stop(self.base+at,'PACKAGE_INDEX_DOMAIN')
  def resolve(j,seen=None):
   seen=set()if seen is None else seen
   if j in seen:raise Stop(self.base+at,'PACKAGE_INDEX_CYCLE')
   seen.add(j)
   if j==0:return None
   if j>0:return self.exports[j-1]['object_name']
   x=self.imports[-j-1];outer=x['outer_index']
   return (str(resolve(outer,seen))+'.'if outer else'')+x['object_name']
  return {'packageIndex':i,'object':resolve(i),'byteOffset':self.base+at}
 def child(self,size):
  if size<0 or size>len(self.b)-self.p:raise Stop(self.base+self.p,'TAG_SIZE_BOUNDS')
  r=Reader(self.b[self.p:self.p+size],self.names,self.imports,self.exports,self.base+self.p);self.p+=size;return r
 def eof(self):
  if self.p!=len(self.b):raise Stop(self.base+self.p,'FIELD_TRAILING_BYTES')
 def primitive(self,typ,st=None):
  if typ=='ObjectProperty':return self.object()
  if typ=='IntProperty':return self.get('i')
  if typ=='UInt32Property':return self.get('I')
  if typ=='UInt16Property':return self.get('H')
  if typ=='Int16Property':return self.get('h')
  if typ=='ByteProperty':return self.get('B')
  if typ=='BoolProperty':
   at=self.p;b=self.get('B')
   if b not in(0,1):raise Stop(self.base+at,'BOOLEAN_FLAG_DOMAIN')
   return bool(b)
  if typ=='TextProperty':
   flags=self.get('I');history=self.get('b')
   if history!=0:raise Stop(self.base+self.p-1,'FTEXT_HISTORY_UNSUPPORTED_'+str(history))
   return {'flags':flags,'historyType':history,'namespace':self.string(),'key':self.string(),'sourceString':self.string(),'locale':'native-editor-source; not Korean locale'}
  if typ=='FloatProperty':return self.get('f')
  if typ=='NameProperty':return self.fname()
  if typ=='StrProperty':return self.string()
  if typ=='SoftObjectProperty':return {'assetPath':self.fname(),'subPath':self.string()}
  if typ=='StructProperty'and st in('MovieSceneSequenceID','MovieSceneTrackIdentifier'):return {'domain':st,'value':self.get('I')}
  if typ=='StructProperty'and st=='Guid':return {'domain':'Guid','words':[self.get('I')for _ in range(4)]}
  if typ=='StructProperty'and st in('NiagaraVariable','NiagaraVariableWithOffset'):
   name=self.fname();definition=self.tagged()
   if st=='NiagaraVariable':n=self.count();data=self.b[self.p:self.p+n].hex();self.skip(n);return {'name':name,'typeDefinition':definition,'varDataHex':data}
   return {'name':name,'typeDefinition':definition,'offset':self.get('i')}
  raise Stop(self.base+self.p,'UNSUPPORTED_PRIMITIVE_'+typ+'_'+str(st))
 def node(self):
  bounds=[]
  for _ in range(2):
   at=self.p;k=self.get('B');v=self.get('i')
   if k>2:raise Stop(self.base+at,'RANGE_BOUND_ENUM')
   bounds.append({'kind':k,'frame':v})
  return {'range':bounds,'parentChildrenHandle':self.get('i'),'parentIndex':self.get('i'),'childrenID':self.get('i'),'dataID':self.get('i')}
 def container(self,getter,stride):
  entries=[{'start':self.get('i'),'size':self.get('i'),'capacity':self.get('i')}for _ in range(self.count(12))]
  items=[getter()for _ in range(self.count(stride))]
  for e in entries:
   if min(e.values())<0 or e['size']>e['capacity']or e['start']+e['capacity']>len(items):raise Stop(self.base+self.p,'TREE_ENTRY_DOMAIN')
  return {'entries':entries,'items':items}
 def tree(self,subsequence=False):
  root=self.node();children=self.container(self.node,26)
  def item():
   if subsequence:
    at=self.p;s=self.get('I');f=self.get('B')
    if f>3:raise Stop(self.base+at+4,'EVALUATION_FLAGS_DOMAIN')
    return {'sequenceID':s,'evaluationFlags':f}
   return {'entityIndex':self.get('i'),'metaDataIndex':self.get('i')}
  data=self.container(item,5 if subsequence else 8)
  for n in [root]+children['items']:
   if n['childrenID']<-1 or n['childrenID']>=len(children['entries'])or n['dataID']<-1 or n['dataID']>=len(data['entries']):raise Stop(self.base+self.p,'TREE_HANDLE_DOMAIN')
  return {'root':root,'children':children,'data':data}
 def curve(self):
  pre=self.get('B');post=self.get('B')
  if pre>4 or post>4:raise Stop(self.base+self.p-2,'CURVE_EXTRAP_ENUM')
  at=self.p;ts=self.get('i')
  if ts!=4:raise Stop(self.base+at,'CURVE_TIME_ELEMENT_SIZE')
  times=[self.get('i')for _ in range(self.count(4))]
  at=self.p;vs=self.get('i')
  if vs!=28:raise Stop(self.base+at,'CURVE_VALUE_ELEMENT_SIZE')
  values=[]
  for _ in range(self.count(28)):
   val=self.get('f');t=[self.get('f')for _ in range(4)];w=self.get('B');self.skip(3);i=self.get('B');m=self.get('B');self.skip(2)
   if w>3 or i>5 or m>3:raise Stop(self.base+self.p-8,'CURVE_VALUE_ENUM')
   values.append((val,t,w,i,m))
  default=self.get('f');at=self.p;has=self.get('i')
  if has not in(0,1):raise Stop(self.base+at,'BOOLEAN_DOMAIN')
  numerator=self.get('i');denominator=self.get('i')
  if len(times)!=len(values):raise Stop(self.base+self.p,'CURVE_TIMES_VALUES_COUNT')
  return {'preInfinity':pre,'postInfinity':post,'timesCount':len(times),'valuesCount':len(values),'timeElementSize':ts,'valueElementSize':vs,'defaultValue':default,'hasDefault':bool(has),'tickResolution':[numerator,denominator],'typedDomain':'visual-float-channel; no text/state identity'}
 def tagged(self):
  props=[]
  while True:
   tagat=self.base+self.p;name=self.fname()
   if name=='None':return props
   typ=self.fname();size=self.get('i');index=self.get('i');meta={}
   if typ=='StructProperty':meta['structType']=self.fname();self.skip(16)
   elif typ in('ArrayProperty','SetProperty'):meta['innerType']=self.fname()
   elif typ=='MapProperty':meta['keyType']=self.fname();meta['valueType']=self.fname()
   elif typ in('ByteProperty','EnumProperty'):meta['enumType']=self.fname()
   elif typ=='BoolProperty':meta['boolValue']=self.get('B')
   flag=self.get('B')
   if flag not in(0,1):raise Stop(self.base+self.p-1,'TAG_GUID_MARKER')
   if flag:self.skip(16)
   sub=self.child(size);rec={'name':name,'type':typ,'tagOffset':tagat,'bodyOffset':sub.base,'bytes':size,'arrayIndex':index,**meta}
   try:rec['value']=sub.decode(typ,meta.get('structType'),name,meta);sub.eof();rec['status']='FIELD_EOF_PASS'
   except Stop as e:rec['status']='STOP';rec['firstFailureOffset']=e.offset;rec['firstFailure']=e.reason
   props.append(rec)
 def decode(self,typ,st=None,name='',meta=None):
  meta=meta or{}
  if typ=='MulticastInlineDelegateProperty':
   return [{'target':self.object(),'functionName':self.fname()}for _ in range(self.count(12))]
  if typ=='StructProperty':
   if st=='MovieSceneFloatChannel':return self.curve()
   if st=='MovieSceneEvaluationFieldEntityTree':return self.tree()
   if st=='MovieSceneSubSequenceTree':return self.tree(True)
   if st=='SoftObjectPath':return {'assetPath':self.fname(),'subPath':self.string()}
   if st=='LinearColor':return {k:self.get('f')for k in('R','G','B','A')}
   if st in('Vector','Rotator'):return {k:self.get('f')for k in('X','Y','Z')}
   if st=='MovieSceneEvaluationKey':return {'sequenceID':self.get('I'),'trackIdentifier':self.get('I'),'sectionIndex':self.get('I'),'typedDomain':'native evaluation key'}
   if st in('MovieSceneSequenceInstanceDataPtr','MovieSceneTrackImplementationPtr','MovieSceneEvalTemplatePtr'):
    name=self.string()
    if name.endswith('.MovieSceneLiveLinkSectionTemplate'):raise Stop(self.base+self.p,'LIVELINK_NATIVE_TAIL_UNSUPPORTED')
    return {'typeName':name,'properties':self.tagged()if name else None}
   if st in('NiagaraVariable','NiagaraVariableWithOffset'):return self.primitive(typ,st)
   if st in('Guid','MovieSceneSequenceID','MovieSceneTrackIdentifier'):return self.primitive(typ,st)
   if st=='MovieSceneFrameRange':
    out=[]
    for _ in range(2):
     k=self.get('B');v=self.get('i')
     if k>2:raise Stop(self.base+self.p-5,'RANGE_BOUND_ENUM')
     out.append({'kind':k,'frame':v})
    return out
   if st=='FrameNumber':return self.get('i')
   if st=='FrameRate'and len(self.b)==8:return[self.get('i'),self.get('i')]
   return self.tagged()
  if typ=='MapProperty':
   if name=='BindingGroups':
    if meta.get('keyType',meta.get('key_type'))!='NameProperty'or meta.get('valueType',meta.get('mapped_type'))!='StructProperty':raise Stop(self.base+self.p,'MAP_TYPE_DOMAIN')
    removed=[self.fname()for _ in range(self.count(8))];entries=[]
    for _ in range(self.count(8)):entries.append({'key':{'domain':'NameProperty','value':self.fname()},'value':self.tagged()})
    return {'removed':removed,'entries':entries,'schemaSource':'UScriptMap primitive NameProperty key; unspecified struct mapped value uses FStructFallback tagged serializer'}
   schema={'Tracks':('MovieSceneTrackIdentifier',None),'SubSequences':('MovieSceneSequenceID',None),'Hierarchy':('MovieSceneSequenceID',None),'TrackSignatureToTrackIdentifier':('Guid','MovieSceneTrackIdentifier'),'BindingIdToReferences':('Guid',None),'UserParameterRedirects':('NiagaraVariable','NiagaraVariable')}
   if name not in schema:raise Stop(self.base+self.p,'MAP_STRUCT_SCHEMA_UNSUPPORTED_'+name)
   key,val=schema[name]
   if meta.get('keyType',meta.get('key_type'))!='StructProperty'or meta.get('valueType',meta.get('mapped_type'))!='StructProperty':raise Stop(self.base+self.p,'MAP_TYPE_DOMAIN')
   removed=[self.primitive('StructProperty',key)for _ in range(self.count(4))];entries=[]
   for _ in range(self.count(4)):
    k=self.primitive('StructProperty',key);v=self.primitive('StructProperty',val)if val else self.tagged();entries.append({'key':k,'value':v})
   return {'removed':removed,'entries':entries,'schemaSource':'VersionContainer.InitMapStructTypes'}
  if typ=='ArrayProperty':
   inner=meta.get('innerType')
   if inner=='StructProperty':
    n=self.count();self.fname();itype=self.fname();size=self.get('i');idx=self.get('i');sst=self.fname();self.skip(16);flag=self.get('B')
    if flag not in(0,1)or itype!='StructProperty':raise Stop(self.base+self.p,'ARRAY_INNER_TAG')
    if flag:self.skip(16)
    return [self.decode('StructProperty',sst)for _ in range(n)]
   return [self.primitive(inner)for _ in range(self.count())]
  if typ=='BoolProperty'and len(self.b)==0:return bool(meta['boolValue'])
  if typ in('ByteProperty','EnumProperty')and len(self.b)==8:return self.fname()
  return self.primitive(typ,st)

def replay(data,pkg,field):
 r=Reader(data,pkg.names,pkg.imports,pkg.exports,field['offset']);value=r.decode(field['type'],field.get('structType'),field['property'],field);r.eof();return value

def nested_stops(value):
 if isinstance(value,list):return [s for x in value for s in nested_stops(x)]
 if isinstance(value,dict):
  if value.get('status')=='STOP':return [value]
  return [s for x in value.values()for s in nested_stops(x)]
 return []
