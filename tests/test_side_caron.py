import io
import unittest
from pathlib import Path
from fontTools.ttLib import TTFont
import accents
from app import app
from test_bulk import without

ROOT=Path(__file__).resolve().parents[1]

class SideCaronTests(unittest.TestCase):
    def test_export_preserves_base_and_reuses_side_mark(self):
        data=(ROOT/'testFonts/AbhayaLibre-Regular.ttf').read_bytes()
        client=app.test_client()
        for char,base in zip('ďľť','dlt'):
            with self.subTest(char=char):
                missing=without(data,char)
                response=client.post('/api/export',data={'font':(io.BytesIO(missing),'font.ttf'), 'character':char,'method':'accent'},content_type='multipart/form-data')
                self.assertEqual(response.status_code,200,response.json)
                self.assertEqual(response.headers['X-Accent-Source'],'existing side caron')
                original=TTFont(io.BytesIO(missing)); result=TTFont(io.BytesIO(response.data))
                before=accents.contours(original,original.getBestCmap()[ord(base)])
                after=accents.contours(result,result.getBestCmap()[ord(char)])
                self.assertEqual([c.value for c in after[:len(before)]],[c.value for c in before])
                self.assertGreater(len(after),len(before))
                self.assertEqual(result['hmtx'][result.getBestCmap()[ord(char)]][0],original['hmtx'][original.getBestCmap()[ord(base)]][0])
    def test_fallback_and_script_style(self):
        data=(ROOT/'testFonts/ostrich-regular.ttf').read_bytes()
        self.assertEqual(accents.sources(TTFont(io.BytesIO(data)),'ď')[1],'right quote')
        data=(ROOT/'testFonts/AlexBrush-Regular.ttf').read_bytes()
        font=TTFont(io.BytesIO(data)); base=accents.bounds(accents.contours(font,font.getBestCmap()[ord('d')]))
        out,source,_=accents.build(font,data,'ď')
        result=TTFont(io.BytesIO(out)); glyph=accents.contours(result,result.getBestCmap()[ord('ď')]); n=len(accents.contours(font,font.getBestCmap()[ord('d')]))
        self.assertEqual(source,'existing side caron')
        self.assertGreater(accents.bounds(glyph[n:])[1],base[3])
