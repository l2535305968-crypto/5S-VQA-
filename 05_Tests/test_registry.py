from __future__ import annotations
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'04_Scripts'/'validate_registry.py'
REGISTRY=ROOT/'02_Style_Registry'

class RegistryTest(unittest.TestCase):
    def run_validation(self,path):
        return subprocess.run([sys.executable,str(SCRIPT),'--root',str(path)],capture_output=True,text=True)

    def test_valid_open_registry(self):
        p=self.run_validation(REGISTRY)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('PASS',p.stdout)

    def test_duplicate_profile_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'registry'
            shutil.copytree(REGISTRY,root)
            idx=root/'registry.json'
            obj=json.loads(idx.read_text(encoding='utf-8'))
            obj['entries'].append(dict(obj['entries'][0]))
            idx.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8')
            p=self.run_validation(root)
            self.assertEqual(p.returncode,2)
            self.assertIn('Duplicate ID',p.stderr)

    def test_unknown_extension_fields_accepted(self):
        # Future media/visual axes may add fields without altering the global core.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'registry'
            shutil.copytree(REGISTRY,root)
            pfile=root/'Profiles'/'ink-wash-experimental.json'
            prof=json.loads(pfile.read_text(encoding='utf-8'))
            prof['extensions']['experimental-depth-rhythm']={'metric':'intent-based'}
            prof['entirely_new_visual_medium_axis']=['intentional_new_semantics']
            pfile.write_text(json.dumps(prof,ensure_ascii=False),encoding='utf-8')
            p=self.run_validation(root)
            self.assertEqual(p.returncode,0,p.stderr)

    def test_draft_cannot_be_officially_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'registry'
            shutil.copytree(REGISTRY,root)
            index_path=root/'registry.json'
            index=json.loads(index_path.read_text(encoding='utf-8'))
            entry=index['entries'][0]
            profile_path=root/entry['path']
            profile=json.loads(profile_path.read_text(encoding='utf-8'))
            profile['status']='draft'
            profile_path.write_text(json.dumps(profile,ensure_ascii=False),encoding='utf-8')
            entry['status']='draft'
            index_path.write_text(json.dumps(index,ensure_ascii=False),encoding='utf-8')
            p=self.run_validation(root)
            self.assertEqual(p.returncode,2)
            self.assertIn('draft cannot be registered',p.stderr)

    def test_missing_style_fields_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'registry'
            shutil.copytree(REGISTRY,root)
            pfile=root/'Profiles'/'cinematic-photography.json'
            prof=json.loads(pfile.read_text(encoding='utf-8'))
            del prof['visual_rules']
            pfile.write_text(json.dumps(prof,ensure_ascii=False),encoding='utf-8')
            p=self.run_validation(root)
            self.assertEqual(p.returncode,2)
            self.assertIn('visual_rules',p.stderr)

if __name__=='__main__':
    unittest.main()
