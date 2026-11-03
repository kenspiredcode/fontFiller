"""Font Filler: local, single-user prototype."""
import base64
import io
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import os
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file, send_from_directory
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.svgLib.path import parse_path
from PIL import Image, ImageDraw, ImageFont
import accents
import bulk_grid

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024
EXTRA_SYMBOLS = '‘’“”–—…•€£¥¢©®™¿¡«»‹›°×÷±µ§¶†‡' + ''.join(accents.FAMILIES)
SYMBOLS = ''.join(chr(code) for code in range(33, 127)) + EXTRA_SYMBOLS
FLIP_SOURCES = {'¿': '?', '¡': '!'}
MODEL = 'fal-ai/gpt-image-1.5/edit'
BENCHMARK_MODELS = {
    'qwen': 'fal-ai/qwen-image-edit-2511',
    'klein': 'fal-ai/flux-2/klein/4b/base/edit',
    'gpt': 'fal-ai/gpt-image-1.5/edit',
}
RATE_GATE_URL = 'https://font-filler-rate-gate.kennethblakeburleson.workers.dev'


def read_font(data):
    try:
        font = TTFont(io.BytesIO(data))
        if 'fvar' in font or 'CFF2' in font or font.flavor is not None:
            raise ValueError('Please use a static TTF or CFF OTF font; variable and web fonts are not supported.')
        if 'glyf' not in font and 'CFF ' not in font:
            raise ValueError('Please use a static TTF or CFF OTF font with outline glyphs.')
        if 'CFF ' in font and hasattr(font['CFF '].cff.topDictIndex[0], 'FDArray'):
            raise ValueError('CID-keyed CFF fonts are not supported yet.')
        if not font.getBestCmap():
            raise ValueError('The font has no usable character map.')
        return font
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Could not read this font. Choose a valid static TTF or CFF OTF file.') from exc


def glyph_bounds(font, name):
    if not name or name == '.notdef':
        return None
    glyphs = font.getGlyphSet()
    if name not in glyphs:
        return None
    pen = BoundsPen(glyphs)
    glyphs[name].draw(pen)
    return pen.bounds


def has_outline(font, name):
    bounds = glyph_bounds(font, name)
    return bool(bounds and bounds[2] > bounds[0] and bounds[3] > bounds[1])


def uploaded_font():
    file = request.files.get('font')
    if not file or not file.filename.lower().endswith(('.ttf', '.otf')):
        raise ValueError('Choose a static .ttf or .otf font file.')
    data = file.read()
    if len(data) > 2_500_000: raise ValueError('Choose a font smaller than 2.5 MB.')
    read_font(data)
    return data


def trace_path(image_data):
    from potrace import Bitmap
    image = Image.open(io.BytesIO(image_data)).convert('L')
    if image.width * image.height > 12_000_000:
        raise ValueError('Generated image is too large.')
    image.thumbnail((512, 512))
    curves = Bitmap(image).trace(turdsize=10, opttolerance=0.2)
    def xy(p): return f'{p.x:.4f} {-p.y:.4f}'
    paths = []
    for curve in curves:
        if curve.start_point is None: continue
        parts = ['M ' + xy(curve.start_point)]
        for segment in curve:
            if segment.is_corner:
                parts.append('L ' + xy(segment.c) + ' L ' + xy(segment.end_point))
            else:
                parts.append('C ' + xy(segment.c1) + ' ' + xy(segment.c2) + ' ' + xy(segment.end_point))
        parts.append('Z'); paths.append(' '.join(parts))
    if not paths: raise ValueError('The generated image contains no visible outline.')
    return ' '.join(paths)


def specimen(data, lowercase=False):
    # Individually spaced glyphs avoid clipping even with elaborate swashes.
    f = ImageFont.truetype(io.BytesIO(data), 100)
    source_font = read_font(data); source_cmap = source_font.getBestCmap()
    if lowercase and not any(has_outline(source_font, source_cmap.get(ord(ch))) for ch in 'abcdefghijklmnopqrstuvwxyz'):
        rows = ('ABCDEFGHIJKLM', 'NOPQRSTUVWXYZ')
    else:
        rows = ('abcdefghijklm', 'nopqrstuvwxyz') if lowercase else ('ABCDEFGHJKLM', 'NOPQRSTUVWXYZ', 'abcdefghijklm', '0123456789')
    canvas = Image.new('RGB', (1400, 205 * len(rows) + 20), 'white')
    draw = ImageDraw.Draw(canvas)
    for row, chars in enumerate(rows):
        for col, ch in enumerate(chars):
            if not has_outline(source_font, source_cmap.get(ord(ch))): continue
            x, y = 20 + col * 105, 10 + row * 205
            draw.text((x, y), ch, font=f, fill='black')
    out = io.BytesIO(); canvas.save(out, format='PNG'); return out.getvalue()


