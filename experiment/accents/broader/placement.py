from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from fontTools.ttLib import TTFont
import compare

OUT=Path(__file__).resolve().parent

def bounded_scale(im, width, height):
    return compare.scale(im,min(width/im.width,height/im.height))

def mark_for(source, raw, base_width, base_height, revised):
    if source=="'": raw=raw.rotate(-35,expand=True,fillcolor=255)
    if not revised:
        if source=='.':
            dot=bounded_scale(raw,38,38); mark=Image.new('L',(2*dot.width+18,dot.height),255); mark.paste(dot,(0,0)); mark.paste(dot,(dot.width+18,0)); return mark,18
        return bounded_scale(raw,90,55),18
    if source=='.':
        # The two equal dots and their gap collectively span 55% of the visible base width.
        # Cap dot height so short, wide glyphs don't get oversized marks.
        dot=bounded_scale(raw,base_width*.22,base_height*.19)
        gap=max(1,round(base_width*.11))
        mark=Image.new('L',(2*dot.width+gap,dot.height),255)
        mark.paste(dot,(0,0));mark.paste(dot,(dot.width+gap,0))
    elif source=='~':
        mark=bounded_scale(raw,base_width*.52,base_height*.20)
    else:
        # The full punctuation silhouette is preserved; fit rather than stretch.
        mark=bounded_scale(raw,base_width*.42,base_height*.40)
    return mark,max(8,round(base_height*.10))

def main():
    page=Image.new('RGB',(1500,2020),'white');d=ImageDraw.Draw(page)
    label=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',25);small=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',19)
    for x,s in [(295,'Base letter'),(570,'Earlier placement'),(865,'Proportional rules'),(1190,'Font’s own glyph')]:d.text((x,20),s,font=small,fill='black')
    for row,(key,name,file,basechar,target,source) in enumerate(compare.CASES):
        top=65+row*320; f=ImageFont.truetype(str(compare.ROOT/'testFonts'/file),500)
        base=compare.glyph(f,basechar); factor=min(180/base.height,210/base.width); b=compare.scale(base,factor)
        raw=compare.glyph(f,source)
        d.text((15,top+110),name,font=label,fill='black');d.text((15,top+145),f'{basechar} to {target}   source: {source}',font=small,fill='black')
        def put(im,cx,y):page.paste(ImageOps.colorize(im,'black','white'),(round(cx-im.width/2),round(y)))
        for cx in [355,650,950]: put(b,cx,top+105)
        for cx,revised in [(650,False),(950,True)]:
            mark,gap=mark_for(source,raw,b.width,b.height,revised); put(mark,cx,top+105-mark.height-gap)
        tt=TTFont(compare.ROOT/'testFonts'/file)
        if ord(target) in tt.getBestCmap():
            original=compare.glyph(f,target)
            if original:put(compare.scale(original,factor),1280,top+105+b.height-original.height*factor)
        else:d.text((1190,top+120),'not in font',font=small,fill='gray')
    page.save(OUT/'placement-comparison.png')
if __name__=='__main__':main()
