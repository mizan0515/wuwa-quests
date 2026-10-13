import importlib.util,json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
spec=importlib.util.spec_from_file_location('shared_ui',Path(__file__).with_name('share_publication_ui.py'));M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
class SharedUITest(unittest.TestCase):
 def test_two_pages_share_one_frame_module_and_keep_originals_static(self):
  with TemporaryDirectory()as tmp:
   root=Path(tmp)/'dist';root.mkdir();receipt=Path(tmp)/'receipt.json'
   behavior='window.addEventListener("DOMContentLoaded",()=>document.body.dataset.ready="yes");'+'/*behavior*/'*20
   header='<header class="header"><a href="/wuwa-quests/index.html">자료집</a>'+'<span>탐색</span>'*40+'</header>'
   originals={}
   for i in range(2):
    reading=f'<div class="original-row" data-reading-template="row"><p class="original-body" id="line-{i}">원문 {i} &amp; 선택지</p></div>'
    text=f'<!DOCTYPE html><html><head><script type="module">{behavior}</script></head><body>{header}<main>{reading}</main></body></html>'
    (root/f'{i}.html').write_text(text,'utf8');originals[i]=(text,reading)
   M.optimize(root,'/wuwa-quests',receipt);report=json.loads(receipt.read_text('utf8'))
   self.assertEqual(CounterKinds(report),{'behavior':1,'frame':1})
   for i,(text,reading)in originals.items():
    packed=(root/f'{i}.html').read_text('utf8');self.assertIn(reading,packed);self.assertNotIn(header,packed);self.assertEqual(M.expand(packed,report),text)
   self.assertLess(report['afterBytes'],report['beforeBytes']);M.optimize(root,'/wuwa-quests',receipt)
   (root/'0.html').write_text((root/'0.html').read_text('utf8').replace('원문 0','변조'),'utf8')
   with self.assertRaises(ValueError):M.verify(root,receipt)
 def test_reading_context_is_never_a_global_frame(self):
  text='<div id="starlight__sidebar"><div data-origin-model="{}"><p class="original-body">원문</p></div></div>'
  self.assertEqual(M.frames(text),[])
 def test_starlight_custom_sidebar_is_shared_as_one_balanced_frame(self):
  text='<sl-sidebar-pane id="starlight__sidebar"><div><nav>전체 탐색</nav></div></sl-sidebar-pane><main>본문</main>'
  self.assertEqual(M.frames(text),[(0,text.index('<main>'))])
 def test_svg_shape_shared_without_changing_outer_accessibility_or_exact_inverse(self):
  with TemporaryDirectory()as tmp:
   root=Path(tmp)/'dist';root.mkdir();receipt=Path(tmp)/'receipt.json'
   svg='<svg width="16" height="16" aria-hidden="true"><path d="'+'M1 2L3 4 '*40+'"/></svg>'
   text='<html><head></head><body>'+svg+'<p id="line-1" class="original-body">그대로</p></body></html>'
   for i in range(2):(root/f'{i}.html').write_text(text,'utf8')
   M.optimize(root,'/wuwa-quests',receipt);report=json.loads(receipt.read_text('utf8'));packed=(root/'0.html').read_text('utf8')
   self.assertIn('<svg width="16" height="16" aria-hidden="true"><use href="/wuwa-quests/_shared-ui/',packed)
   self.assertEqual(CounterKinds(report),{'icons':1});self.assertEqual(M.expand(packed,report),text)
def CounterKinds(report):
 from collections import Counter
 return dict(Counter(v['kind']for v in report['assets'].values()))
if __name__=='__main__':unittest.main()
