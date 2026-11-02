from pathlib import Path
import re, subprocess, tempfile
from PIL import Image
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import parse_path

ROOT=Path(__file__).resolve().parents[2]
CASES=[('ostrich','ostrich-regular.ttf','ostrich-isolated-ampersand.png','&'),('kool','KoolBeans-eerm.ttf','kool-isolated.png','@'),('mono','monofonto.ttf','mono-isolated.png','%'),('signature','Perfectsignature.ttf','signature-isolated.png','$')]
for key, filename, image, char in CASES:
    font=TTFont(ROOT/'testFonts'/filename)
    # Make a pure two-color PBM, keeping the generated artwork as the only source.
    with tempfile.TemporaryDirectory() as d:
        pbm=Path(d)/'image.pbm'; svg=Path(d)/'trace.svg'
        Image.open(ROOT/'experiment'/image).convert('L').point(lambda p: 0 if p < 128 else 255, mode='1').save(pbm)
        subprocess.run(['potrace','--svg','--flat','--turdsize','30','--opttolerance','0.2','-o',str(svg),str(pbm)],check=True)
        paths=re.findall(r'<path\s+d="([^"]+)"',svg.read_text(),re.S)
    if len(paths)!=1: raise ValueError(f'{key}: expected one traced path, got {len(paths)}')
    path=paths[0]; bounds=BoundsPen(None); parse_path(path,bounds)
    x0,y0,x1,y1=bounds.bounds
    cmap=font.getBestCmap(); old_name=cmap[ord(char)]
    old=font['glyf'][old_name]; old.recalcBounds(font['glyf'])
    # Some existing punctuation is tiny: for these cases use a capital as a visual guide.
    guide_name=cmap[ord('H')] if key in ('kool','signature') else old_name
    guide=font['glyf'][guide_name]; guide.recalcBounds(font['glyf'])
    scale=(guide.yMax-guide.yMin)/(y1-y0)
    lsb=max(0,font['hmtx'][guide_name][1]); guide_advance=font['hmtx'][guide_name][0]
    right=max(0,guide_advance-guide.xMax)
    x_scale=scale
    if key == 'mono':
        # Preserve cap height and the fixed-width cell; narrow only the outline.
        advance=font['hmtx'][old_name][0]
        lsb=round(advance * 0.05)
        right=lsb
        x_scale=min(scale,(advance-lsb-right)/(x1-x0))
    else:
        # Add breathing room for the italic @ before Kool Beans' decorative letters.
        if key == 'kool':
            lsb += round(font['head'].unitsPerEm * 0.03)
            right += round(font['head'].unitsPerEm * 0.05)
        advance=lsb+round((x1-x0)*x_scale)+right
    glyph_name='fontFiller_'+format(ord(char),'04X')
    if glyph_name in font.getGlyphOrder(): raise ValueError('Glyph name already exists')
    pen=TTGlyphPen(font.getGlyphSet()); quad=Cu2QuPen(pen,max_err=1,reverse_direction=True)
    trans=TransformPen(quad,(x_scale,0,0,scale,lsb-x0*x_scale,guide.yMin-y0*scale))
    parse_path(path,trans); glyph=pen.glyph()
    font.setGlyphOrder(font.getGlyphOrder()+[glyph_name]); font['glyf'][glyph_name]=glyph
    font['hmtx'][glyph_name]=(advance,lsb)
    for table in font['cmap'].tables:
        if table.isUnicode() and ord(char) in table.cmap: table.cmap[ord(char)]=glyph_name
    # Distinguish the modified font from the installed source without discarding notices.
    for record in font['name'].names:
        if record.nameID in (1,3,4,6,16,21):
            oldtext=record.toUnicode()
            suffix='-FillerTrial' if record.nameID==6 else ' Filler Trial'
            record.string=(oldtext+suffix).encode(record.getEncoding(),errors='replace')
    dest=ROOT/'experiment'/'traced'/f'{key}-filler-trial.ttf'; font.save(dest)
    check=TTFont(dest); assert check.getBestCmap()[ord(char)]==glyph_name
    assert check['glyf'][glyph_name].numberOfContours>0
    print(f'{key}: {char} -> {glyph_name}; guide height {guide.yMax-guide.yMin}, advance {advance}, saved {dest.name}')
