from pathlib import Path
import math, statistics, io
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
import compare, slant, dot_check

ROOT=compare.ROOT; OUT=Path(__file__).resolve().parent
FONTS=sorted((ROOT/'testFonts').glob('*.ttf'))+sorted((ROOT/'testFonts').glob('*.otf'))

def glyph_image(tt,name):
    # Map the outline temporarily to a private-use character so Pillow renders
    # the raw mark rather than applying combining-mark shaping or fallback.
    for table in tt['cmap'].tables:
        if table.isUnicode(): table.cmap[0xE000]=name
    data=io.BytesIO();tt.save(data);data.seek(0)
    f=ImageFont.truetype(data,500); im=Image.new('L',(1800,1800),255)
    ImageDraw.Draw(im).text((700,600),chr(0xE000),font=f,fill=0)
    box=ImageOps.invert(im).getbbox()
    return im.crop(box) if box else None

def two_blobs(im):
    arr=np.asarray(im)<160; columns=np.flatnonzero(arr.any(axis=0));groups=[]
    for x in columns:
        if not groups or x>groups[-1][-1]+1:groups.append([])
        groups[-1].append(x)
    return len(groups)==2 and min(map(len,groups))>=2

def existing(tt,f):
    cmap=tt.getBestCmap()
    # Direct marks first, including spacing and combining encodings.
    for code in [0x0308,0x00A8]:
        name=cmap.get(code)
        if name:
            im=glyph_image(tt,name)
            if im and two_blobs(im):return im, f'U+{code:04X}'
    # Then a diaeresis taken from a different precomposed character.
    for char in 'äëüïÄËÜÏ':
        if ord(char) not in cmap:continue
        im=Image.new('L',(1800,1800),255);ImageDraw.Draw(im).text((350,250),char,font=f,fill=0)
        a=np.asarray(im)<160;ys=np.where(a.any(axis=1))[0];runs=[]
        for y in ys:
            if not runs or y>runs[-1][-1]+1:runs.append([])
            runs[-1].append(y)
        if len(runs)<2:continue
        segment=im.crop((0,runs[0][0],im.width,runs[0][-1]+1));box=ImageOps.invert(segment).getbbox()
        if box:
            mark=segment.crop(box)
            if two_blobs(mark):return mark, char
    return None,None

def dot(f,c):
    im=Image.new('L',(1800,1800),255);ImageDraw.Draw(im).text((350,250),c,font=f,fill=0)
    a=np.asarray(im)<160;ys=np.where(a.any(axis=1))[0];runs=[]
    for y in ys:
        if not runs or y>runs[-1][-1]+1:runs.append([])
        runs[-1].append(y)
    if len(runs)!=2:return None
    segment=im.crop((0,runs[0][0],im.width,runs[0][-1]+1));box=ImageOps.invert(segment).getbbox()
    return segment.crop(box) if box else None

def main():
    label=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',21);small=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',16)
    pages=[]; rows=[]
    for idx,file in enumerate(FONTS):
        if idx%5==0:
            page=Image.new('RGB',(1600,1580),'white');pages.append(page);d=ImageDraw.Draw(page)
            for x,s in [(325,'Original o'),(575,'1. Existing diaeresis'),(880,'2. i/j dot pair'),(1190,'Font’s own ö')]:d.text((x,15),s,font=small,fill='black')
        top=60+(idx%5)*300;tt=TTFont(file);f=ImageFont.truetype(str(file),500);cmap=tt.getBestCmap()
        d.text((12,top+93),file.stem[:23],font=label,fill='black')
        if ord('o') not in cmap:
            d.text((320,top+100),'No lowercase o in font',font=small,fill='gray');rows.append((file.name,'no o'));continue
        base=compare.glyph(f,'o'); factor=min(165/base.height,200/base.width); b=compare.scale(base,factor)
        def put(im,cx,y):page.paste(ImageOps.colorize(im,'black','white'),(round(cx-im.width/2),round(y)))
        for cx in [400,675,975]:put(b,cx,top+100)
        slope,_=slant.estimate(f); measured,agreement=dot_check.dot_measurements(f)
        def place(mark,cx):
            gap=max(5,round((agreement[1] if agreement else .10)*b.height))
            # Dot-to-stem offsets are unreliable when a dot sits over just one
            # part of a broad serif or hook. Use them only if a separately
            # measured slant corroborates their direction.
            dot_offset = agreement[0] if agreement else 0
            if slope is None or abs(slope)<.05 or dot_offset*slope<=0:
                dot_offset = 0
            shift=(slope or 0)*b.height*.5+(dot_offset*b.height if dot_offset else (slope or 0)*(gap+mark.height*.5))
            shift=max(-b.width*.25,min(b.width*.25,shift));put(mark,cx+shift,top+100-gap-mark.height)
        found,src=existing(tt,f)
        if found:
            mark=compare.scale(found,min(b.width*.63/found.width,b.height*.27/found.height))
            place(mark,675);d.text((575,top+5),'source: '+src,font=small,fill='gray')
        else:d.text((575,top+55),'no reliable source',font=small,fill='gray')
        which=next((c for c in 'ij' if ord(c) in cmap and dot(f,c) is not None),None)
        if which:
            raw=dot(f,which); one=compare.scale(raw,factor)
            one=compare.scale(one,min(1,b.width*.25/one.width,b.height*.20/one.height))
            gap=max(3,round(b.width*.12));pair=Image.new('L',(2*one.width+gap,one.height),255);pair.paste(one,(0,0));pair.paste(one,(one.width+gap,0));place(pair,975)
            d.text((880,top+5),'source: '+which,font=small,fill='gray')
        else:d.text((880,top+55),'no isolated dot',font=small,fill='gray')
        if ord('ö') in cmap:
            original=compare.glyph(f,'ö')
            def box(ch):
                im=Image.new('L',(1800,1800),255);ImageDraw.Draw(im).text((350,250),ch,font=f,fill=0);return ImageOps.invert(im).getbbox()
            bb=box('o');ob=box('ö');offset=((ob[0]+ob[2])-(bb[0]+bb[2]))*.5*factor
            put(compare.scale(original,factor),1290+offset,top+100+(ob[1]-bb[1])*factor)
        else:d.text((1190,top+90),'not in font',font=small,fill='gray')
        rows.append((file.name,src or '-',which or '-', 'yes' if ord('ö') in cmap else 'no'))
    for n,p in enumerate(pages,1):p.save(OUT/f'diaeresis-survey-{n}.png')
    for row in rows: print('\t'.join(row))
if __name__=='__main__':main()
