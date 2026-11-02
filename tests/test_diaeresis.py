import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from fontTools.ttLib import TTFont
import accents
from app import app

ROOT=Path(__file__).resolve().parents[1]

def image(dots=True):
    im=Image.new('RGB',(256,256),'white');d=ImageDraw.Draw(im)
    d.ellipse((50,90,100,140),fill='black')
    if dots:d.ellipse((150,90,200,140),fill='black')
    out=io.BytesIO();im.save(out,format='PNG');return out.getvalue()

class Diaeresis(unittest.TestCase):
    def setUp(self):self.client=app.test_client()
    def post(self,path,font,**fields):
        return self.client.post(path,data={'font':(io.BytesIO(font),'test.ttf'),**fields},content_type='multipart/form-data')
    def test_export_preserves_base_and_removes_i_dot(self):
        for name in ['KoolBeans-eerm.ttf','AbrilFatface-Regular.ttf','MechanicalBold-oOmA.otf']:
            with self.subTest(name=name):
                data=(ROOT/'testFonts'/name).read_bytes();original=TTFont(io.BytesIO(data))
                for ch,base in accents.BASES.items():
                    if ch == 'ñ': continue  # A tilde is one mark, not two dots.
                    result=self.post('/api/export',data,method='accent',character=ch)
                    self.assertEqual(result.status_code,200,result.json)
                    generated=TTFont(io.BytesIO(result.data));g=generated.getBestCmap()[ord(ch)];base_name=original.getBestCmap()[ord(base)]
                    self.assertEqual(generated['hmtx'][g][0],original['hmtx'][base_name][0])
                    old=accents.contours(original,base_name)
                    if base=='i':_,old=accents.split_top(old)
                    new=accents.contours(generated,g)
                    self.assertGreaterEqual(len(new),len(old)+2)
                    for a,b in zip(old,new):self.assertEqual(a.value,b.value)
    def test_ai_generation_and_bad_mark(self):
        data=(ROOT/'testFonts'/'KoolBeans-eerm.ttf').read_bytes()
        with patch('app.generate_image',return_value=image()):
            result=self.post('/api/generate',data,method='accent-ai',character='ö')
            self.assertEqual(result.status_code,200,result.json)
            result=self.post('/api/export',data,method='accent-ai',character='ö',image=(io.BytesIO(image()),'mark.png'))
            self.assertEqual(result.status_code,200,result.json)
            self.assertEqual(result.headers['X-Accent-Source'],'AI-generated diaeresis')
        with patch('app.generate_image',return_value=image(False)):
            result=self.post('/api/generate',data,method='accent-ai',character='ö')
            self.assertEqual(result.status_code,400)
    def test_unusable_i_is_rejected(self):
        data=(ROOT/'testFonts'/'ostrich-regular.ttf').read_bytes()
        result=self.post('/api/export',data,method='accent',character='ï')
        self.assertEqual(result.status_code,400)
        self.assertIn('separable',result.json['error'])
    def test_pair_kerning_matches_base(self):
        hb='/opt/homebrew/bin/hb-shape'
        if not Path(hb).exists():self.skipTest('HarfBuzz CLI is unavailable')
        data=(ROOT/'testFonts'/'AbrilFatface-Regular.ttf').read_bytes()
        response=self.post('/api/export',data,method='accent',character='ö')
        self.assertEqual(response.status_code,200,response.json)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.ttf') as trial:
            trial.write(response.data);trial.flush()
            def shape(path,text):
                result=json.loads(subprocess.check_output([hb,str(path),text,'--output-format=json','--features=-liga,-clig'],text=True))
                return [(x['dx'],x['dy'],x['ax'],x['ay']) for x in result]
            for before,after in [('To','Tö'),('oV','öV'),('Yo','Yö'),('oT','öT')]:
                self.assertEqual(shape(ROOT/'testFonts'/'AbrilFatface-Regular.ttf',before),shape(trial.name,after))

if __name__=='__main__':unittest.main()