def isolated_specimens(data, count):
    font=ImageFont.truetype(io.BytesIO(data), 300)
    result=[]
    for letter in 'HOSAR'[:count]:
        image=Image.new('RGB',(900,900),'white'); draw=ImageDraw.Draw(image)
        box=draw.textbbox((0,0),letter,font=font)
        draw.text(((900-(box[2]-box[0]))/2-box[0],(900-(box[3]-box[1]))/2-box[1]),letter,font=font,fill='black')
        out=io.BytesIO();image.resize((512,512), Image.Resampling.LANCZOS).save(out,format='PNG')
        result.append(out.getvalue())
    return result


class DailyLimitReached(Exception):
    pass


def reserve_generation():
    secret = os.getenv('RATE_GATE_SECRET')
    if not secret:
        raise ValueError('The daily generation limit is not configured. Contact the app owner.')
    req = Request(RATE_GATE_URL, data=b'', method='POST', headers={'Authorization': 'Bearer ' + secret, 'User-Agent': 'FontFiller/1.0'})
    try:
        with urlopen(req, timeout=10) as response:
            return json.load(response)['remaining']
    except HTTPError as exc:
        if exc.code == 429:
            raise DailyLimitReached('Daily limit reached. Try again after midnight Pacific time.') from exc
        raise ValueError('The daily generation limit service is unavailable. Please try again later.') from exc
    except (URLError, TimeoutError, ValueError, KeyError) as exc:
        raise ValueError('The daily generation limit service is unavailable. Please try again later.') from exc


def generate_image(data, character, model=MODEL, reference_count=0, style_emphasis=False, accent=False):
    key = os.getenv('FAL_KEY')
    if not key:
        raise ValueError('The fal API key is not configured. Contact the app owner.')
    references = isolated_specimens(data, reference_count) if reference_count else [specimen(data)]
    if accent:
        f=ImageFont.truetype(io.BytesIO(data),300); base=accents.BASES[character]
        image=Image.new('RGB',(768,768),'white'); draw=ImageDraw.Draw(image)
        box=draw.textbbox((0,0),base,font=f)
        draw.text(((768-(box[2]-box[0]))/2-box[0],(768-(box[3]-box[1]))/2-box[1]),base,font=f,fill='black')
        buffer=io.BytesIO();image.save(buffer,format='PNG');references=[buffer.getvalue(),specimen(data, lowercase=True)]
    image_urls = ['data:image/png;base64,' + base64.b64encode(image).decode('ascii') for image in references]
    prompt = (f'Use the provided image as a typeface style reference. Create exactly one {character} character '
              'in a matching typeface: match the letterforms’ stroke weight, proportions, slant and distinctive details. '
              'Show only the single black glyph, large and centered on a plain white background; no labels, other letters, texture or decoration.')
    if style_emphasis:
        prompt = (f'Create exactly one {character} character as a new member of the typeface shown in the reference image or images. '
                  'Study and carry over the distinctive visual DNA: proportions, stroke weight and contrast, angle, curves, terminals, '
                  'serifs or lack of serifs, flourishes, decorative cuts, outlines and other repeated signature details when present. '
                  'Be faithful to this specific font, even if unusual; do not replace its character with a generic symbol. '
                  'Keep the symbol immediately recognizable as the requested character. Show only one black glyph, large and centered '
                  'on a plain white background, with clear edges for tracing; no labels, other characters, shadows, background texture or decoration unrelated to the font.')
    if accent:
        mark = ('an inverted comma above the letter, for lowercase g with cedilla' if character=='ģ'
                else 'an apostrophe-like side caron: a single small comma-shaped mark' if character in accents.SIDE_CARONS
                else 'a diaeresis: exactly two separate dots side by side' if accents.FAMILIES[character]=='diaeresis'
                else 'the '+accents.FAMILIES[character]+' diacritical mark')
        prompt = ('Use the first image as the base letter and the second as a typeface reference. '
                  f'Create only {mark}, in black and in the visual style of this font. '
                  'Do not draw the letter itself, other characters, labels, shadows or decoration. '
                  'Center the mark on a plain white background with clear edges.')
    payload = json.dumps({'prompt':prompt, 'image_urls':image_urls,
                          'image_size':'square_hd', 'num_images':1, 'output_format':'png', 'sync_mode':True}).encode()
    if model == BENCHMARK_MODELS['gpt']:
        options = json.loads(payload); options.update({'image_size':'1024x1024', 'quality':'low', 'input_fidelity':'low', 'background':'opaque'}); payload = json.dumps(options).encode()
    reserve_generation()  # Reserve before submission; count failures too, since fal may charge for them.
    req = Request('https://fal.run/' + model, data=payload, method='POST',
                  headers={'Authorization':'Key ' + key, 'Content-Type':'application/json', 'User-Agent':'FontFiller/1.0'})
    try:
        with urlopen(req, timeout=100) as response:
            result=json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError('fal could not generate this character. Check your fal key and balance, then try again.') from exc
    images=result.get('images') or []
    uri=images[0].get('url','') if images else ''
    if not uri.startswith('data:image/png;base64,'):
        raise ValueError('fal returned an unexpected image. Please try again.')
    try:
        return base64.b64decode(uri.split(',',1)[1],validate=True)
    except ValueError as exc:
        raise ValueError('fal returned an invalid image. Please try again.') from exc


