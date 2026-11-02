from pathlib import Path
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
import build_trial as b

OUT=Path(__file__).resolve().parent

def check():
    for title,file in b.CASES:
        orig=TTFont(b.ROOT/'testFonts'/file);font=TTFont(OUT/('trial-'+file));o=orig.getBestCmap();c=font.getBestCmap()
        for target,base in b.CHARS.items():
            name=c[ord(target)]; assert name.startswith('experiment_')
            assert font['hmtx'][name][0]==orig['hmtx'][o[ord(base)]][0]
            old=b.contours(orig,o[ord(base)]);new=b.contours(font,name)
            if base=='i':dot,old=b.split_dot(old);assert len(new)>=len(old)+2
            assert len(new)>=len(old)
            for a,z in zip(old,new):
                assert len(a.value)==len(z.value)
                for (op,args),(op2,args2) in zip(a.value,z.value):
                    assert op==op2
                    for p,q in zip(args,args2):
                        if p is None:assert q is None
                        else:assert all(abs(x-y)<.06 for x,y in zip(p,q))
        ys=[b.bounds(b.contours(font,c[ord(ch)]))[3] for ch in b.CHARS]
        h=font['hhea'];os=font['OS/2'];print(title,'all bases and advances verified; max y',round(max(ys)),'hhea ascent',h.ascent,'win ascent',os.usWinAscent)
    for file in ['Cameoantique-VLPw.ttf','ostrich-regular.ttf','Pazea-2v4Wd.ttf']:
        font=TTFont(b.ROOT/'testFonts'/file)
        try:print(file,'source:',b.source_mark(font)[1])
        except ValueError as e:print(file,'safe failure:',str(e))

def sheet():
    im=Image.new('RGB',(1800,1900),'white');d=ImageDraw.Draw(im)
    label=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',26);small=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',20)
    d.text((30,20),'Exported font trials — rendered from the generated TTF / OTF files',font=label,fill='black')
    for row,(title,file) in enumerate(b.CASES):
        y=70+row*600;trial=ImageFont.truetype(str(OUT/('trial-'+file)),85);orig=ImageFont.truetype(str(b.ROOT/'testFonts'/file),85)
        context=ImageFont.truetype(str(OUT/('trial-'+file)),65)
        d.text((30,y),title+'   '+('TTF' if file.endswith('.ttf') else 'CFF OTF'),font=label,fill='black')
        d.text((30,y+42),'Trial glyphs',font=small,fill='gray');d.text((30,y+65),'ä  ë  ï  ö  ü',font=trial,fill='black')
        if title!='Kool Beans':
            d.text((900,y+42),'Font designer’s original glyphs',font=small,fill='gray');d.text((900,y+65),'ä  ë  ï  ö  ü',font=orig,fill='black')
        d.text((30,y+210),'Trial glyphs in words',font=small,fill='gray')
        d.text((30,y+240),'naïve     Noël     über     möbel     süd',font=context,fill='black')
        d.text((30,y+355),'Two lines in Pillow',font=small,fill='gray')
        d.multiline_text((30,y+385),'naïve möbel\nüber süd',font=context,fill='black',spacing=4)
    im.save(OUT/'export-specimens.png')
if __name__=='__main__':check();sheet()
