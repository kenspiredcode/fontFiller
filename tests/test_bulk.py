import base64
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw
import app

ROOT=Path(__file__).resolve().parents[1]


def without(data, chars):
    font=TTFont(io.BytesIO(data))
    for table in font['cmap'].tables:
        if table.isUnicode():
            for char in chars: table.cmap.pop(ord(char), None)
    out=io.BytesIO();font.save(out);return out.getvalue()


class BulkTests(unittest.TestCase):
    def setUp(self):
        self.client=app.app.test_client()
        self.original=(ROOT/'testFonts/AbhayaLibre-Regular.ttf').read_bytes()

    def upload(self, data, **fields):
        return {'font':(io.BytesIO(data),'test.ttf'), **fields}

    def test_prepare_builds_missing_flip_and_tilde_without_overwriting(self):
        data=without(self.original,'¿ñ')
        result=self.client.post('/api/bulk/prepare',data=self.upload(data),content_type='multipart/form-data')
        self.assertEqual(result.status_code,200,result.json)
        result=result.json; self.assertIn('¿',result['added']); self.assertIn('ñ',result['added'])
        font=app.read_font(base64.b64decode(result['font'])); cmap=font.getBestCmap()
        self.assertTrue(app.has_outline(font,cmap[ord('ñ')]))
        self.assertNotIn('ñ',result['remaining'])
        self.assertFalse((font['name'].getDebugName(1) or '').endswith(' Font Filler Font Filler'))

    def test_prepare_supports_cff_and_preserves_existing_glyphs(self):
        source=(ROOT/'testFonts/MechanicalBold-oOmA.otf').read_bytes()
        data=without(source,'¿ñ')
        result=self.client.post('/api/bulk/prepare', data={'font':(io.BytesIO(data),'test.otf')}, content_type='multipart/form-data')
        self.assertEqual(result.status_code,200,result.json)
        self.assertIn('¿',result.json['added']); self.assertIn('ñ',result.json['added'])
        font=app.read_font(base64.b64decode(result.json['font']))
        self.assertIn('CFF ',font)
        for char in 'A¿ñ': self.assertTrue(app.has_outline(font,font.getBestCmap()[ord(char)]))

    def test_generate_and_apply_reviewed_only(self):
        data=without(self.original,'@#$')
        image=Image.new('RGB',(300,300),'white'); draw=ImageDraw.Draw(image)
        for i in range(3): draw.rectangle((i*100+35,35,i*100+60,65),fill='black')
        out=io.BytesIO();image.save(out,'PNG')
        response={'images':[{'url':'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()}]}
        class FakeResponse(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self,*args): self.close()
        with patch.dict(os.environ,{'FAL_KEY':'test'}), patch.object(app,'reserve_generation') as reserve, patch.object(app,'urlopen',return_value=FakeResponse(json.dumps(response).encode())):
            generated=self.client.post('/api/bulk/generate',data=self.upload(data,characters='@#$',grid='3'),content_type='multipart/form-data')
        self.assertEqual(generated.status_code,200,generated.json);reserve.assert_called_once()
        crops=generated.json['crops'];self.assertEqual([x['character'] for x in crops],list('@#$'))
        image_data=base64.b64decode(crops[0]['image'].split(',')[1])
        applied=self.client.post('/api/bulk/apply',data=self.upload(data,characters='@',images=(io.BytesIO(image_data),'glyph.png')),content_type='multipart/form-data')
        self.assertEqual(applied.status_code,200,applied.json)
        self.assertEqual(applied.json['added'],['@']);self.assertIn('#',applied.json['remaining'])
        font=app.read_font(base64.b64decode(applied.json['font']));self.assertTrue(app.has_outline(font,font.getBestCmap()[ord('@')]))

    def test_generation_rejects_present_character_before_charging(self):
        with patch.object(app,'reserve_generation') as reserve:
            result=self.client.post('/api/bulk/generate',data=self.upload(self.original,characters='A',grid='4'),content_type='multipart/form-data')
        self.assertEqual(result.status_code,400);reserve.assert_not_called()

if __name__=='__main__':unittest.main()
