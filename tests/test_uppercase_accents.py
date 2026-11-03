import base64
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from fontTools.ttLib import TTFont
import accents
import app
from test_bulk import without

ROOT = Path(__file__).resolve().parents[1]


class UppercaseAccents(unittest.TestCase):
    def test_coverage_and_special_mark_classes(self):
        for char in list(accents.BASES):
            self.assertIn(char.upper(), accents.BASES)
        self.assertEqual(accents.BASES['Í'], 'I')
        self.assertEqual(accents.attachment_kind('Ģ'), 'attached')
        self.assertEqual(accents.attachment_kind('Ķ'), 'floating')
        self.assertNotIn('Ď', accents.SIDE_CARONS)
        self.assertIn('Ľ', accents.SIDE_CARONS)

    def test_capitals_preserve_base_and_metrics_in_ttf_and_cff(self):
        for filename in ('AbhayaLibre-Regular.ttf', 'MechanicalBold-oOmA.otf'):
            data = (ROOT/'testFonts'/filename).read_bytes()
            for char in 'ÀÂÄÉÍĢĎĽĶĄ':
                with self.subTest(font=filename, char=char):
                    original = TTFont(io.BytesIO(data)); cmap = original.getBestCmap()
                    base_name = cmap[ord(accents.BASES[char])]
                    base = accents.contours(original, base_name)
                    output, _, _ = accents.build(original, data, char, return_checks=True)
                    result = TTFont(io.BytesIO(output)); name = result.getBestCmap()[ord(char)]
                    outlines = accents.contours(result, name)
                    self.assertEqual(result['hmtx'][name][0], original['hmtx'][base_name][0])
                    self.assertEqual([c.value for c in outlines[:len(base)]], [c.value for c in base])
                    self.assertGreater(len(outlines), len(base))
                    glyph_bounds = accents.bounds(outlines)
                    self.assertGreaterEqual(result['OS/2'].usWinAscent, glyph_bounds[3])
                    self.assertGreaterEqual(result['OS/2'].usWinDescent, -glyph_bounds[1])
                    if char == 'Ģ':
                        self.assertLess(accents.bounds(outlines[len(base):])[1], accents.bounds(base)[1])
                    if char == 'Ď':
                        self.assertGreater(accents.bounds(outlines[len(base):])[1], accents.bounds(base)[3])

    def test_capital_inherits_base_kerning(self):
        hb = Path('/opt/homebrew/bin/hb-shape')
        if not hb.exists(): self.skipTest('HarfBuzz CLI is unavailable')
        path = ROOT/'testFonts/AbrilFatface-Regular.ttf'; data = path.read_bytes()
        output, _, _ = accents.build(TTFont(io.BytesIO(data)), data, 'Á')
        def shape(font, text):
            result = json.loads(subprocess.check_output([str(hb), str(font), text, '--output-format=json', '--features=-liga,-clig'], text=True))
            return [(item['dx'], item['dy'], item['ax'], item['ay']) for item in result]
        with tempfile.NamedTemporaryFile(suffix='.ttf') as trial:
            trial.write(output); trial.flush()
            for original, accented in [('VA', 'VÁ'), ('AV', 'ÁV')]:
                self.assertEqual(shape(path, original), shape(trial.name, accented))

    def test_one_generated_mark_applies_to_both_cases(self):
        data = without((ROOT/'testFonts/AbhayaLibre-Regular.ttf').read_bytes(), 'éÉ')
        image = Image.new('L', (100,100), 255); ImageDraw.Draw(image).rectangle((30,20,60,70), fill=0)
        out = io.BytesIO(); image.save(out, 'PNG')
        with patch.object(app, 'missing_characters', return_value=['é', 'É']), patch.object(accents, 'sources', side_effect=ValueError('missing mark')):
            groups = app.missing_mark_groups(data)
            self.assertEqual(groups['acute'], ['é', 'É'])
            with patch.object(app, 'trace_path', return_value='M 0 0 L 20 0 L 20 40 L 0 40 Z'):
                response = app.app.test_client().post('/api/bulk/apply-marks', data={
                    'font': (io.BytesIO(data), 'font.ttf'), 'characters': 'é',
                    'images': (io.BytesIO(out.getvalue()), 'mark.png')}, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['added'], ['é', 'É'])
        result = TTFont(io.BytesIO(base64.b64decode(response.json['font'])))
        self.assertTrue(all(ord(ch) in result.getBestCmap() for ch in 'éÉ'))


if __name__ == '__main__': unittest.main()
