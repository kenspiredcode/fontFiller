"""Build accented glyphs from the original font's outlines."""
import io
import math
import statistics
import unicodedata
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.pens.recordingPen import RecordingPen, DecomposingRecordingPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.basePen import BasePen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.svgLib.path import parse_path
from accent_kerning import inherit_kerning

ACUTE_BASES = dict(zip('áćéíḱĺńóŕśúẃýź', 'aceiklnorsuwyz'))
FAMILY_CHARS = {
    'grave': 'àèìǹòùẁỳ', 'circumflex': 'âĉêĝĥîĵôŝûŵŷ',
    'tilde': 'ãĩñõũỹ', 'diaeresis': 'äëïöüẅÿ',
    'ring': 'åů', 'macron': 'āēīōū', 'breve': 'ăĕğĭŏŭ',
    'caron': 'ǎčďěǐľňǒřšťǔž', 'dot above': 'ċḋėġṅż',
    'double acute': 'őű', 'acute': ''.join(ACUTE_BASES),
    'cedilla': 'çģķļņŗşţ', 'ogonek': 'ąęįų',
    'dot below': 'ḍḥḳḷṇṛṣṭẓ', 'comma below': 'șț',
}
# Each supported lowercase letter has a corresponding precomposed capital.
FAMILY_CHARS = {family: chars + chars.upper() for family, chars in FAMILY_CHARS.items()}
ACUTE_BASES.update({ch.upper(): base.upper() for ch, base in list(ACUTE_BASES.items())})
FAMILIES = {char: family for family, chars in FAMILY_CHARS.items() for char in chars}
BASES = {char: unicodedata.normalize('NFD', char)[0] for char in FAMILIES}
BELOW = {'cedilla', 'ogonek', 'dot below', 'comma below'}
# Explicit classification: adding a family requires choosing its behavior.
FAMILY_ATTACHMENT = {
    'acute': 'floating', 'grave': 'floating', 'circumflex': 'floating',
    'tilde': 'floating', 'diaeresis': 'floating', 'ring': 'floating',
    'macron': 'floating', 'breve': 'floating', 'caron': 'floating',
    'dot above': 'floating', 'double acute': 'floating',
    'cedilla': 'attached', 'ogonek': 'attached',
    'dot below': 'floating', 'comma below': 'floating',
}
ATTACHMENT_OVERRIDES = {char: 'floating' for char in 'ģķļņŗĶĻŅŖ'}

def attachment_kind(char):
    return ATTACHMENT_OVERRIDES.get(char, FAMILY_ATTACHMENT[FAMILIES[char]])

# Spacing accents are preferred to approximations from punctuation.
MARKS = {
    'grave': ('\u0300', '`'), 'circumflex': ('\u0302', 'ˆ', '^'),
    'tilde': ('\u0303', '~'), 'diaeresis': ('\u0308', '¨'),
    'ring': ('\u030a', '˚'), 'macron': ('\u0304', '¯'),
    'breve': ('\u0306', '˘'), 'caron': ('\u030c', 'ˇ'),
    'cedilla': ('\u0327', '¸'), 'ogonek': ('\u0328', '˛'),
    'dot above': ('\u0307', '˙'), 'dot below': ('\u0323',),
    'double acute': ('\u030b', '˝'), 'comma below': ('\u0326', ','),
}


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

class _PolygonPen(BasePen):
    """Flatten outlines for a bounded-resolution ink contact check."""
    def __init__(self):
        super().__init__(None); self.paths=[]; self.path=[]
    def _moveTo(self,p): self.path=[p]
    def _lineTo(self,p): self.path.append(p)
    def _curveToOne(self,p1,p2,p3):
        p0=self._getCurrentPoint()
        for i in range(1,17):
            t=i/16;u=1-t
            self.path.append((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],
                              u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1]))
    def _qCurveToOne(self,p1,p2):
        p0=self._getCurrentPoint()
        for i in range(1,13):
            t=i/12;u=1-t
            self.path.append((u*u*p0[0]+2*u*t*p1[0]+t*t*p2[0],
                              u*u*p0[1]+2*u*t*p1[1]+t*t*p2[1]))
    def _closePath(self):
        if len(self.path)>=3: self.paths.append(self.path)
        self.path=[]
    def _endPath(self): self._closePath()

