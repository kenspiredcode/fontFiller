"""Build diaeresis glyphs from the original font's outlines."""
import io
import statistics
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.pens.recordingPen import RecordingPen, DecomposingRecordingPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.svgLib.path import parse_path
from accent_kerning import inherit_kerning

BASES = {'ä':'a', 'ë':'e', 'ï':'i', 'ö':'o', 'ü':'u', 'ñ':'n'}

def contours(font, name):
    glyphs=font.getGlyphSet()
    if not name or name not in glyphs or name=='.notdef': return []
    rec=DecomposingRecordingPen(glyphs); glyphs[name].draw(rec)
    result=[]; current=None
    for op,args in rec.value:
        if op=='moveTo' or (op=='qCurveTo' and current is None): current=RecordingPen()
        if current is None: raise ValueError('This outline cannot be safely separated.')
        current.value.append((op,args))
        if op in ('closePath','endPath'): result.append(current); current=None
    if current is not None: raise ValueError('This outline cannot be safely separated.')
    return [c for c in result if bounds([c])]

def bounds(items):
    pen=BoundsPen(None)
    for c in items:c.replay(pen)
    return pen.bounds

def split_top(items):
    ordered=sorted(items,key=lambda c:bounds([c])[3],reverse=True)
    for i in range(1,len(ordered)):
        mark,body=ordered[:i],ordered[i:]; mb=bounds(mark);bb=bounds(body)
        if mb[1]>bb[3] and 0 < mb[3]-mb[1] < (bb[3]-bb[1])*.75:
            return mark,body
    raise ValueError('This font does not have a safely separable dot.')

def is_pair(items):
    # Two horizontally separated groups; include holes with their parent dot.
    boxes=[bounds([c]) for c in items]
    intervals=sorted((b[0],b[2]) for b in boxes)
    groups=[]
    for lo,hi in intervals:
        if not groups or lo>groups[-1][1]:groups.append([lo,hi])
        else:groups[-1][1]=max(groups[-1][1],hi)
    return len(groups)==2

def sources(font, char):
    cmap=font.getBestCmap()
    if char == 'ñ':
        for cp in (0x0303, 0x007e):
            items = contours(font, cmap.get(cp))
            if items and bounds(items): return items, 'existing tilde', False
        raise ValueError('No usable tilde was found.')
    for cp in (0x0308,0x00a8):
        items=contours(font,cmap.get(cp))
        if items and is_pair(items):return items,'existing diaeresis',False
    for other in 'äëüï':
        if other==char:continue
        try:mark,_=split_top(contours(font,cmap.get(ord(other))))
        except ValueError:continue
        if is_pair(mark):return mark,'existing diaeresis',False
    for other in 'ij':
        try:mark,_=split_top(contours(font,cmap.get(ord(other))))
        except ValueError:continue
        if bounds(mark):return mark,other+' dot',True
    items=contours(font,cmap.get(ord('.')))
    if items and bounds(items):return items,'period',True
    raise ValueError('No usable accent source was found. Try the AI accent.')

def estimate_slant(data, font):
    f=ImageFont.truetype(io.BytesIO(data),300);measure=[]
    for ch in 'Il1':
        if not font.getBestCmap().get(ord(ch)):continue
        image=Image.new('L',(800,800),255);ImageDraw.Draw(image).text((200,200),ch,font=f,fill=0)
        ink=np.asarray(image)<128;ys=np.where(ink.any(axis=1))[0];runs=[]
        for y in ys:
            if not runs or y>runs[-1][-1]+1:runs.append([])
            runs[-1].append(y)
        if not runs:continue
        run=max(runs,key=len);rows=[]
        for y in run[int(len(run)*.2):int(len(run)*.8)]:
            xs=np.flatnonzero(ink[y]);rows.append((y,(int(xs[0])+int(xs[-1]))/2,len(xs)))
        if len(rows)<8:continue
        p=np.asarray(rows);slope,intercept=np.polyfit(p[:,0],p[:,1],1)
        err=np.sqrt(np.mean((p[:,1]-(slope*p[:,0]+intercept))**2))/max(1,np.median(p[:,2]))
        if err<=.12:measure.append(-float(slope))
    clusters=[[v for v in measure if abs(v-item)<=.12] for item in measure]
    best=max(clusters,key=len,default=[])
    return statistics.median(best) if len(best)>=2 else 0

def dot_guides(data,font):
    """Estimate dot offset and clearance only when i and j agree."""
    cmap=font.getBestCmap();f=ImageFont.truetype(io.BytesIO(data),300)
    if any(not cmap.get(ord(c)) for c in 'ijx'):return None
    xmask=f.getmask('x').getbbox()
    if not xmask:return None
    height=xmask[3]-xmask[1]
    if height<=0:return None
    values=[]
    for ch in 'ij':
        im=Image.new('L',(800,800),255);ImageDraw.Draw(im).text((200,200),ch,font=f,fill=0)
        ink=np.asarray(im)<128;ys=np.flatnonzero(ink.any(axis=1));runs=[]
        for y in ys:
            if not runs or y>runs[-1][-1]+1:runs.append([])
            runs[-1].append(y)
        if len(runs)!=2:return None
        dot,stem=runs
        if len(dot)>.75*height or len(stem)<.5*height:return None
        xs=np.flatnonzero(ink[dot[0]:dot[-1]+1].any(axis=0))
        centers=[]
        for y in stem[:max(1,round(min(len(stem),height)*.15))]:
            points=np.flatnonzero(ink[y]);centers.append((int(points[0])+int(points[-1]))/2)
        values.append((((int(xs[0])+int(xs[-1]))/2-statistics.median(centers))/height,
                       (int(stem[0])-int(dot[-1])-1)/height))
    if abs(values[0][0]-values[1][0])>.12 or abs(values[0][1]-values[1][1])>.10:return None
    return (statistics.mean(v[0] for v in values),statistics.mean(v[1] for v in values))

