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

    def test_workspace_refresh_reports_newly_added_glyphs(self):
        data=without(self.original,'éñ')
        first=self.client.post('/api/export',data=self.upload(data,character='é',method='accent'),content_type='multipart/form-data')
        self.assertEqual(first.status_code,200,first.json)
        info=self.client.post('/api/font',data=self.upload(first.data,workspace='1'),content_type='multipart/form-data')
        self.assertEqual(info.status_code,200,info.json)
        self.assertNotIn('é',info.json['missing']);self.assertIn('ñ',info.json['missing'])
        self.assertIn('mark_groups',info.json)
        second=self.client.post('/api/export',data=self.upload(first.data,character='ñ',method='accent'),content_type='multipart/form-data')
        self.assertEqual(second.status_code,200,second.json)
        font=app.read_font(second.data)
        self.assertTrue(all(app.has_outline(font,font.getBestCmap().get(ord(ch))) for ch in 'éñ'))

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

    def test_one_reviewed_mark_builds_multiple_letters(self):
        data=without(self.original, 'áé')
        image=Image.new('RGB',(100,100),'white'); ImageDraw.Draw(image).rectangle((35,25,60,70),fill='black')
        out=io.BytesIO(); image.save(out,'PNG')
        with patch.object(app.accents,'sources',side_effect=ValueError('missing mark')):
            groups=app.missing_mark_groups(data)
            self.assertIn('á',groups['acute']); self.assertIn('é',groups['acute'])
            representative=groups['acute'][0]
            with patch.object(app,'trace_path',return_value='M 0 0 L 20 0 L 20 40 L 0 40 Z'):
                result=self.client.post('/api/bulk/apply-marks',data=self.upload(data,characters=representative,images=(io.BytesIO(out.getvalue()),'mark.png')),content_type='multipart/form-data')
        self.assertEqual(result.status_code,200,result.json)
        self.assertTrue({'á','é'}.issubset(result.json['added']))
        font=app.read_font(base64.b64decode(result.json['font']))
        for ch in 'áé': self.assertTrue(app.has_outline(font,font.getBestCmap()[ord(ch)]))

    def test_mark_grid_uses_lowercase_specimen(self):
        data=without(self.original,'á')
        image=Image.new('RGB',(90,90),'white'); ImageDraw.Draw(image).rectangle((20,20,40,40),fill='black')
        out=io.BytesIO(); image.save(out,'PNG')
        response={'images':[{'url':'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()}]}
        class FakeResponse(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self,*args): self.close()
        with patch.dict(os.environ,{'FAL_KEY':'test'}), patch.object(app,'missing_mark_groups',return_value={'acute':['á']}), patch.object(app,'specimen',return_value=b'lowercase-reference') as reference, patch.object(app,'reserve_generation'), patch.object(app,'urlopen',return_value=FakeResponse(json.dumps(response).encode())):
            result=self.client.post('/api/bulk/generate',data=self.upload(data,characters='á',grid='3',kind='marks'),content_type='multipart/form-data')
        self.assertEqual(result.status_code,200,result.json)
        reference.assert_called_once_with(data,lowercase=True)

    def test_mark_grid_rejects_nonrepresentative_before_charging(self):
        with patch.object(app,'reserve_generation') as reserve:
            result=self.client.post('/api/bulk/generate',data=self.upload(without(self.original,'@'),characters='@',grid='3',kind='marks'),content_type='multipart/form-data')
        self.assertEqual(result.status_code,400); reserve.assert_not_called()

    def test_generation_rejects_present_character_before_charging(self):
        with patch.object(app,'reserve_generation') as reserve:
            result=self.client.post('/api/bulk/generate',data=self.upload(self.original,characters='A',grid='4'),content_type='multipart/form-data')
        self.assertEqual(result.status_code,400);reserve.assert_not_called()

if __name__=='__main__':unittest.main()