def build_font(data, image_data, char, scale=1.0, spacing=1.0, offset=0.0, flip=False):
    font = read_font(data); cmap = font.getBestCmap(); upem = font['head'].unitsPerEm
    source_name = cmap.get(ord(FLIP_SOURCES[char])) if flip and char in FLIP_SOURCES else None
    if flip and (char not in FLIP_SOURCES or not has_outline(font, source_name)):
        raise ValueError('The matching upright character is not available to flip.')
    if flip:
        # Decompose composites before transformation, so both outline formats can use them.
        from fontTools.pens.recordingPen import DecomposingRecordingPen
        glyphs = font.getGlyphSet()
        recording = DecomposingRecordingPen(glyphs)
        glyphs[source_name].draw(recording)
        x0, y0, x1, y1 = glyph_bounds(font, source_name)
    else:
        path = trace_path(image_data)
        bounds = BoundsPen(None); parse_path(path, bounds)
        if bounds.bounds is None: raise ValueError('The generated image contains no visible outline.')
        x0, y0, x1, y1 = bounds.bounds
    if x1 <= x0 or y1 <= y0: raise ValueError('The generated outline is empty.')
    guide_name = next((cmap.get(ord(c)) for c in 'HO' if has_outline(font, cmap.get(ord(c)))), None)
    if not guide_name: raise ValueError('This font needs a visible H or O to estimate glyph size.')
    guide_bounds = glyph_bounds(font, guide_name)
    height = guide_bounds[3] - guide_bounds[1]
    # Small punctuation occupies a portion of cap height, and sits at a suitable
    # position within the em. These are starting points; users can adjust them.
    if char in '‘’“”°™': factor, bottom = .38, .62
    elif char in '–—': factor, bottom = .12, .42
    elif char == '•': factor, bottom = .25, .32
    elif char in '×÷±‹›': factor, bottom = .6, .15
    elif char == '…': factor, bottom = .15, 0
    else: factor, bottom = 1, 0
    y_scale = (scale if flip else height * factor * scale / (y1-y0))
    x_scale = y_scale
    bearing = max(round(upem * .04), 1)
    is_fixed = bool(font['post'].isFixedPitch)
    if is_fixed:
        advance = font['hmtx'][source_name if flip else guide_name][0]
        x_scale = min(x_scale, max(1, advance - 2*bearing)/(x1-x0))
    else:
        bearing = round((max(x0, 0) if flip else bearing) * spacing)
        advance = round((x1-x0)*x_scale) + 2*bearing
    if flip:
        # Rotate 180 degrees, keeping the width; lower the inverted form slightly.
        transform=(-x_scale,0,0,-y_scale,bearing+x1*x_scale,
                   guide_bounds[1] - height*.2*scale + y1*y_scale + offset*upem)
    else:
        transform=(x_scale,0,0,y_scale,bearing-x0*x_scale,guide_bounds[1]+height*bottom-y0*y_scale+offset*upem)
    def draw(pen):
        target = TransformPen(pen, transform)
        if flip: recording.replay(target)
        else: parse_path(path, target)
    name = 'fontFiller_%04X' % ord(char)
    if name in font.getGlyphOrder():
        n=2
        while f'{name}_{n}' in font.getGlyphOrder(): n+=1
        name=f'{name}_{n}'
    if 'glyf' in font:
        pen=TTGlyphPen(font.getGlyphSet())
        draw(Cu2QuPen(pen,max_err=1,reverse_direction=True))
        font.setGlyphOrder(font.getGlyphOrder()+[name])
        font['glyf'][name]=pen.glyph()
    else:
        cff=font['CFF '].cff
        top=cff.topDictIndex[0]
        private=top.Private
        width=None if advance == private.defaultWidthX else advance-private.nominalWidthX
        pen=T2CharStringPen(width,None)
        draw(pen)
        charstring=pen.getCharString(private=private,globalSubrs=cff.GlobalSubrs)
        charstrings=top.CharStrings
        if charstrings.charStringsAreIndexed:
            charstrings.charStrings[name]=len(charstrings.charStringsIndex)
            charstrings.charStringsIndex.append(charstring)
        else:
            charstrings[name]=charstring
        order=list(font.getGlyphOrder())
        top.charset.append(name)
        font.setGlyphOrder(order+[name])
    font['hmtx'][name]=(advance,bearing)
    mapped=False
    for table in font['cmap'].tables:
        if table.isUnicode() and (ord(char) <= 0xffff or table.format in (12, 13)):
            table.cmap[ord(char)]=name; mapped=True
    if not mapped: raise ValueError('This font cannot encode the selected character.')
    for record in font['name'].names:
        if record.nameID in (1,3,4,6,16,21):
            suffix='-FontFiller' if record.nameID == 6 else ' Font Filler'
            value=record.toUnicode()
            record.string=(value if value.endswith(suffix) else value+suffix).encode(record.getEncoding(),errors='replace')
    if 'CFF ' in font:
        cff=font['CFF '].cff
        if not cff.fontNames[0].endswith('-FontFiller'): cff.fontNames[0] += '-FontFiller'
    out=io.BytesIO(); font.save(out); out.seek(0)
    check=TTFont(out)
    if check.getBestCmap()[ord(char)] != name: raise ValueError('Export mapping mismatch: ' + str(check.getBestCmap()[ord(char)]) + ' expected ' + name)
    return out.getvalue()


