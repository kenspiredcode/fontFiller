from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from fontTools.ttLib import TTFont

ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).resolve().parent
CASES=[('abril','Abril Fatface','AbrilFatface-Regular.ttf','a','à','`'),('allura','Allura','Allura-Regular.ttf','n','ñ','~'),('kool','Kool Beans','KoolBeans-eerm.ttf','o','ö','.'),('mono','Monofonto','monofonto.ttf','a','à','`'),('ostrich','Ostrich','ostrich-regular.ttf','o','ö','.'),('cameo','Cameo Antique','Cameoantique-VLPw.ttf','e','é',"'")]

def ink(im): return ImageOps.invert(im).getbbox()
def glyph(font,char):
    im=Image.new('L',(1800,1800),255); ImageDraw.Draw(im).text((350,250),char,font=font,fill=0)
    box=ink(im); return im.crop(box) if box else None

def scale(im, factor): return im.resize((max(1,round(im.width*factor)),max(1,round(im.height*factor))),Image.Resampling.LANCZOS)
def get_ai_mark(path, target_height):
    im=Image.open(path).convert('L'); mask=im.point(lambda x:255 if x<180 else 0)
    rows=[y for y in range(mask.height) if mask.crop((0,y,mask.width,y+1)).getbbox()]
    runs=[]
    for y in rows:
        if not runs or y>runs[-1][-1]+1: runs.append([])
        runs[-1].append(y)
    if len(runs)<2: return None,0
    y0,y1=runs[0][0],runs[0][-1]+1
    box=mask.crop((0,y0,mask.width,y1)).getbbox(); mark=im.crop((box[0],y0,box[2],y1))
    factor=target_height/len(runs[-1]); gap=round((runs[-1][0]-y1)*factor)
    return scale(mark,factor),gap

def main():
    page=Image.new('RGB',(1500,2020),'white'); d=ImageDraw.Draw(page)
    label=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',25)
    small=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',19)
    for x,s in [(295,'Original base'),(570,'Punctuation reuse'),(865,'AI accent + original'),(1190,'Font’s own glyph')]: d.text((x,20),s,font=small,fill='black')
    for row,(key,name,file,basechar,target,source) in enumerate(CASES):
        top=65+row*320; f=ImageFont.truetype(str(ROOT/'testFonts'/file),500)
        base=glyph(f,basechar); factor=min(180/base.height,210/base.width); b=scale(base,factor)
        mark=glyph(f,source)
        if source=="'": mark=mark.rotate(-35,expand=True,fillcolor=255)
        if source=='.':
            dot=scale(mark,min(38/mark.width,38/mark.height)); mark=Image.new('L',(dot.width*2+18,dot.height),255);mark.paste(dot,(0,0));mark.paste(dot,(dot.width+18,0))
        else: mark=scale(mark,min(90/mark.width,55/mark.height))
        d.text((15,top+110),name,font=label,fill='black');d.text((15,top+145),f'{basechar} to {target}   source: {source}',font=small,fill='black')
        def put(im,cx,y): page.paste(ImageOps.colorize(im,'black','white'),(round(cx-im.width/2),round(y)))
        for cx in [355,650,950]: put(b,cx,top+105)
        put(mark,650,top+105-mark.height-18)
        ai=OUT/(key+'-ai.png')
        if ai.exists():
            a,gap=get_ai_mark(ai,b.height)
            if a: put(a,950,top+105-a.height-gap)
            else: d.text((865,top+65),'could not isolate mark',font=small,fill='gray')
        else: d.text((865,top+65),'AI result unavailable',font=small,fill='gray')
        tt=TTFont(ROOT/'testFonts'/file)
        if ord(target) in tt.getBestCmap():
            original=glyph(f,target)
            if original: put(scale(original,factor),1280,top+105+base.height*factor-original.height*factor)
        else: d.text((1190,top+120),'not in font',font=small,fill='gray')
    page.save(OUT/'comparison.png')
if __name__=='__main__': main()