def outline_contact(base, marks, upem, tolerance=0):
    """Compare ink masks, preserving holes by the nonzero winding rule.

    Curves are flattened and rasterized at up to 512 pixels per em; this is
    a review warning, not an exact vector intersection or a proof of quality.
    """
    bb=bounds(base); mb=bounds(marks)
    if not bb or not mb: return False
    scale=512/upem
    if bb[2]+tolerance/scale<mb[0] or mb[2]+tolerance/scale<bb[0] or bb[3]+tolerance/scale<mb[1] or mb[3]+tolerance/scale<bb[1]: return False
    x0=min(bb[0],mb[0]);y0=min(bb[1],mb[1]);w=max(bb[2],mb[2])-x0;h=max(bb[3],mb[3])-y0
    scale=min(scale, 760/max(w,h,1))
    width=max(3,math.ceil(w*scale)+5);height=max(3,math.ceil(h*scale)+5)
    def mask(contours):
        winding=np.zeros((height,width),dtype=np.int32)
        pen=_PolygonPen()
        for contour in contours: contour.replay(pen)
        for path in pen.paths:
            area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(path,path[1:]+path[:1]))
            if not area: continue
            image=Image.new('1',(width,height));draw=ImageDraw.Draw(image)
            draw.polygon([((x-x0)*scale+2,(y-y0)*scale+2) for x,y in path],fill=1)
            winding+=np.asarray(image,dtype=np.int32)*(1 if area>0 else -1)
        return winding!=0
    a=mask(base);b=mask(marks)
    if tolerance:
        # Include immediate pixel neighbors so outlines that meet at an edge
        # count as attached despite quantization.
        grown=np.zeros_like(a)
        for dy in range(-tolerance,tolerance+1):
            for dx in range(-tolerance,tolerance+1):
                sy0=max(0,-dy);sy1=min(height,height-dy);sx0=max(0,-dx);sx1=min(width,width-dx)
                grown[sy0+dy:sy1+dy,sx0+dx:sx1+dx] |= a[sy0:sy1,sx0:sx1]
        a=grown
    return bool(np.any(a & b))

def nudge_attachment(base, placed, upem, kind, direction='above', advance=None):
    """Find a small, bounded correction, or return None if none is safe.

    Positions are tried from shortest distance outward. Floating marks move
    away from the letter, attached marks toward it. The approximate ink test
    remains the authority; this does not assess the design of the result.
    """
    touching=outline_contact(base,placed,upem,tolerance=0 if kind=='floating' else 1)
    if (kind=='floating' and not touching) or (kind=='attached' and touching): return (0,0)
    before=bounds(placed); step=upem*.015
    candidates=[]
    for x in range(-8,9):
        for y in range(-8,9):
            if not (x or y) or x*x+y*y>64: continue
            if kind=='floating' and direction=='above' and y<0: continue
            if kind=='floating' and direction=='below' and y>0: continue
            if kind=='floating' and direction=='side' and x<0: continue
            if kind=='attached' and y<0: continue
            # Prefer movement in the expected direction when distances tie.
            preference=abs(x) if direction in ('above','below') or kind=='attached' else abs(y)
            candidates.append((x*x+y*y,preference,x,y))
    for _,_,x,y in sorted(candidates):
        dx=x*step;dy=y*step
        if advance is not None and before[0]>=0 and before[2]<=advance and (before[0]+dx<0 or before[2]+dx>advance): continue
        moved=[]
        for contour in placed:
            rec=RecordingPen();contour.replay(TransformPen(rec,(1,0,0,1,dx,dy)));moved.append(rec)
        contact=outline_contact(base,moved,upem,tolerance=1)
        if kind=='floating' and not contact: return dx,dy
        # Prefer a near-touching join; avoid forcing two strokes to overlap
        # substantially just to clear an approximate attachment warning.
        if kind=='attached' and contact and not outline_contact(base,moved,upem): return dx,dy
    return None

