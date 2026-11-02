from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from PIL import ImageFont
import sys, math
ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'experiment/accents/broader'))
import slant
from kerning import inherit_kerning
CASES=[('Kool Beans','KoolBeans-eerm.ttf'),('Abril Fatface','AbrilFatface-Regular.ttf'),('Mechanical Bold','MechanicalBold-oOmA.otf')]
CHARS={'ä':'a','ë':'e','ï':'i','ö':'o','ü':'u'}

def contours(font,name):
    glyphs=font.getGlyphSet();p=DecomposingRecordingPen(glyphs);glyphs[name].draw(p)
    chunks=[];current=None
    for op,args in p.value:
        if op=='moveTo' or (op=='qCurveTo' and current is None):current=RecordingPen()
        if current is None:raise ValueError('Unexpected glyph contour')
        current.value.append((op,args))
        if op in ('closePath','endPath'):chunks.append(current);current=None
    return chunks

def bounds(items):
    p=BoundsPen(None)
    for c in items:c.replay(p)
    return p.bounds

def split_dot(items):
    # Accept only contours wholly above the body with a visible vertical gap.
    ordered=sorted(items,key=lambda c:bounds([c])[3],reverse=True)
    for i in range(1,len(ordered)):
        dots,body=ordered[:i],ordered[i:]; db=bounds(dots); bb=bounds(body)
        if db[1]>bb[3] and (db[1]-bb[3])>0:
            if db[3]-db[1] < (bb[3]-bb[1])*.75:return dots,body
    raise ValueError('No safely separable i dot')

def source_mark(font):
    cmap=font.getBestCmap()
    for ch in ['\u0308','\u00a8']:
        if ord(ch) in cmap:
            items=contours(font,cmap[ord(ch)])
            if items and bounds(items):return items, 'existing '+hex(ord(ch))
    if ord('i') in cmap:
        dot,_=split_dot(contours(font,cmap[ord('i')]))
        return dot,'i dot pair'
    raise ValueError('No trustworthy source mark')

def add_glyph(font,char,basechar,mark,method,slope):
    font.getGlyphOrder()  # Materialize before mutating the CFF charset.
    cmap=font.getBestCmap();base_name=cmap.get(ord(basechar))
    if not base_name:raise ValueError('Missing base '+basechar)
    base=contours(font,base_name)
    if basechar=='i':_,base=split_dot(base)
    bx0,by0,bx1,by1=bounds(base);bh=by1-by0;bw=bx1-bx0
    mx0,my0,mx1,my1=bounds(mark);mw=mx1-mx0;mh=my1-my0
    # Prefer a whole existing mark; otherwise duplicate the original i dot.
    if method=='i dot pair':
        desired=min(bw*.24,bh*.19); sf=min(desired/mw,bh*.19/mh); dotw=mw*sf; dotgap=bw*.12; pairw=2*dotw+dotgap
    else:
        sf=min(bw*(1.0 if basechar=='i' else .63)/mw,bh*.27/mh);pairw=mw*sf
    gap=bh*.10; shift=max(-bw*.25,min(bw*.25,slope*(bh*.5+gap+mh*sf*.5)))
    left=(bx0+bx1-pairw)/2+shift; bottom=by1+gap
    advance,lsb=font['hmtx'][base_name];name='experiment_%04X'%ord(char)
    def draw(pen):
        for c in base:c.replay(pen)
        def render(x):
            target=TransformPen(pen,(sf,0,0,sf,x-mx0*sf,bottom-my0*sf))
            for c in mark:c.replay(target)
        render(left)
        if method=='i dot pair':render(left+dotw+dotgap)
    if 'glyf' in font:
        pen=TTGlyphPen(font.getGlyphSet());draw(pen);font.setGlyphOrder(font.getGlyphOrder()+[name]);font['glyf'][name]=pen.glyph()
    else:
        top=font['CFF '].cff.topDictIndex[0];private=top.Private
        width=None if advance==private.defaultWidthX else advance-private.nominalWidthX
        pen=T2CharStringPen(width,None,roundTolerance=0);draw(pen);cs=pen.getCharString(private=private,globalSubrs=font['CFF '].cff.GlobalSubrs)
        chars=top.CharStrings
        if chars.charStringsAreIndexed:chars.charStrings[name]=len(chars.charStringsIndex);chars.charStringsIndex.append(cs)
        else:chars[name]=cs
        order=list(font.getGlyphOrder());top.charset.append(name);font.setGlyphOrder(order+[name])
    font['hmtx'][name]=(advance,lsb)
    for table in font['cmap'].tables:
        if table.isUnicode():table.cmap[ord(char)]=name
    return name

def main():
    for title,filename in CASES:
        font=TTFont(ROOT/'testFonts'/filename);mark,method=source_mark(font)
        s,_=slant.estimate(ImageFont.truetype(str(ROOT/'testFonts'/filename),500));s=s or 0
        aliases={}
        for ch,base in CHARS.items():
            try:
                new=add_glyph(font,ch,base,mark,method,s)
                aliases[new]=font.getBestCmap()[ord(base)]
            except ValueError as e: print(title,ch,'SKIPPED',str(e))
        inherit_kerning(font,aliases)
        out=OUT/('trial-'+filename);font.save(out);reopened=TTFont(out)
        for ch,base in CHARS.items():
            name=reopened.getBestCmap().get(ord(ch))
            if name and name.startswith('experiment_'):
                assert reopened['hmtx'][name][0]==reopened['hmtx'][reopened.getBestCmap()[ord(base)]][0]
        print(title,method,'slope',round(s,3),'saved',out.name)
if __name__=='__main__':main()
