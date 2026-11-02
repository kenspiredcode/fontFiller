import io
import unittest
from pathlib import Path
from unittest.mock import patch
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from PIL import Image, ImageDraw, ImageFont
import app

ROOT=Path(__file__).resolve().parents[1]
CASES=['UtAyonahDemoRegular-xRA55.otf','MechanicalBold-oOmA.otf','Dknanuk-q6G6.otf','ostrich-regular.ttf']

def drawing(font, name):
    pen=RecordingPen();font.getGlyphSet()[name].draw(pen);return pen.value

class FontFormats(unittest.TestCase):
    def test_upload_generation_and_export(self):
        client=app.app.test_client()
        image=(ROOT/'experiment/fal/ostrich-gpt.png').read_bytes()
        for filename in CASES:
            with self.subTest(font=filename):
                source=(ROOT/'testFonts'/filename).read_bytes()
                original=TTFont(io.BytesIO(source))
                upload=client.post('/api/font',data={'font':(io.BytesIO(source),filename)})
                self.assertEqual(upload.status_code,200,upload.json)
                with patch('app.generate_image',return_value=image):
                    generated=client.post('/api/generate',data={'font':(io.BytesIO(source),filename),'character':'&'})
                self.assertEqual(generated.status_code,200,generated.json)
                exported=client.post('/api/export',data={'font':(io.BytesIO(source),filename),'character':'&','image':(io.BytesIO(image),'glyph.png')})
                self.assertEqual(exported.status_code,200,exported.json)
                is_cff='CFF ' in original
                self.assertEqual(exported.mimetype,'font/otf' if is_cff else 'font/ttf')
                self.assertIn('.otf' if is_cff else '.ttf', exported.headers['Content-Disposition'])
                result=TTFont(io.BytesIO(exported.data)); cmap=result.getBestCmap()
                self.assertTrue(cmap[ord('&')].startswith('fontFiller_'))
                self.assertTrue(app.has_outline(result,cmap[ord('&')]))
                for char in 'AHO':
                    before=original.getBestCmap().get(ord(char)); after=cmap.get(ord(char))
                    if before and before != '.notdef':
                        self.assertEqual(before,after)
                        self.assertEqual(drawing(original,before),drawing(result,after))
                        self.assertEqual(original['hmtx'][before],result['hmtx'][after])
                self.assertEqual(original['name'].getDebugName(0),result['name'].getDebugName(0))
                if is_cff:
                    self.assertEqual(result['CFF '].cff.fontNames[0],result['name'].getDebugName(6))
                rendered=Image.new('L',(900,200),255)
                ImageDraw.Draw(rendered).text((20,15),'ART & DESIGN',font=ImageFont.truetype(io.BytesIO(exported.data),100),fill=0)
                self.assertIsNotNone(rendered.getbbox())

    def test_bad_fonts_are_rejected(self):
        client=app.app.test_client()
        for name in ('fake.ttf','fake.otf'):
            r=client.post('/api/font',data={'font':(io.BytesIO(b'not a font'),name)})
            self.assertEqual(r.status_code,400)

if __name__=='__main__':unittest.main()
