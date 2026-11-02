import io
import unittest
from pathlib import Path
from unittest.mock import patch

from fontTools.ttLib import TTFont
import app

ROOT = Path(__file__).resolve().parents[1]

class ExtendedCharacters(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def upload(self, name):
        return (ROOT / 'testFonts' / name).read_bytes()

    def test_coverage_includes_new_groups(self):
        data = self.upload('ostrich-regular.ttf')
        response = self.client.post('/api/font', data={'font': (io.BytesIO(data), 'font.ttf')})
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(set(result['present'] + result['missing']), set(app.SYMBOLS))
        self.assertEqual(set(result['flippable']), {'¿', '¡'})

    def test_flipped_outline_in_ttf_and_cff_without_generation(self):
        for name in ('ostrich-regular.ttf', 'MechanicalBold-oOmA.otf'):
            data = self.upload(name)
            source = TTFont(io.BytesIO(data))
            for char, upright in app.FLIP_SOURCES.items():
                with self.subTest(font=name, char=char), patch('app.generate_image', side_effect=AssertionError('unexpected AI call')):
                    response = self.client.post('/api/export', data={'font': (io.BytesIO(data), name), 'character': char, 'method': 'flip'})
                    self.assertEqual(response.status_code, 200, response.get_json())
                    result = TTFont(io.BytesIO(response.data))
                    before = app.glyph_bounds(source, source.getBestCmap()[ord(upright)])
                    after = app.glyph_bounds(result, result.getBestCmap()[ord(char)])
                    self.assertAlmostEqual(before[2]-before[0], after[2]-after[0], delta=2)
                    self.assertAlmostEqual(before[3]-before[1], after[3]-after[1], delta=2)
                    self.assertLess(after[1], 0)

    def test_flip_rejects_missing_source_and_unrelated_character(self):
        data = self.upload('UtAyonahDemoRegular-xRA55.otf')
        for char in ('¿', 'A'):
            response = self.client.post('/api/export', data={'font': (io.BytesIO(data), 'font.otf'), 'character': char, 'method': 'flip'})
            self.assertEqual(response.status_code, 400)

    def test_small_marks_start_smaller_and_higher(self):
        data = self.upload('ostrich-regular.ttf')
        # A square outline gives a predictable comparison independent of tracing.
        with patch('app.trace_path', return_value='M 0 0 L 100 0 L 100 100 L 0 100 Z'):
            large = TTFont(io.BytesIO(app.build_font(data, b'', '€')))
            small = TTFont(io.BytesIO(app.build_font(data, b'', '°')))
        lb = app.glyph_bounds(large, large.getBestCmap()[ord('€')])
        sb = app.glyph_bounds(small, small.getBestCmap()[ord('°')])
        self.assertLess(sb[3]-sb[1], (lb[3]-lb[1]) * .5)
        self.assertGreater(sb[1], lb[1])

if __name__ == '__main__':
    unittest.main()
