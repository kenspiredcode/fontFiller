import io
import unittest
from pathlib import Path
from fontTools.ttLib import TTFont
import accents

ROOT=Path(__file__).resolve().parents[1]

class AccentPlacement(unittest.TestCase):
    def font(self,name):
        data=(ROOT/'testFonts'/name).read_bytes()
        return data,TTFont(io.BytesIO(data))
    def mark_box(self,data,font,ch):
        base=accents.contours(font,font.getBestCmap()[ord(accents.BASES[ch])])
        if accents.BASES[ch] in 'ij':_,base=accents.split_top(base)
        data,_,_=accents.build(font,data,ch)
        result=TTFont(io.BytesIO(data));glyph=accents.contours(result,result.getBestCmap()[ord(ch)])
        return accents.bounds(glyph[len(base):]),accents.bounds(base)
    def test_script_accents_follow_font_references(self):
        data,font=self.font('AlexBrush-Regular.ttf')
        self.assertEqual(accents.estimate_slant(data,font),0)
        self.assertGreater(accents.reference_shift(font,'â'),.12)
        mark,base=self.mark_box(data,font,'â')
        self.assertGreater((mark[0]+mark[2])/2,(base[0]+base[2])/2+(base[2]-base[0])*.12)
    def test_circumflex_and_ring_have_family_specific_size(self):
        for ch in 'âå':
            with self.subTest(ch=ch):
                data,font=self.font('AbhayaLibre-Regular.ttf');mark,base=self.mark_box(data,font,ch)
                self.assertGreater((mark[3]-mark[1])/(base[3]-base[1]),.30)
    def test_d_dot_is_above_bowl_beside_ascender(self):
        data,font=self.font('AbhayaLibre-Regular.ttf');mark,base=self.mark_box(data,font,'ḋ')
        self.assertLess(mark[3],base[3]+10)
        self.assertLess((mark[0]+mark[2])/2,(base[0]+base[2])/2)
