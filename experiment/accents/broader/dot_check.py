from pathlib import Path
import statistics
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from fontTools.ttLib import TTFont
import compare, placement, slant

OUT=Path(__file__).resolve().parent

def dot_measurements(font):
    results=[]
    x=compare.glyph(font,'x')
    if not x:return results,None
    xheight=x.height
    for char in 'ij':
        im=Image.new('L',(1400,1400),255);ImageDraw.Draw(im).text((400,300),char,font=font,fill=0)
        ink=np.asarray(im)<128;ys=np.where(ink.any(axis=1))[0];runs=[]
        for y in ys:
            if not runs or y>runs[-1][-1]+1:runs.append([])
            runs[-1].append(y)
        if len(runs)!=2:continue
        dot,stem=runs
        if len(dot)>.75*xheight or len(stem)<.5*xheight:continue
        xs=np.flatnonzero(ink[dot[0]:dot[-1]+1].any(axis=0))
        if len(xs)==0:continue
        dotcenter=(int(xs[0])+int(xs[-1]))/2
        centers=[]
        for y in stem[:max(1,round(min(len(stem),xheight)*.15))]:
            pixels=np.flatnonzero(ink[y]);centers.append((int(pixels[0])+int(pixels[-1]))/2)
        offset=(dotcenter-statistics.median(centers))/xheight
        gap=(stem[0]-dot[-1]-1)/xheight
        results.append((char,offset,gap))
    if len(results)<2:return results,None
    a,b=results
    if abs(a[1]-b[1])>.12 or abs(a[2]-b[2])>.10:return results,None
    return results,(statistics.median(v[1] for v in results),statistics.median(v[2] for v in results))

def main():
    page=Image.new('RGB',(1600,1690),'white');d=ImageDraw.Draw(page)
    label=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',23);small=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',18)
    for x,s in [(350,'Geometric center'),(650,'Stem-based slant'),(960,'Stem + i/j dots'),(1280,'Font’s own glyph')]:d.text((x,20),s,font=small,fill='black')
    for row,(name,file,basechar,target,source) in enumerate(slant.CASES):
        top=65+row*320;f=ImageFont.truetype(str(compare.ROOT/'testFonts'/file),500)
        base=compare.glyph(f,basechar);factor=min(180/base.height,210/base.width);b=compare.scale(base,factor)
        mark,gap=placement.mark_for(source,compare.glyph(f,source),b.width,b.height,True)
        slope,_=slant.estimate(f); measured,agreed=dot_measurements(f)
        prior=0 if slope is None else max(-b.width*.25,min(b.width*.25,slope*(b.height*.5+gap+mark.height*.5)))
        if agreed is None: shift,newgap=prior,gap
        else:
            # Dot displacement is relative to the top of its stem. Translate from
            # the target's mid-height center to its top using the stem slope.
            shift=(slope or 0)*b.height*.5+agreed[0]*b.height
            shift=max(-b.width*.25,min(b.width*.25,shift))
            newgap=max(4,min(b.height*.3,agreed[1]*b.height))
        d.text((15,top+100),name,font=label,fill='black')
        info='dots disagree / unavailable' if agreed is None else f'i/j: offset {agreed[0]*100:+.0f}%, gap {agreed[1]*100:.0f}%'
        d.text((15,top+135),info,font=small,fill='black')
        d.text((15,top+160),'fallback to stem placement' if agreed is None else f'shift {shift:+.0f}px; gap {newgap:.0f}px',font=small,fill='gray')
        def put(im,cx,y):page.paste(ImageOps.colorize(im,'black','white'),(round(cx-im.width/2),round(y)))
        for cx in [420,730,1040]:put(b,cx,top+105)
        for cx,dx,g in [(420,0,gap),(730,prior,gap),(1040,shift,newgap)]:put(mark,cx+dx,top+105-g-mark.height)
        if ord(target) in TTFont(compare.ROOT/'testFonts'/file).getBestCmap():
            original=compare.glyph(f,target)
            def box(ch):
                im=Image.new('L',(1800,1800),255);ImageDraw.Draw(im).text((350,250),ch,font=f,fill=0);return ImageOps.invert(im).getbbox()
            bb=box(basechar); ob=box(target); offset=((ob[0]+ob[2])-(bb[0]+bb[2]))*.5*factor
            put(compare.scale(original,factor),1370+offset,top+105+(ob[1]-bb[1])*factor)
        else:d.text((1280,top+120),'not in font',font=small,fill='gray')
        print(name,' '.join(f'{c}:offset={off:.3f} gap={g:.3f}' for c,off,g in measured),'accepted',agreed)
    page.save(OUT/'dot-comparison.png')
if __name__=='__main__':main()
