import base64
import io
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from fontTools.ttLib import TTFont
import accents
from app import app
from test_bulk import without

ROOT=Path(__file__).resolve().parents[1]

class BelowAccents(unittest.TestCase):
    def setUp(self):
        self.data=(ROOT/'testFonts/AbhayaLibre-Regular.ttf').read_bytes()
        self.client=app.test_client()
    def post(self,path,data,**fields):
        return self.client.post(path,data={'font':(io.BytesIO(data),'test.ttf'),**fields},content_type='multipart/form-data')
    def test_marks_place_at_or_below_the_base(self):
        for char in 'çķąęįųḍșț':
            with self.subTest(char=char):
                response=self.post('/api/export',self.data,method='accent',character=char)
                self.assertEqual(response.status_code,200,response.json)
                old=TTFont(io.BytesIO(self.data));new=TTFont(io.BytesIO(response.data))
                base=accents.contours(old,old.getBestCmap()[ord(accents.BASES[char])])
                glyph=accents.contours(new,new.getBestCmap()[ord(char)])
                self.assertEqual([x.value for x in glyph[:len(base)]],[x.value for x in base])
                self.assertGreater(len(glyph),len(base))
                bb=accents.bounds(base);mb=accents.bounds(glyph[len(base):])
                self.assertLess(mb[1],bb[1])
                if char in 'ķļņŗḍșț': self.assertLess(mb[3],bb[1])
                self.assertEqual(new['hmtx'][new.getBestCmap()[ord(char)]][0],old['hmtx'][old.getBestCmap()[ord(accents.BASES[char])]][0])
    def test_latvian_marks_are_detached_in_true_type_and_cff(self):
        for name in ('AbhayaLibre-Regular.ttf', 'MechanicalBold-oOmA.otf'):
            data=(ROOT/'testFonts'/name).read_bytes()
            for char in 'ķļņŗ':
                with self.subTest(font=name, char=char):
                    original=TTFont(io.BytesIO(data))
                    base=accents.contours(original,original.getBestCmap()[ord(accents.BASES[char])])
                    result,_,_=accents.build(original,data,char)
                    generated=TTFont(io.BytesIO(result))
                    glyph=accents.contours(generated,generated.getBestCmap()[ord(char)])
                    self.assertGreater(len(glyph),len(base))
                    self.assertLess(accents.bounds(glyph[len(base):])[3],accents.bounds(base)[1])

    def test_g_cedilla_is_above_and_base_descender_is_preserved(self):
        old=TTFont(io.BytesIO(self.data))
        result,source,_=accents.build(old,self.data,'ģ')
        self.assertEqual(source,'existing g cedilla')
        new=TTFont(io.BytesIO(result));base=accents.contours(old,old.getBestCmap()[ord('g')]);glyph=accents.contours(new,new.getBestCmap()[ord('ģ')])
        self.assertEqual([x.value for x in glyph[:len(base)]],[x.value for x in base])
        self.assertGreater(accents.bounds(glyph[len(base):])[1],accents.bounds(base)[3])
    def test_bulk_builds_missing_below_marks(self):
        data=without(self.data,'çąḍș')
        result=self.post('/api/bulk/prepare',data)
        self.assertEqual(result.status_code,200,result.json)
        self.assertTrue(set('çąḍș').issubset(result.json['added']))
        font=TTFont(io.BytesIO(base64.b64decode(result.json['font'])))
        self.assertTrue(all(ord(c) in font.getBestCmap() for c in 'çąḍș'))
    def test_ai_accent_keeps_i_dot(self):
        im=Image.new('RGB',(128,128),'white');ImageDraw.Draw(im).rectangle((40,35,70,90),fill='black')
        out=io.BytesIO();im.save(out,'PNG')
        original=TTFont(io.BytesIO(self.data));base=accents.contours(original,original.getBestCmap()[ord('i')])
        result,_,_=accents.build(original,self.data,'į',image_data=out.getvalue(),trace=lambda _: 'M 0 0 L 20 0 L 20 40 L 0 40 Z')
        font=TTFont(io.BytesIO(result));glyph=accents.contours(font,font.getBestCmap()[ord('į')])
        self.assertEqual([x.value for x in glyph[:len(base)]],[x.value for x in base])