@app.before_request
def local_only():
    if not os.getenv('VERCEL') and request.host.split(':', 1)[0] not in ('127.0.0.1', 'localhost'):
        return jsonify(error='This prototype only accepts local requests.'), 403
    origin = request.headers.get('Origin')
    if request.method == 'POST' and origin and urlparse(origin).netloc != request.host:
        return jsonify(error='Request origin is not allowed.'), 403

@app.errorhandler(Exception)
def errors(error):
    if getattr(error, 'code', None) == 413: return jsonify(error='File too large. Use a font under 2.5 MB.'), 413
    app.logger.warning('Request failed: %s', type(error).__name__)
    if isinstance(error, DailyLimitReached): return jsonify(error=str(error)), 429
    if isinstance(error, ValueError): return jsonify(error=str(error)), 400
    return jsonify(error='Something went wrong. Check the font, API configuration, and server output, then try again.'), 500

@app.get('/')
def index(): return send_from_directory('static','index.html')

@app.post('/api/font')
def upload():
    data=uploaded_font(); font=read_font(data); cmap=font.getBestCmap()
    missing=[c for c in SYMBOLS if not has_outline(font,cmap.get(ord(c)))]
    family=font['name'].getDebugName(1) or 'Uploaded font'
    accent_sources={}
    for ch,base in accents.BASES.items():
        if not has_outline(font,cmap.get(ord(base))):
            accent_sources[ch]='missing base'
            continue
        if base in 'ij' and accents.FAMILIES[ch] not in accents.BELOW:
            try: accents.split_top(accents.contours(font,cmap.get(ord(base))))
            except ValueError as exc:
                accent_sources[ch]=str(exc)
                continue
        try:
            accent_sources[ch]=accents.sources(font,ch)[1]
        except ValueError:
            accent_sources[ch]='AI accent'
    info = dict(session=True, family=family, missing=missing, present=[c for c in SYMBOLS if c not in missing], flippable=[c for c, source in FLIP_SOURCES.items() if has_outline(font, cmap.get(ord(source)))], accent_sources=accent_sources)
    if request.form.get('workspace') == '1': info['mark_groups'] = missing_mark_groups(data)
    return jsonify(info)