def ai_mark(image_data, trace):
    im=Image.open(io.BytesIO(image_data)).convert('L')
    if im.width*im.height>12_000_000:raise ValueError('Generated image is too large.')
    im.thumbnail((512,512)); a=np.asarray(im)<128
    cols=np.flatnonzero(a.any(axis=0)); groups=[]
    for x in cols:
        if not groups or x>groups[-1][-1]+1:groups.append([])
        groups[-1].append(x)
    if len(groups)!=2 or min(len(g) for g in groups)<3:
        raise ValueError('The generated accent could not be isolated as two dots. Try again.')
    path=trace(image_data);rec=RecordingPen();parse_path(path,rec)
    return [rec]

def build(font,data,char,scale=1,offset=0,horizontal=0,image_data=None,trace=None):
    if char not in BASES:raise ValueError('Choose a supported accented letter.')
    font.getGlyphOrder();cmap=font.getBestCmap();base_name=cmap.get(ord(BASES[char]));base=contours(font,base_name)
    if not base:raise ValueError('This font needs the original base letter.')
    if BASES[char]=='i':_,base=split_top(base)
    if image_data:
        mark=ai_mark(image_data,trace);method='AI-generated diaeresis';pair=False
    else:mark,method,pair=sources(font,char)
    bx0,by0,bx1,by1=bounds(base);bw=bx1-bx0;bh=by1-by0
    mx0,my0,mx1,my1=bounds(mark);mw=mx1-mx0;mh=my1-my0
    if min(bw,bh,mw,mh)<=0:raise ValueError('The accent or base outline is empty.')
    if pair:
        sf=min(bw*.24/mw,bh*.19/mh)*scale;dotw=mw*sf;dotgap=bw*.12;pairw=2*dotw+dotgap
    else:
        sf=min(bw*(1 if BASES[char]=='i' else .8 if char=='ñ' else .63)/mw,bh*.27/mh)*scale;pairw=mw*sf
    slope=estimate_slant(data,font);guides=dot_guides(data,font)
    gap=bh*max(.03,min(.30,guides[1] if guides else .10))
    if guides and abs(slope)>=.05 and guides[0]*slope>0:
        shift=slope*bh*.5+guides[0]*bh
    else:
        shift=slope*(bh*.5+gap+mh*sf*.5)
    shift=max(-bw*.25,min(bw*.25,shift))
    left=(bx0+bx1-pairw)/2+shift+horizontal*font['head'].unitsPerEm
    bottom=by1+gap+offset*font['head'].unitsPerEm
    advance,lsb=font['hmtx'][base_name]
    name='fontFiller_%04X'%ord(char);n=2
    while name in font.getGlyphOrder():name='fontFiller_%04X_%d'%(ord(char),n);n+=1
    def draw(pen):
        for c in base:c.replay(pen)
        def accent(x):
            target=TransformPen(pen,(sf,0,0,sf,x-mx0*sf,bottom-my0*sf))
            if image_data and 'glyf' in font:target=Cu2QuPen(target,max_err=1,reverse_direction=True)
            for c in mark:c.replay(target)
        accent(left)
        if pair:accent(left+dotw+dotgap)
    if 'glyf' in font:
        pen=TTGlyphPen(font.getGlyphSet());draw(pen);font.setGlyphOrder(font.getGlyphOrder()+[name]);font['glyf'][name]=pen.glyph()
    else:
        cff=font['CFF '].cff;top=cff.topDictIndex[0];private=top.Private
        width=None if advance==private.defaultWidthX else advance-private.nominalWidthX
        pen=T2CharStringPen(width,None,roundTolerance=0);draw(pen);cs=pen.getCharString(private=private,globalSubrs=cff.GlobalSubrs)
        chars=top.CharStrings
        if chars.charStringsAreIndexed:chars.charStrings[name]=len(chars.charStringsIndex);chars.charStringsIndex.append(cs)
        else:chars[name]=cs
        order=list(font.getGlyphOrder());top.charset.append(name);font.setGlyphOrder(order+[name])
    font['hmtx'][name]=(advance,lsb)
    inherit_kerning(font,{name:base_name})
    for table in font['cmap'].tables:
        if table.isUnicode():table.cmap[ord(char)]=name
    for record in font['name'].names:
        if record.nameID in (1,3,4,6,16,21):
            value=record.toUnicode(); suffix='-FontFiller' if record.nameID==6 else ' Font Filler'
            record.string=(value if value.endswith(suffix) else value+suffix).encode(record.getEncoding(),errors='replace')
    if 'CFF ' in font and not font['CFF '].cff.fontNames[0].endswith('-FontFiller'):font['CFF '].cff.fontNames[0]+='-FontFiller'
    out=io.BytesIO();font.save(out)
    warning=left<0 or left+pairw>advance
    return out.getvalue(),method,warning
