from pathlib import Path
import math, statistics
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
import compare, placement

OUT=Path(__file__).resolve().parent
CASES=[('Kool Beans','KoolBeans-eerm.ttf','o','ö','.'),('Perfect Signature','Perfectsignature.ttf','a','à','`'),('Allura','Allura-Regular.ttf','n','ñ','~'),('Abril Fatface','AbrilFatface-Regular.ttf','a','à','`'),('Ostrich','ostrich-regular.ttf','o','ö','.')]

def estimate(font):
    measurements=[]
    for char in 'Il1':
        image=Image.new('L',(1400,1400),255);ImageDraw.Draw(image).text((400,300),char,font=font,fill=0)
        ink=np.asarray(image)<128; ys=np.where(ink.any(axis=1))[0]; runs=[]
        for y in ys:
            if not runs or y>runs[-1][-1]+1:runs.append([])
            runs[-1].append(y)
        if not runs:continue
        run=max(runs,key=len);rows=[]
        for y in run[int(len(run)*.2):int(len(run)*.8)]:
            xs=np.flatnonzero(ink[y]);rows.append((y,(int(xs[0])+int(xs[-1]))/2,len(xs)))
        if len(rows)<8:continue
        p=np.array(rows);slope,intercept=np.polyfit(p[:,0],p[:,1],1)
        err=np.sqrt(np.mean((p[:,1]-(slope*p[:,0]+intercept))**2))/max(1,np.median(p[:,2]))
        if err<=.12:measurements.append((char,-float(slope),float(err)))
    best=[]
    for item in measurements:
        cluster=[v for v in measurements if abs(v[1]-item[1])<=.12]
        if len(cluster)>len(best):best=cluster
    return (statistics.median(v[1] for v in best),best) if len(best)>=2 else (None,best)

def main():
    page=Image.new('RGB',(1400,1690),'white'); d=ImageDraw.Draw(page)
    label=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',24);small=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',18)
    for x,s in [(340,'Geometric center'),(650,'Slant-aware'),(1000,'Font’s own glyph')]:d.text((x,20),s,font=small,fill='black')
    for row,(name,file,basechar,target,source) in enumerate(CASES):
        top=65+row*320; font=ImageFont.truetype(str(compare.ROOT/'testFonts'/file),500)
        base=compare.glyph(font,basechar);factor=min(180/base.height,210/base.width);b=compare.scale(base,factor)
        mark,gap=placement.mark_for(source,compare.glyph(font,source),b.width,b.height,True)
        slope,accepted=estimate(font)
        shift=0 if slope is None else max(-b.width*.25,min(b.width*.25,slope*(b.height*.5+gap+mark.height*.5)))
        d.text((15,top+105),name,font=label,fill='black')
        msg='low confidence: no shift' if slope is None else f'{math.degrees(math.atan(slope)):+.1f} deg; shift {shift:+.0f}px'
        d.text((15,top+140),msg,font=small,fill='black')
        d.text((15,top+165),'accepted: '+(', '.join(x[0] for x in accepted) or 'none'),font=small,fill='gray')
        def put(im,cx,y):page.paste(ImageOps.colorize(im,'black','white'),(round(cx-im.width/2),round(y)))
        for cx in [430,740]:put(b,cx,top+105)
        put(mark,430,top+105-gap-mark.height);put(mark,740+shift,top+105-gap-mark.height)
        from fontTools.ttLib import TTFont
        if ord(target) in TTFont(compare.ROOT/'testFonts'/file).getBestCmap():
            original=compare.glyph(font,target)
            def original_box(ch):
                im=Image.new('L',(1800,1800),255); ImageDraw.Draw(im).text((350,250),ch,font=font,fill=0)
                return ImageOps.invert(im).getbbox()
            bb=original_box(basechar); ob=original_box(target)
            offset=((ob[0]+ob[2])-(bb[0]+bb[2]))*.5*factor
            put(compare.scale(original,factor),1080+offset,top+105+(ob[1]-bb[1])*factor)
        else:d.text((1000,top+120),'not in font',font=small,fill='gray')
        print(name,msg,' '.join(f'{c}={v:.3f} err={e:.3f}' for c,v,e in accepted))
    page.save(OUT/'slant-comparison.png')
if __name__=='__main__':main()