@app.post('/api/generate')
def generate():
    data=uploaded_font(); ch=request.form.get('character','')
    if len(ch)!=1 or ch not in SYMBOLS: raise ValueError('Choose a supported character.')
    variant=request.form.get('model','gpt') if os.getenv('VERCEL_ENV') == 'preview' else 'gpt'
    if variant not in BENCHMARK_MODELS: raise ValueError('Unknown model.')
    reference_count=request.form.get('reference_count', '0') if os.getenv('VERCEL_ENV') == 'preview' else '0'
    if reference_count not in ('0','1','3','5'): raise ValueError('Invalid reference count.')
    style_emphasis=os.getenv('VERCEL_ENV') == 'preview' and request.form.get('style_emphasis') == '1'
    is_accent = request.form.get('method') == 'accent-ai'
    if is_accent and ch not in accents.BASES: raise ValueError('Choose a supported accented letter.')
    image=generate_image(data,ch,BENCHMARK_MODELS[variant],int(reference_count),style_emphasis,accent=is_accent)
    resized=Image.open(io.BytesIO(image)).convert('RGB'); resized.thumbnail((512,512))
    buffer=io.BytesIO(); resized.save(buffer,format='PNG',optimize=True); image=buffer.getvalue()
    if is_accent: accents.build(read_font(data),data,ch,image_data=image,trace=trace_path)
    else: build_font(data,image,ch)
    return jsonify(image='data:image/png;base64,'+base64.b64encode(image).decode())

def missing_characters(data):
    font = read_font(data); cmap = font.getBestCmap()
    return [ch for ch in SYMBOLS if not has_outline(font, cmap.get(ord(ch)))]


def encode_font(data):
    return base64.b64encode(data).decode('ascii')


def missing_mark_groups(data):
    """Group buildable missing letters by the exact mark they need."""
    font = read_font(data); cmap = font.getBestCmap(); groups = {}
    for ch in missing_characters(data):
        if ch not in accents.BASES or not has_outline(font, cmap.get(ord(accents.BASES[ch]))): continue
        try:
            if accents.BASES[ch] in 'ij' and accents.FAMILIES[ch] not in accents.BELOW:
                accents.split_top(accents.contours(font, cmap.get(ord(accents.BASES[ch]))))
            try:
                accents.sources(font, ch)
                continue
            except ValueError:
                pass
        except ValueError:
            continue
        key = 'inverted comma above' if ch == 'ģ' else 'side caron' if ch in accents.SIDE_CARONS else accents.FAMILIES[ch]
        groups.setdefault(key, []).append(ch)
    return groups


@app.post('/api/bulk/prepare')
def bulk_prepare():
    data = uploaded_font(); added = []; issues = []
    for ch in missing_characters(data):
        if ch not in FLIP_SOURCES and ch not in accents.BASES: continue
        font = read_font(data); cmap = font.getBestCmap()
        try:
            if ch in FLIP_SOURCES:
                if not has_outline(font, cmap.get(ord(FLIP_SOURCES[ch]))): continue
                data = build_font(data, None, ch, flip=True)
            else:
                if not has_outline(font, cmap.get(ord(accents.BASES[ch]))): continue
                accents.sources(font, ch)
                data, _, checks = accents.build(font, data, ch, return_checks=True)
                if checks['nudged']: issues.append(f'{ch}: accent was adjusted automatically; review placement.')
                if checks['overhang']: issues.append(f'{ch}: accent extends beyond its advance; review spacing.')
                if checks['collision']: issues.append(f'{ch}: floating accent may overlap the letter; review placement.')
                if checks['unattached']: issues.append(f'{ch}: attached accent may be disconnected; review placement.')
            added.append(ch)
        except ValueError as exc:
            issues.append(f'{ch}: {exc}')
    return jsonify(font=encode_font(data), added=added, remaining=missing_characters(data), warnings=issues, mark_groups=missing_mark_groups(data))


