import io
import unittest
from pathlib import Path
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
from app import app
import accents

ROOT=Path(__file__).resolve().parents[1]

def square(x0,y0,x1,y1,reverse=False):
    points=[(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
    if reverse: points.reverse()
    p=RecordingPen();p.moveTo(points[0])
    for pt in points[1:]:p.lineTo(pt)
    p.closePath();return p

class AttachmentTests(unittest.TestCase):
    def test_every_supported_character_has_explicit_behavior(self):
        self.assertEqual(set(accents.FAMILIES.values()),set(accents.FAMILY_ATTACHMENT))
        for char in accents.BASES:
            self.assertIn(accents.attachment_kind(char),('floating','attached'))
        for char in 'ķļņŗģḋďḍș':self.assertEqual(accents.attachment_kind(char),'floating')
        for char in 'çşţąęįų':self.assertEqual(accents.attachment_kind(char),'attached')
    def test_ink_check_uses_outlines_and_respects_holes(self):
        ring=[square(0,0,200,200),square(40,40,160,160,True)]
        self.assertFalse(accents.outline_contact(ring,[square(60,60,120,120)],1000))
        self.assertTrue(accents.outline_contact(ring,[square(20,20,70,70)],1000))
        self.assertFalse(accents.outline_contact([square(0,0,100,100)],[square(120,0,160,50)],1000))
    def test_manual_overlap_reports_warning_and_can_be_corrected(self):
        data=(ROOT/'testFonts/AbhayaLibre-Regular.ttf').read_bytes();client=app.test_client()
        def export(**fields):
            return client.post('/api/export',data={'font':(io.BytesIO(data),'font.ttf'),'character':'é','method':'accent',**fields},content_type='multipart/form-data')
        result=export(offset='-0.3');self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.headers['X-Accent-Collision'],'1')
        result=export();self.assertEqual(result.headers['X-Accent-Collision'],'0')
    def test_bounded_nudge_corrects_two_kinds_of_warning(self):
        base=[square(0,0,300,300)]
        floating=[square(150,270,190,330)]
        delta=accents.nudge_attachment(base,floating,1000,'floating','above')
        self.assertIsNotNone(delta);self.assertGreater(delta[1],0)
        self.assertLessEqual((delta[0]**2+delta[1]**2)**.5,120.01)
        attached=[square(130,-120,170,-16)]
        delta=accents.nudge_attachment(base,attached,1000,'attached','below')
        self.assertIsNotNone(delta);self.assertGreater(delta[1],0)
        self.assertIsNone(accents.nudge_attachment([square(0,0,1000,1000)],[square(400,400,600,600)],1000,'floating','above'))
    def test_font_nudges_and_manual_adjustments(self):
        for filename,char,problem in [('AlexBrush-Regular.ttf','ç','unattached'),
                                      ('Dknanuk-q6G6.otf','ď','collision')]:
            with self.subTest(font=filename):
                data=(ROOT/'testFonts'/filename).read_bytes()
                _,_,before=accents.build(TTFont(io.BytesIO(data)),data,char,return_checks=True,auto_nudge=False)
                self.assertTrue(before[problem])
                output,_,after=accents.build(TTFont(io.BytesIO(data)),data,char,return_checks=True)
                self.assertTrue(after['nudged']);self.assertFalse(after[problem])
                moved,_,manual=accents.build(TTFont(io.BytesIO(data)),data,char,offset=.01,return_checks=True)
                self.assertTrue(manual['nudged'])
                original=TTFont(io.BytesIO(data)); base=accents.contours(original,original.getBestCmap()[ord(accents.BASES[char])])
                first=TTFont(io.BytesIO(output)); second=TTFont(io.BytesIO(moved))
                mark1=accents.contours(first,first.getBestCmap()[ord(char)])[len(base):]
                mark2=accents.contours(second,second.getBestCmap()[ord(char)])[len(base):]
                self.assertAlmostEqual(accents.bounds(mark2)[1]-accents.bounds(mark1)[1],original['head'].unitsPerEm*.01,delta=1.5)
    def test_export_reports_auto_nudge(self):
        data=(ROOT/'testFonts/AlexBrush-Regular.ttf').read_bytes()
        result=app.test_client().post('/api/export',data={'font':(io.BytesIO(data),'font.ttf'),'character':'ç','method':'accent'},content_type='multipart/form-data')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.headers['X-Accent-Nudged'],'1')
        self.assertEqual(result.headers['X-Accent-Unattached'],'0')

    def test_detached_cedilla_warning(self):
        data=(ROOT/'testFonts/AbhayaLibre-Regular.ttf').read_bytes();client=app.test_client()
        result=client.post('/api/export',data={'font':(io.BytesIO(data),'font.ttf'),'character':'ç','method':'accent','offset':'-0.3'},content_type='multipart/form-data')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.headers['X-Accent-Unattached'],'1')
