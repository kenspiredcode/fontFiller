import io
import unittest
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
import accents
import app

ROOT = Path(__file__).resolve().parents[1]

class ReuseTests(unittest.TestCase):
    def test_punctuation_exports_in_both_outline_formats(self):
        for filename in ('AbhayaLibre-Regular.ttf', 'MechanicalBold-oOmA.otf'):
            data = (ROOT / 'testFonts' / filename).read_bytes()
            font = app.read_font(data)
            for char in app.REUSE_SOURCES:
                if not app.reusable(font, char): continue
                with self.subTest(font=filename, char=char):
                    result = app.read_font(app.build_font(data, None, char, reuse=True))
                    self.assertTrue(app.has_outline(result, result.getBestCmap().get(ord(char))))
                    if char in '…÷':
                        self.assertGreaterEqual(len(accents.contours(result, result.getBestCmap()[ord(char)])), 3)

    def test_double_quotes_rotate_and_guillemets_overlap(self):
        font = app.read_font((ROOT / 'testFonts/AbhayaLibre-Regular.ttf').read_bytes())
        cmap = font.getBestCmap(); glyphs = font.getGlyphSet()
        for char, source in (('“','”'), ('”','“')):
            bounds = app.glyph_bounds(font, cmap[ord(source)])
            x0, y0, x1, y1 = bounds
            expected = DecomposingRecordingPen(glyphs)
            glyphs[cmap[ord(source)]].draw(TransformPen(expected, (-1, 0, 0, -1, x1, y0+y1)))
            actual = app.reuse_outline(font, char, 700, 0)
            self.assertEqual(actual.value, expected.value)
        for char, source in (('«','<'), ('»','>')):
            x0, _, x1, _ = app.glyph_bounds(font, cmap[ord(source)])
            from fontTools.pens.boundsPen import BoundsPen
            pen = BoundsPen(glyphs); app.reuse_outline(font, char, 700, 0).replay(pen)
            self.assertAlmostEqual(pen.bounds[2] - pen.bounds[0], (x1-x0)*.8*1.7)

    def test_api_reports_and_exports_reuse(self):
        data = (ROOT / 'testFonts/AbhayaLibre-Regular.ttf').read_bytes()
        client = app.app.test_client()
        def upload(**fields):
            return {'font': (io.BytesIO(data), 'font.ttf'), **fields}
        info = client.post('/api/font', data=upload(), content_type='multipart/form-data')
        self.assertIn('…', info.json['reusable'])
        result = client.post('/api/export', data=upload(character='…', method='reuse'), content_type='multipart/form-data')
        self.assertEqual(result.status_code, 200)
        font = app.read_font(result.data)
        self.assertTrue(app.has_outline(font, font.getBestCmap().get(ord('…'))))

    def test_reuse_requires_all_sources(self):
        data = (ROOT / 'testFonts/AbhayaLibre-Regular.ttf').read_bytes()
        font = TTFont(io.BytesIO(data))
        for table in font['cmap'].tables:
            if table.isUnicode(): table.cmap.pop(ord('.'), None)
        self.assertFalse(app.reusable(font, '÷'))
        self.assertFalse(app.reusable(font, '…'))

    def test_accent_fallbacks(self):
        data = (ROOT / 'testFonts/AbhayaLibre-Regular.ttf').read_bytes()
        font = TTFont(io.BytesIO(data))
        # Remove every competing accent and accented letter, leaving basic sources.
        remove = set(''.join(accents.FAMILY_CHARS[f] for f in ('dot above','macron','caron','ring')))
        remove.update(ch for f in ('dot above','macron','caron','ring') for ch in accents.MARKS[f])
        for table in font['cmap'].tables:
            if table.isUnicode():
                for ch in remove: table.cmap.pop(ord(ch), None)
        for char, expected in (('ċ','period'), ('ū','hyphen'), ('š','flipped circumflex'), ('å','lowercase o')):
            with self.subTest(char=char):
                self.assertEqual(accents.sources(font, char)[1], expected)

if __name__ == '__main__': unittest.main()