def split_top(items):
    ordered=sorted(items,key=lambda c:bounds([c])[3],reverse=True)
    for i in range(1,len(ordered)):
        mark,body=ordered[:i],ordered[i:]; mb=bounds(mark);bb=bounds(body)
        if mb[1]>bb[3] and 0 < mb[3]-mb[1] < (bb[3]-bb[1])*.75:
            return mark,body
    raise ValueError('This font does not have a safely separable dot.')

def split_bottom(items):
    ordered=sorted(items,key=lambda c:bounds([c])[1])
    for i in range(1,len(ordered)):
        mark,body=ordered[:i],ordered[i:]; mb=bounds(mark);bb=bounds(body)
        if mb[3]<bb[1] and 0 < mb[3]-mb[1] < (bb[3]-bb[1])*.75:
            return mark,body
    raise ValueError('This font does not have a safely separable mark.')

def is_pair(items):
    # Two horizontally separated groups; include holes with their parent dot.
    boxes=[bounds([c]) for c in items]
    intervals=sorted((b[0],b[2]) for b in boxes)
    groups=[]
    for lo,hi in intervals:
        if not groups or lo>groups[-1][1]:groups.append([lo,hi])
        else:groups[-1][1]=max(groups[-1][1],hi)
    return len(groups)==2

def orient_acute(items, mirror=False):
    """Orient an elongated punctuation outline; reject round or ambiguous marks."""
    points=[]
    for contour in items:
        for _, args in contour.value:
            for point in args:
                if isinstance(point, tuple) and len(point)==2 and all(isinstance(v, (int, float)) for v in point):
                    points.append(point)
    if len(points)<3: return None
    p=np.asarray(points, dtype=float)
    if mirror: p[:,0]*=-1
    values,vectors=np.linalg.eigh(np.cov(p.T))
    if values[1]<=0 or values[1]<values[0]*1.7: return None
    x,y=vectors[:,1]
    angle=math.atan2(y,x) % math.pi
    if mirror:
        # A vertical or backward grave is not an acute after reflection.
        if not math.radians(15)<=angle<=math.radians(80): return None
        matrix=(-1,0,0,1,0,0)
    else:
        delta=math.radians(55)-angle
        cos,sin=math.cos(delta),math.sin(delta)
        matrix=(cos,sin,-sin,cos,0,0)
    transformed=[]
    for contour in items:
        rec=RecordingPen();contour.replay(TransformPen(rec,matrix));transformed.append(rec)
    return transformed

SIDE_CARONS = 'ďľťĽ'

def side_caron_source(font, char):
    cmap=font.getBestCmap()
    for other in SIDE_CARONS:
        if other == char: continue
        base=contours(font,cmap.get(ord(BASES[other])))
        remaining=contours(font,cmap.get(ord(other)))
        if not base or not remaining: continue
        for contour in base:
            match=next((i for i, candidate in enumerate(remaining) if candidate.value==contour.value),None)
            if match is None: break
            remaining.pop(match)
        else:
            if remaining and bounds(remaining): return remaining, 'existing side caron', False
    for cp,label in ((0x2019,'right quote'),(0x27,'apostrophe')):
        items=contours(font,cmap.get(cp))
        if items and bounds(items): return items, label, False
    raise ValueError('No usable side caron was found. Try the AI accent.')

