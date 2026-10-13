import io,tarfile,tempfile,unittest
from pathlib import Path
from verify_pages_artifact import verify,blob_digest
class PagesArtifactTests(unittest.TestCase):
 def check(self,files,expected):
  with tempfile.TemporaryDirectory()as tmp:
   target=Path(tmp)/'artifact.tar'
   with tarfile.open(target,'w')as tar:
    for name,raw in files.items():
     info=tarfile.TarInfo(name);info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
   return verify(target,{k:blob_digest(v)for k,v in expected.items()})
 def test_sources_original_export_and_shared_module_all_survive(self):
  files={'sources/record.html':b'original','originals/quest.txt':b'speaker\r\nchoice','_shared-ui/core.js':b'module'}
  self.assertEqual(self.check(files,files)['status'],'PASS')
 def test_missing_curated_source_is_rejected_even_when_the_site_is_small(self):
  result=self.check({'index.html':b'index'},{'index.html':b'index','sources/record.html':b'original'})
  self.assertEqual(result['status'],'FAIL');self.assertIn('Missing original publication file: sources/record.html',result['errors'])
 def test_rewritten_original_or_generated_orphan_or_development_input_is_rejected(self):
  expected={'originals/quest.txt':b'original'}
  for extra in ({'originals/quest.txt':b'changed'},{**expected,'source/package.json':b'{}'},{**expected,'settings/orphan.html':b'orphan'}):
   self.assertEqual(self.check(extra,expected)['status'],'FAIL')
if __name__=='__main__':unittest.main()
