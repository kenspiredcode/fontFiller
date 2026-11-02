import base64
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

import accents
from app import app
from test_bulk import without

ROOT = Path(__file__).resolve().parents[1]


class AcuteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def post(self, path, font, **fields):
        return self.client.post(path, data={'font': (io.BytesIO(font), 'test.ttf'), **fields},
                                content_type='multipart/form-data')

    def test_export_acute_family_preserves_base_and_metrics(self):
        for filename in ('AbhayaLibre-Regular.ttf', 'MechanicalBold-oOmA.otf'):
            data = (ROOT / 'testFonts' / filename).read_bytes()
            original = TTFont(io.BytesIO(data))
            for char, base in accents.ACUTE_BASES.items():
                with self.subTest(font=filename, char=char):
                    response = self.post('/api/export', data, method='accent', character=char)
                    self.assertEqual(response.status_code, 200, response.json)
                    result = TTFont(io.BytesIO(response.data))
                    base_name = original.getBestCmap()[ord(base)]
                    glyph = result.getBestCmap()[ord(char)]
                    self.assertEqual(result['hmtx'][glyph][0], original['hmtx'][base_name][0])
                    before = accents.contours(original, base_name)
                    if base == 'i': _, before = accents.split_top(before)
                    after = accents.contours(result, glyph)
                    self.assertGreater(len(after), len(before))
                    self.assertEqual([x.value for x in after[:len(before)]], [x.value for x in before])

    def test_missing_acutes_are_built_in_bulk(self):
        data = without((ROOT / 'testFonts/AbhayaLibre-Regular.ttf').read_bytes(), 'éí')
        response = self.post('/api/bulk/prepare', data)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue({'é', 'í'}.issubset(response.json['added']))
        font = TTFont(io.BytesIO(base64.b64decode(response.json['font'])))
        self.assertTrue(all(ord(c) in font.getBestCmap() for c in 'éí'))

    def test_fallback_prefers_mirrored_grave_then_rotates_apostrophe(self):
        for filename, expected in (('KoolBeans-eerm.ttf', 'mirrored grave accent'),
                                   ('ostrich-regular.ttf', 'rotated apostrophe')):
            with self.subTest(font=filename):
                data = (ROOT / 'testFonts' / filename).read_bytes()
                font = TTFont(io.BytesIO(data))
                mark, source, _ = accents.sources(font, 'é')
                self.assertEqual(source, expected)
                x0, y0, x1, y1 = accents.bounds(mark)
                self.assertGreater(x1-x0, 0)
                self.assertGreater(y1-y0, 0)
                response = self.post('/api/export', data, method='accent', character='é')
                self.assertEqual(response.status_code, 200, response.json)
                self.assertEqual(response.headers['X-Accent-Source'], expected)

    def test_round_mark_is_not_used_as_acute(self):
        from fontTools.pens.recordingPen import RecordingPen
        circle = RecordingPen()
        circle.moveTo((0, 50)); circle.lineTo((50, 0)); circle.lineTo((100, 50))
        circle.lineTo((50, 100)); circle.closePath()
        self.assertIsNone(accents.orient_acute([circle]))

    def test_ai_acute_accepts_one_mark_and_rejects_two(self):
        data = (ROOT / 'testFonts/AbhayaLibre-Regular.ttf').read_bytes()
        def image(two=False):
            im = Image.new('RGB', (256, 256), 'white')
            draw = ImageDraw.Draw(im)
            draw.polygon([(50, 150), (70, 150), (130, 80), (110, 80)], fill='black')
            if two: draw.rectangle((180, 90, 200, 140), fill='black')
            out = io.BytesIO(); im.save(out, 'PNG'); return out.getvalue()
        with patch('app.generate_image', return_value=image()), patch('app.trace_path', return_value='M 0 0 L 20 0 L 40 40 L 20 40 Z'):
            response = self.post('/api/generate', data, method='accent-ai', character='é')
            self.assertEqual(response.status_code, 200, response.json)
        with patch('app.generate_image', return_value=image(True)):
            response = self.post('/api/generate', data, method='accent-ai', character='é')
            self.assertEqual(response.status_code, 400)

class MarkFamilyTests(unittest.TestCase):
    def test_each_family_builds_from_font_outlines(self):
        data = (ROOT / 'testFonts/AbhayaLibre-Regular.ttf').read_bytes()
        for family, char in [('grave', 'à'), ('circumflex', 'â'), ('tilde', 'ã'),
                             ('diaeresis', 'ä'), ('ring', 'å'), ('macron', 'ā'),
                             ('breve', 'ă'), ('caron', 'ǎ'), ('dot above', 'ċ'),
                             ('double acute', 'ő')]:
            with self.subTest(family=family):
                original = TTFont(io.BytesIO(data))
                result, _, _ = accents.build(original, data, char)
                font = TTFont(io.BytesIO(result))
                cmap = font.getBestCmap()
                base = accents.contours(font, cmap[ord(accents.BASES[char])])
                built = accents.contours(font, cmap[ord(char)])
                self.assertGreater(len(built), len(base))
                self.assertGreater(accents.bounds(built[len(base):])[1], accents.bounds(base)[3])