def extracted_mark(font, target, candidates):
    """Return an independently outlined mark and its base, when unambiguous."""
    cmap=font.getBestCmap()
    for other in candidates:
        if other==target and target!='ģ': continue
        base=contours(font,cmap.get(ord(BASES[other])))
        result=contours(font,cmap.get(ord(other)))
        if not base or not result: continue
        remaining=result[:]
        for contour in base:
            index=next((i for i,c in enumerate(remaining) if c.value==contour.value),None)
            if index is None: break
            remaining.pop(index)
        else:
            if not remaining: continue
            bb=bounds(base); mb=bounds(remaining)
            if mb[3]-mb[1] > (bb[3]-bb[1])*.7: continue
            if target=='ģ':
                if mb[1] <= bb[3]: continue
            elif mb[1] >= bb[1]+(bb[3]-bb[1])*.15 or mb[3] > bb[1]+(bb[3]-bb[1])*.2: continue
            return remaining, base
    return None

def sources(font, char):
    cmap=font.getBestCmap()
    if char in SIDE_CARONS: return side_caron_source(font,char)
    if char in ACUTE_BASES:
        for cp in (0x0301, 0x00b4):
            items=contours(font,cmap.get(cp))
            if items and bounds(items): return items, 'existing acute', False
        for other in ACUTE_BASES:
            if other == char: continue
            try: mark,_=split_top(contours(font,cmap.get(ord(other))))
            except ValueError: continue
            if bounds(mark): return mark, 'existing acute', False
        for cp in (0x0300, 0x0060):
            items=contours(font,cmap.get(cp))
            mark=orient_acute(items, mirror=True) if items else None
            if mark: return mark, 'mirrored grave accent', False
        for cp, name in ((0x0027, 'rotated apostrophe'), (0x2019, 'rotated right quote')):
            items=contours(font,cmap.get(cp))
            mark=orient_acute(items) if items else None
            if mark: return mark, name, False
        raise ValueError('No usable acute accent was found. Try the AI accent.')
    family=FAMILIES[char]
    if char=='ģ':
        found=extracted_mark(font,char,'ģ')
        if found: return found[0], 'existing g cedilla', False
        for cp in (0x0312, 0x02bb):
            items=contours(font,cmap.get(cp))
            if items: return items, 'existing turned comma', False
        raise ValueError('No usable above-g cedilla was found. Try the AI accent.')
    if family in BELOW:
        candidates=FAMILY_CHARS[family].replace('ģ','')
        if family=='cedilla': candidates='çşţÇŞŢĢ' if attachment_kind(char)=='attached' else 'ķļņŗĶĻŅŖ'
        found=extracted_mark(font,char,candidates)
        if found: return found[0], 'existing '+family+' from letter', False
        if family=='dot below':
            for cp in (0x0323,0x002e):
                items=contours(font,cmap.get(cp))
                if items: return items, 'existing dot' if cp==0x0323 else 'period', False
    for cp in MARKS[family]:
        items=contours(font,cmap.get(ord(cp)))
        if items and bounds(items) and (family!='diaeresis' or is_pair(items)):
            return items, 'existing '+family, False
    if family not in BELOW:
        for other in FAMILY_CHARS[family]:
            if other==char or other in SIDE_CARONS: continue
            try: mark,_=split_top(contours(font,cmap.get(ord(other))))
            except ValueError: continue
            if family!='diaeresis' or is_pair(mark): return mark, 'existing '+family, False
    if family!='diaeresis':
        raise ValueError('No usable '+family+' mark was found. Try the AI accent.')
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

def reference_shift(font, char):
    """Estimate mark offset from other accented letters in this font."""
    cmap=font.getBestCmap()
    def offsets(base):
        original=contours(font,cmap.get(ord(base)))
        if not original: return []
        if base in 'ij':
            try: _,original=split_top(original)
            except ValueError: return []
        bb=bounds(original); width=bb[2]-bb[0]
        if width<=0: return []
        values=[]
        for other,other_base in BASES.items():
            if other==char or other_base!=base or other in SIDE_CARONS or FAMILIES[other] in BELOW: continue
            try: mark,_=split_top(contours(font,cmap.get(ord(other))))
            except ValueError: continue
            mb=bounds(mark)
            value=((mb[0]+mb[2])-(bb[0]+bb[2]))/(2*width)
            if abs(value)<=.4: values.append(value)
        return values
    base=BASES[char]
    values=offsets(base)
    if len(values)>=2: return max(-.35,min(.35,statistics.median(values)))
    # A few families lack an existing version of this base; look for a
    # consistent font-wide tendency among the common lowercase vowels.
    measures=[]
    for ref in ('AEOU' if base.isupper() else 'aeou'):
        vals=offsets(ref)
        if len(vals)>=2: measures.append(statistics.median(vals))
    if len(measures)>=2 and max(measures)-min(measures)<=.15:
        return max(-.35,min(.35,statistics.median(measures)))
    return None

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