@app.post('/api/bulk/generate')
def bulk_generate():
    data = uploaded_font()
    chars = request.form.get('characters', '')
    size = request.form.get('grid', '')
    if size not in ('3', '4'): raise ValueError('Choose a 3×3 or 4×4 grid.')
    size = int(size)
    if not chars or len(chars) > size*size or len(set(chars)) != len(chars): raise ValueError('Invalid batch of characters.')
    missing = set(missing_characters(data))
    if any(ch not in missing for ch in chars): raise ValueError('Only missing supported characters can be generated.')
    mark_mode = request.form.get('kind') == 'marks'
    groups = missing_mark_groups(data) if mark_mode else {}
    if mark_mode and (size != 3 or any(ch not in [v[0] for v in groups.values()] for ch in chars)):
        raise ValueError('Choose missing accent marks for a 3×3 grid.')
    key = os.getenv('FAL_KEY')
    if not key: raise ValueError('The fal API key is not configured. Contact the app owner.')
    positions = [f'row {i//size+1}, column {i%size+1}: {json.dumps(ch, ensure_ascii=False)}' for i,ch in enumerate(chars)]
    prompt = (f'Use the provided image as a typeface style reference. Create exactly {len(chars)} distinct black glyphs '
              f'in a {size} by {size} grid on a white square canvas. Place exactly one glyph in each specified cell: '
              + '; '.join(positions) + '. Leave all other cells blank. Match the typeface stroke weight, proportions, '
              'slant and distinctive details. Center each glyph within its cell with generous whitespace, including at all image edges. '
              'No grid lines, labels, extra characters, texture or decoration.')
    if mark_mode:
        names = {v[0]: k for k, v in groups.items()}
        positions = [f'row {i//3+1}, column {i%3+1}: {names[ch]}' for i, ch in enumerate(chars)]
        prompt = ('Use the provided typeface specimen as a style reference. Draw isolated black diacritical marks '
                  'in a 3 by 3 grid on a white square canvas, one mark per specified cell: ' + '; '.join(positions) +
                  '. A diaeresis has two separate dots; a double acute has two separate strokes. '
                  'A side caron is a small apostrophe-like mark. Leave unused cells empty. Match the font’s stroke and style. '
                  'Center each mark with generous whitespace. No letters, grid lines, labels, or decoration.')
    reference_image = specimen(data, lowercase=True) if mark_mode or all(ch in accents.BASES for ch in chars) else specimen(data)
    reference = 'data:image/png;base64,' + base64.b64encode(reference_image).decode('ascii')
    payload = json.dumps({'prompt': prompt, 'image_urls': [reference], 'image_size': '1024x1024',
                          'num_images': 1, 'output_format': 'png', 'sync_mode': True, 'quality': 'low',
                          'input_fidelity': 'low', 'background': 'opaque'}).encode()
    reserve_generation()
    req = Request('https://fal.run/' + MODEL, data=payload, method='POST',
                  headers={'Authorization':'Key '+key, 'Content-Type':'application/json', 'User-Agent':'FontFiller/1.0'})
    try:
        with urlopen(req, timeout=100) as response: result=json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError('fal could not generate this batch. Please try again.') from exc
    images=result.get('images') or []; uri=images[0].get('url','') if images else ''
    if not uri.startswith('data:image/png;base64,'): raise ValueError('fal returned an unexpected image.')
    try: image=base64.b64decode(uri.split(',',1)[1], validate=True)
    except ValueError as exc: raise ValueError('fal returned an invalid image.') from exc
    crops=[]
    for ch, crop, warnings in bulk_grid.split(image, chars, size):
        crops.append({'character':ch, 'kind':'mark' if mark_mode else 'glyph', 'label': names[ch] if mark_mode else ch, 'letters': groups[names[ch]] if mark_mode else [ch], 'image':'data:image/png;base64,'+base64.b64encode(crop).decode('ascii') if crop else None, 'warnings':warnings})
    return jsonify(crops=crops)


