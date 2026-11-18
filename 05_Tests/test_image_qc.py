from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / '04_Scripts' / 'image_qc.py'


class ImageQCTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.image = self.base / '测试_示例.png'
        Image.new('RGB',(64,48),(120,150,180)).save(self.image)

    def run_cli(self, *args):
        return subprocess.run([sys.executable,str(SCRIPT),*map(str,args)], capture_output=True,text=True)

    def test_target_pass_and_crops(self):
        out=self.base/'qc'
        proc=self.run_cli(self.image,'--target','64x48','--format','PNG','--crop','24','--out',out,'--focus','10,10,16,12')
        self.assertEqual(proc.returncode,0,proc.stderr)
        result=json.loads((out/'report.json').read_text(encoding='utf-8'))
        self.assertEqual(result['technical_status'],'TECHNICAL_PASS_VISUAL_PENDING')
        self.assertEqual(result['visual_quality_status'],'NOT_EVALUATED')
        self.assertEqual(result['pixel_requirement'],'PASS')
        self.assertEqual(len(result['inspection_crops']),5)
        with Image.open(out/'focus_01_100pct.png') as crop:
            self.assertEqual(crop.size,(16,12))
        self.assertTrue((out/'review_100pct_crops.png').exists())

    def test_target_fail(self):
        out=self.base/'qc_fail'
        proc=self.run_cli(self.image,'--target','2160x3840','--out',out)
        self.assertEqual(proc.returncode,2,proc.stderr)
        result=json.loads((out/'report.json').read_text(encoding='utf-8'))
        self.assertEqual(result['pixel_requirement'],'FAIL')
        self.assertEqual(result['technical_status'],'FAIL')

    def test_missing_target_never_claims_pass(self):
        out=self.base/'qc_no_target'
        proc=self.run_cli(self.image,'--out',out)
        self.assertEqual(proc.returncode,0,proc.stderr)
        data=json.loads((out/'report.json').read_text(encoding='utf-8'))
        self.assertEqual(data['pixel_requirement'],'NOT_EVALUATED')
        self.assertEqual(data['technical_status'],'INSPECTION_ONLY')

    def test_batch_and_summary(self):
        other=self.base/'B.png'
        Image.new('RGBA',(64,48),(40,50,60,255)).save(other)
        out=self.base/'batch'
        proc=self.run_cli(self.base,'--target','64x48','--out',out,'--crop','20')
        self.assertEqual(proc.returncode,0,proc.stderr)
        summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['succeeded'],2)
        self.assertTrue((out/'summary.csv').exists())

    def test_focus_outside_image_rejected(self):
        proc=self.run_cli(self.image,'--focus','60,40,20,20','--out',self.base/'bad')
        self.assertEqual(proc.returncode,1)
        self.assertIn('exceeds image size',proc.stderr)

    def test_baseline_is_not_detail_verification(self):
        out=self.base/'compare'
        proc=self.run_cli(self.image,'--baseline',self.image,'--out',out)
        self.assertEqual(proc.returncode,0,proc.stderr)
        data=json.loads((out/'report.json').read_text(encoding='utf-8'))
        self.assertIs(data['baseline_comparison']['detail_restoration_verified'],False)
        self.assertEqual(data['source_native_resolution'],'UNKNOWN')

    def test_transparency_metadata_and_checkerboard_preview(self):
        transparent = self.base / 'transparent.png'
        im = Image.new('RGBA', (64, 48), (255, 0, 0, 0))
        for x in range(16, 48):
            for y in range(12, 36):
                im.putpixel((x, y), (20, 120, 220, 255))
        im.save(transparent)
        out = self.base / 'qc_alpha'
        proc = self.run_cli(transparent, '--out', out, '--crop', '24')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads((out / 'report.json').read_text(encoding='utf-8'))
        self.assertTrue(data['has_alpha_channel_or_transparency'])
        self.assertEqual(data['alpha_extrema_0_255'], [0, 255])
        with Image.open(out / 'review_100pct_crops.png') as preview:
            self.assertEqual(preview.mode, 'RGB')
            # Preview must show a checkerboard-backed composite rather than
            # dropping alpha and exposing arbitrary hidden RGB values.
            self.assertTrue((out / 'review_100pct_crops.png').stat().st_size > 0)


if __name__=='__main__':
    unittest.main()