def ai_mark(image_data, trace, family):
    im=Image.open(io.BytesIO(image_data)).convert('L')
    if im.width*im.height>12_000_000:raise ValueError('Generated image is too large.')
    im.thumbnail((512,512)); a=np.asarray(im)<128
    def column_groups(columns):
        columns=np.unique(columns); groups=[]
        for x in columns:
            if not groups or x>groups[-1][-1]+1:groups.append([])
            groups[-1].append(x)
        return groups
    ys,xs=np.nonzero(a)
    groups=column_groups(xs)
    if family == 'double acute':
        # Slanted strokes can overlap in their ordinary x projection even when
        # the ink is separate. Project along several slants to reveal the gap.
        # Reject one-pixel gaps, which can be artifacts of the projection.
        paired=False
        for slope in np.linspace(-.8,.8,33):
            projected=np.rint(xs+slope*ys).astype(int)
            parts=column_groups(projected)
            if (len(parts)==2 and min(len(g) for g in parts)>=3 and
                    parts[1][0]-parts[0][-1]>=3):
                paired=True;break
        if not paired:
            raise ValueError('The generated accent could not be isolated as two marks. Try again.')
    elif family == 'diaeresis':
        if len(groups)!=2 or min(len(g) for g in groups)<3:
            raise ValueError('The generated accent could not be isolated as two marks. Try again.')
    elif len(groups)!=1 or len(groups[0])<3:
        raise ValueError('The generated accent could not be isolated as one mark. Try again.')
    path=trace(image_data);rec=RecordingPen();parse_path(path,rec)
    return [rec]