@app.post('/api/bulk/apply-marks')
def bulk_apply_marks():
    data = uploaded_font(); chars = request.form.get('characters', ''); files = request.files.getlist('images')
    groups = missing_mark_groups(data); representatives = {v[0]: (k, v) for k, v in groups.items()}
    if not chars or len(chars) > 9 or len(chars) != len(files) or len(set(chars)) != len(chars) or any(ch not in representatives for ch in chars):
        raise ValueError('Choose up to nine distinct missing marks.')
    added = []; failed = []; warnings = []; processed = []
    for ch, file in zip(chars, files):
        name, letters = representatives[ch]; image = file.read(); success = False
        for letter in letters:
            try:
                data, _, checks = accents.build(read_font(data), data, letter, image_data=image, trace=trace_path, return_checks=True)
                added.append(letter); success = True
                for check, message in [('nudged', 'adjusted automatically'), ('overhang', 'extends beyond its advance'), ('collision', 'may overlap the letter'), ('unattached', 'may be disconnected')]:
                    if checks[check]: warnings.append(f'{letter}: accent {message}; review placement.')
            except ValueError as exc:
                failed.append({'character': letter, 'error': str(exc)})
        if success: processed.append(ch)
    return jsonify(font=encode_font(data), added=added, processed=processed, failed=failed, warnings=warnings,
                   remaining=missing_characters(data), mark_groups=missing_mark_groups(data))


@app.post('/api/bulk/apply')
def bulk_apply():
    data=uploaded_font()
    chars=request.form.get('characters','')
    files=request.files.getlist('images')
    if not chars or len(chars)>16 or len(chars)!=len(files) or len(set(chars))!=len(chars):
        raise ValueError('Choose up to 16 distinct reviewed characters.')
    missing=set(missing_characters(data))
    if any(ch not in missing for ch in chars): raise ValueError('Only missing supported characters can be added.')
    added=[]; failed=[]
    for ch, file in zip(chars,files):
        try:
            data=build_font(data,file.read(),ch)
            added.append(ch)
        except ValueError as exc: failed.append({'character':ch,'error':str(exc)})
    return jsonify(font=encode_font(data), added=added, failed=failed, remaining=missing_characters(data))


@app.post('/api/export')
def export():
    data=uploaded_font(); ch=request.form.get('character','')
    image=request.files.get('image')
    method=request.form.get('method','generated')
    flip = method == 'flip'
    is_accent = method in ('accent','accent-ai')
    if len(ch)!=1 or ch not in SYMBOLS or (not image and not flip and method!='accent'): raise ValueError('Generate a character first.')
    if is_accent and ch not in accents.BASES: raise ValueError('Choose a supported accented letter.')
    image_data=image.read() if image else None
    def bounded(name, default, low, high):
        try: value=float(request.form.get(name,default))
        except (ValueError, TypeError): raise ValueError('Invalid adjustment.')
        if not low<=value<=high: raise ValueError('Adjustment is out of range.')
        return value
    if is_accent:
        data,source,checks=accents.build(read_font(data),data,ch,bounded('scale',1,.5,1.5),bounded('offset',0,-.5,.5),bounded('horizontal',0,-.5,.5),image_data if method=='accent-ai' else None,trace_path,return_checks=True)
    else:
        data=build_font(data,image_data,ch,bounded('scale',1,.5,1.5),bounded('spacing',1,0,3),bounded('offset',0,-.5,.5),flip=flip)
        source,warning='',False
    is_cff = 'CFF ' in read_font(data)
    extension, mime = ('otf', 'font/otf') if is_cff else ('ttf', 'font/ttf')
    response=send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=f'font-filler.{extension}')
    if is_accent:
        response.headers['X-Accent-Source']=source
        response.headers['X-Accent-Overhang']='1' if checks['overhang'] else '0'
        response.headers['X-Accent-Nudged']='1' if checks['nudged'] else '0'
        response.headers['X-Accent-Collision']='1' if checks['collision'] else '0'
        response.headers['X-Accent-Unattached']='1' if checks['unattached'] else '0'
    return response

if __name__=='__main__': app.run(host='127.0.0.1',port=int(os.getenv('PORT','5050')),debug=False)
