"""C443 open OSS YARA-X only. Public benign synthetic strings; never customer source."""
import hashlib, json, os, pathlib, tempfile, unittest
import yara_x
class YaraNativeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix="ansim-c443-synth-")
  self.addCleanup(self.temp.cleanup)
  self.path=pathlib.Path(self.temp.name)/"한글 file space"
  self.path.mkdir()
  self.rule_text='rule POSITIVE_MARK { strings: $a = "ONLY_C443_BENIGN_MARKER" ascii condition: $a }'
 def scanner(self, rule=None):
  r=yara_x.compile(self.rule_text if rule is None else rule)
  s=yara_x.Scanner(r);s.set_timeout(3);return s
 def matches(self, scanner, sample):
  return sorted(r.identifier for r in scanner.scan(sample).matching_rules)
 def test_01_native_windows(self):
  self.assertEqual(os.name,"nt")
 def test_02_pinned_engine_version(self):
  self.assertTrue(hasattr(yara_x,"compile"))
 def test_03_compile_positive(self):
  self.assertEqual(self.matches(self.scanner(),b"ONLY_C443_BENIGN_MARKER"),["POSITIVE_MARK"])
 def test_04_negative_not_a_safe_verdict(self):
  self.assertEqual(self.matches(self.scanner(),b"ordinary synthetic content"),[])
 def test_05_unicode_path_bytes(self):
  p=self.path/"가상 파일.txt";p.write_bytes(b"ONLY_C443_BENIGN_MARKER")
  self.assertEqual(self.matches(self.scanner(),p.read_bytes()),["POSITIVE_MARK"])
 def test_06_nonmatching_binary(self):
  self.assertEqual(self.matches(self.scanner(),bytes(range(256))),[])
 def test_07_repeated_match(self):
  s=self.scanner()
  self.assertEqual(self.matches(s,b"ONLY_C443_BENIGN_MARKER"*3),["POSITIVE_MARK"])
 def test_08_compile_reject_invalid_rule(self):
  with self.assertRaises(Exception):yara_x.compile("rule BAD { condition: }")
 def test_09_multiple_rule_ids(self):
  two=self.rule_text+'\nrule ALSO_POSITIVE { strings: $a="ONLY_C443_BENIGN_MARKER" ascii condition:$a }'
  self.assertEqual(self.matches(self.scanner(two),b"ONLY_C443_BENIGN_MARKER"),["ALSO_POSITIVE","POSITIVE_MARK"])
 def test_10_synthetic_file_stable_sha(self):
  p=self.path/"고객 아님.txt";p.write_bytes(b"ONLY_C443_BENIGN_MARKER")
  before=hashlib.sha256(p.read_bytes()).hexdigest();self.matches(self.scanner(),p.read_bytes())
  self.assertEqual(before,hashlib.sha256(p.read_bytes()).hexdigest())
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(YaraNativeTests)
 result=unittest.TestResult();suite.run(result)
 print('C443_PUBLIC_YARAX_WINDOWS_RECEIPT '+json.dumps(dict(
  native_windows=os.name=='nt',test_count=result.testsRun,failures=len(result.failures),
  errors=len(result.errors),official_wheel_expected_sha256='04be37c92bbbcba4065a4cf0f0029c0b0bf3e7c68f3c35b4cf523300e534cf58',
  public_synthetic_only=True,private_ansim_product_tested=False,
  malicious_samples_used=False,commercial_release='NO_GO',
  status='PASS' if result.wasSuccessful() and result.testsRun==10 else 'FAIL')))
 for test,tb in result.failures+result.errors:print("FAILED_CASE",str(test),tb.splitlines()[-1])
 raise SystemExit(0 if result.wasSuccessful() and result.testsRun==10 else 1)
