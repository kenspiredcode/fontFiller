from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
FONTS=[('Abril Fatface','AbrilFatface-Regular.ttf',True),('Kool Beans','KoolBeans-eerm.ttf',False),('Allura','Allura-Regular.ttf',True)]

def crop_glyph(font, char):
    im=Image.new('L',(1000,1000),255); d=ImageDraw.Draw(im); d.text((200,100),char,font=font,fill=0)
    box=ImageOps.invert(im).getbbox()
    return im.crop(box) if box else None

def fit(im, w, h):
    im=im.copy(); im.thumbnail((w,h),Image.Resampling.LANCZOS); return im

def make():
    page=Image.new('RGB',(1600,1050),'white'); d=ImageDraw.Draw(page)
    label=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',24)
    small=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',18)
    for i,s in enumerate(['Base e','Apostrophe reuse','AI edit','AI mark + original','Original é']): d.text((220+i*270,20),s,font=small,fill='black')
    for row,(name,file,has_reference) in enumerate(FONTS):
        y=75+row*320; f=ImageFont.truetype(str(ROOT/'testFonts'/file),500)
        base=crop_glyph(f,'e'); mark=crop_glyph(f,"'").rotate(-35,expand=True,fillcolor=255)
        # A fixed proportional starting point, without font-specific tuning.
        b=fit(base,190,180); mark=fit(mark,85,62)
        d.text((15,y+110),name,font=label,fill='black')
        def put(img,col,top): page.paste(ImageOps.colorize(img,'black','white'),(220+col*270+(210-img.width)//2,top))
        put(b,0,y+100)
        put(b,1,y+100); put(mark,1,y+100-mark.height-18)
        ai=OUT/(Path(file).stem+'-ai.png')
        if ai.exists():
            im=Image.open(ai).convert('L')
            mask=im.point(lambda x: 255 if x < 180 else 0)
            rows=[yy for yy in range(mask.height) if mask.crop((0,yy,mask.width,yy+1)).getbbox()]
            runs=[]
            for yy in rows:
                if not runs or yy>runs[-1][-1]+1: runs.append([])
                runs[-1].append(yy)
            if len(runs)>=2:
                accent_box=mask.crop((0,runs[0][0],mask.width,runs[0][-1]+1)).getbbox()
                a=im.crop((accent_box[0],runs[0][0],accent_box[2],runs[0][-1]+1))
                base_start=runs[-1][0]; scale=b.height/len(runs[-1])
                a=a.resize((max(1,round(a.width*scale)),max(1,round(a.height*scale))),Image.Resampling.LANCZOS)
                gap=round((base_start-runs[0][-1]-1)*scale)
                ai_base_box=mask.crop((0,base_start,mask.width,runs[-1][-1]+1)).getbbox()
                ai_base=im.crop((ai_base_box[0],base_start,ai_base_box[2],runs[-1][-1]+1))
                ai_base=ai_base.resize((round(ai_base.width*scale),b.height),Image.Resampling.LANCZOS)
                put(ai_base,2,y+100); put(a,2,y+100-gap-a.height)
                put(b,3,y+100); put(a,3,y+100-gap-a.height)
        if has_reference:
            original=crop_glyph(f,'é'); put(fit(original,200,260),4,y+20)
        else: d.text((220+4*270,y+110),'not in font',font=small,fill='gray')
    page.save(OUT/'pilot-comparison.png')
if __name__=='__main__': make()