def build(font,data,char,scale=1,offset=0,horizontal=0,image_data=None,trace=None,return_checks=False,auto_nudge=True):
    if char not in BASES:raise ValueError('Choose a supported accented letter.')
    font.getGlyphOrder();cmap=font.getBestCmap();base_name=cmap.get(ord(BASES[char]));base=contours(font,base_name)
    if not base:raise ValueError('This font needs the original base letter.')
    if BASES[char] in 'ij' and (FAMILIES[char] not in BELOW or char=='ģ'):_,base=split_top(base)
    if image_data:
        mark=ai_mark(image_data,trace,FAMILIES[char]);method='AI-generated '+FAMILIES[char];pair=False
    else:mark,method,pair=sources(font,char)
    bx0,by0,bx1,by1=bounds(base);bw=bx1-bx0;bh=by1-by0
    mx0,my0,mx1,my1=bounds(mark);mw=mx1-mx0;mh=my1-my0
    if min(bw,bh,mw,mh)<=0:raise ValueError('The accent or base outline is empty.')
    if pair:
        sf=min(bw*.24/mw,bh*.19/mh)*scale;dotw=mw*sf;dotgap=bw*.12;pairw=2*dotw+dotgap
    else:
        family=FAMILIES[char]
        width_limit=1 if BASES[char]=='i' else .8 if char=='ñ' else .55 if family=='ring' else .63
        height_limit=.42 if family in ('ring','circumflex') else .27
        sf=min(bw*width_limit/mw,bh*height_limit/mh)*scale;pairw=mw*sf
    slope=estimate_slant(data,font);guides=dot_guides(data,font)
    gap=bh*max(.03,min(.30,guides[1] if guides else .10))
    if guides and abs(slope)>=.05 and guides[0]*slope>0:
        shift=slope*bh*.5+guides[0]*bh
    else:
        shift=slope*(bh*.5+gap+mh*sf*.5)
    shift=max(-bw*.25,min(bw*.25,shift))
    if FAMILIES[char] not in BELOW and char not in SIDE_CARONS:
        measured=reference_shift(font,char)
        if measured is not None: shift=measured*bw
    left=(bx0+bx1-pairw)/2+shift+horizontal*font['head'].unitsPerEm
    family=FAMILIES[char]
    bottom=by1+gap+offset*font['head'].unitsPerEm
    if char=='ḋ':
        # The dot commonly sits over the bowl, alongside d's ascender.
        x=contours(font,cmap.get(ord('x')))
        if x:
            xb=bounds(x); xheight=xb[3]-xb[1]
            dot_sf=min(xheight*.22/mh,bw*.24/mw)*scale
            dot_gap=xheight*.08
            dot_bottom=xb[3]+dot_gap
            if dot_bottom+mh*dot_sf<=by1+xheight*.03:
                sf=dot_sf; pairw=mw*sf
                left=bx0+bw*.30-pairw/2+shift+horizontal*font['head'].unitsPerEm
                bottom=dot_bottom+offset*font['head'].unitsPerEm
    if family in BELOW and char!='ģ':
        upem=font['head'].unitsPerEm
        xheight=contours(font,cmap.get(ord('x')))
        xheight=(bounds(xheight)[3]-bounds(xheight)[1]) if xheight else bh
        heights={'cedilla':.42,'ogonek':.42,'dot below':.16,'comma below':.30}
        sf=min(xheight*heights[family]/mh,bw*.75/mw)*scale
        if method.endswith('from letter'): sf=scale
        pairw=mw*sf
        left=(bx0+bx1-pairw)/2+horizontal*upem
        attached=attachment_kind(char)=='attached'
        top=by0+(xheight*.035 if attached else -xheight*.10)
        if family=='ogonek':
            # Attach the top of the mark at a low point on the right-hand
            # terminal; the outline's farthest right point may be much higher.
            low=[p for c in base for _,args in c.value for p in args
                 if isinstance(p,tuple) and len(p)==2 and all(isinstance(v,(int,float)) for v in p)
                 and p[1]<=by0+xheight*.16]
            anchor=max(low,key=lambda p:p[0],default=(bx1,by0))
            mark_points=[p for c in mark for _,args in c.value for p in args
                         if isinstance(p,tuple) and len(p)==2 and all(isinstance(v,(int,float)) for v in p)
                         and p[1]>=my1-mh*.08]
            mark_x=sum(p[0] for p in mark_points)/len(mark_points) if mark_points else (mx0+mx1)/2
            left=anchor[0]-(mark_x-mx0)*sf+horizontal*upem
            top=anchor[1]+xheight*.035
        bottom=top-mh*sf+offset*upem
    if char=='ģ':
        upem=font['head'].unitsPerEm
        sf=(scale if method=='existing g cedilla' else min(bw*.4/mw,bh*.3/mh)*scale)
        pairw=mw*sf
        left=(bx0+bx1-pairw)/2+horizontal*upem
        bottom=by1+gap+offset*upem
    if char in SIDE_CARONS:
        # A side caron sits alongside the ascender, not above its center.
        upem=font['head'].unitsPerEm
        sf=min(upem*.18/mw,upem*.23/mh)*scale
        pairw=mw*sf
        points=[point for contour in base for _, args in contour.value for point in args
                if isinstance(point,tuple) and len(point)==2 and all(isinstance(v,(int,float)) for v in point)
                and point[1]>=by0+bh*.82]
        stem_right=max((p[0] for p in points),default=bx1)
        l=contours(font,cmap.get(ord('l')))
        ascender=bounds(l)[3] if l else by1
        top=max(by1,ascender)+upem*.01
        left=stem_right+upem*.015+horizontal*upem
        bottom=top-mh*sf+offset*upem
        if method=='existing side caron':
            # Reuse the font's mark size and offset, including script fonts that
            # place a full caron above the ascender instead of at its side.
            sf=scale; pairw=mw*sf
            for other in SIDE_CARONS:
                if other==char: continue
                refbase=contours(font,cmap.get(ord(BASES[other])))
                refglyph=contours(font,cmap.get(ord(other)))
                rest=refglyph[:]
                for contour in refbase:
                    match=next((i for i,c in enumerate(rest) if c.value==contour.value),None)
                    if match is None: break
                    rest.pop(match)
                else:
                    if refbase and [c.value for c in rest]==[c.value for c in mark]:
                        rx0,ry0,rx1,ry1=bounds(refbase)
                        refpoints=[p for c in refbase for _,args in c.value for p in args
                                   if isinstance(p,tuple) and len(p)==2 and all(isinstance(v,(int,float)) for v in p)
                                   and p[1]>=ry0+(ry1-ry0)*.82]
                        refstem=max((p[0] for p in refpoints),default=rx1)
                        left=stem_right+(mx0-refstem)+horizontal*upem
                        bottom=my1-mh*sf+offset*upem
                        break
    checks={'overhang': False, 'collision': False, 'unattached': False, 'nudged': False}
    advance,lsb=font['hmtx'][base_name]
    if return_checks or auto_nudge:
        def positioned(xpos,ypos):
            placed=[]
            for x in ([xpos,xpos+dotw+dotgap] if pair else [xpos]):
                for contour in mark:
                    rec=RecordingPen(); contour.replay(TransformPen(rec,(sf,0,0,sf,x-mx0*sf,ypos-my0*sf))); placed.append(rec)
            return placed
        placed=positioned(left,bottom)
        kind=attachment_kind(char)
        upem=font['head'].unitsPerEm
        if auto_nudge:
            direction='side' if char in SIDE_CARONS else 'below' if family in BELOW and char!='ģ' else 'above'
            # Compute correction at the unadjusted position, then apply the
            # user's horizontal and vertical offsets relative to that baseline.
            baseline=positioned(left-horizontal*upem,bottom-offset*upem)
            delta=nudge_attachment(base,baseline,upem,kind,direction,advance)
            if delta and delta!=(0,0):
                left+=delta[0];bottom+=delta[1];checks['nudged']=True
                placed=positioned(left,bottom)
        if return_checks:
            if kind=='floating': checks['collision']=outline_contact(base,placed,upem)
            else: checks['unattached']=not outline_contact(base,placed,upem,tolerance=1)
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
    # TrueType rasterizers derive phantom points from the left side bearing.
    # Match the new outline's left edge so an overhanging mark cannot shift
    # the preserved base outline during save or rendering.
    font['hmtx'][name]=(advance,round(min(bx0,left)))
    # Windows uses these bounds to clip ink, including accents above capitals.
    if 'OS/2' in font:
        font['OS/2'].usWinAscent=max(font['OS/2'].usWinAscent, math.ceil(max(by1,bottom+mh*sf,0)))
        font['OS/2'].usWinDescent=max(font['OS/2'].usWinDescent, math.ceil(max(-by0,-bottom,0)))
    inherit_kerning(font,{name:base_name})
    for table in font['cmap'].tables:
        if table.isUnicode():table.cmap[ord(char)]=name
    for record in font['name'].names:
        if record.nameID in (1,3,4,6,16,21):
            value=record.toUnicode(); suffix='-FontFiller' if record.nameID==6 else ' Font Filler'
            record.string=(value if value.endswith(suffix) else value+suffix).encode(record.getEncoding(),errors='replace')
    if 'CFF ' in font and not font['CFF '].cff.fontNames[0].endswith('-FontFiller'):font['CFF '].cff.fontNames[0]+='-FontFiller'
    out=io.BytesIO();font.save(out)
    checks['overhang']=left<0 or left+pairw>advance
    return out.getvalue(),method,checks if return_checks else checks['overhang']
