"""Build a local, reproducible comparison of outline-reuse recipes."""
import html
import hashlib
import io
import json
import sys
from pathlib import Path
from urllib.parse import quote
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import app
import accents

OUT = Path(__file__).resolve().parent
RECIPES = [('.', '•'), ('.', 'ċ'), ('^', 'š'), ('-', 'ū'), ('+ -', '±'),
           ('>', '›'), ('<', '‹'), ('<', '«'), ('>', '»'), ('”', '“'),
           ('“', '”'), ('-', '–'), ('-', '—'), ('.', '…'), ('o', 'º'),
           ('o', 'å'), ('. -', '÷')]
ACCENTS = {'ċ': 'dot above', 'š': 'caron', 'ū': 'macron', 'å': 'ring'}

def stripped(data):
    font = TTFont(io.BytesIO(data))
    remove = set()
    for family in ACCENTS.values():
        remove.update(accents.FAMILY_CHARS[family]); remove.update(accents.MARKS[family])
    for table in font['cmap'].tables:
        if table.isUnicode():
            for c in remove: table.cmap.pop(ord(c), None)
    out = io.BytesIO(); font.save(out)
    return out.getvalue()

def set_mapping(font, char, name):
    for table in font['cmap'].tables:
        if table.isUnicode():
            if name is None: table.cmap.pop(ord(char), None)
            else: table.cmap[ord(char)] = name

def main():
    sections=[]; styles=[]; results=[]
    for i, path in enumerate(sorted((ROOT/'testFonts').iterdir())):
        if path.suffix.lower() not in ('.ttf', '.otf'): continue
        original=path.read_bytes(); original_font=app.read_font(original); original_map=original_font.getBestCmap()
        data=stripped(original); outputs={}; rows=[]
        for source, char in RECIPES:
            font=app.read_font(data)
            try:
                if char in ACCENTS:
                    mark, label, _ = accents.sources(font,char)
                    expected={'ċ':'period','š':'flipped circumflex','ū':'hyphen','å':'lowercase o'}[char]
                    if label != expected: raise ValueError('fallback unavailable (selected '+label+')')
                    data, _, checks=accents.build(font,data,char,return_checks=True)
                    notes=', '.join(k for k,v in checks.items() if v) or 'built'
                else:
                    if not app.reusable(font,char): raise ValueError('source glyph missing')
                    data=app.build_font(data,None,char,reuse=True); notes='built'
                font=app.read_font(data); outputs[char]=font.getBestCmap()[ord(char)]
                # Keep the original quote as the source for its opposite.
                if char in '“”':
                    set_mapping(font,char,original_map.get(ord(char)))
                    out=io.BytesIO();font.save(out);data=out.getvalue()
                rows.append((source,char,notes,True))
            except Exception as exc:
                rows.append((source,char,str(exc),False))
        font=app.read_font(data)
        for ch, name in outputs.items(): set_mapping(font,ch,name)
        out=io.BytesIO();font.save(out)
        filename=f'trial-{i}{path.suffix.lower()}'; (OUT/filename).write_bytes(out.getvalue())
        revision=hashlib.sha256(out.getvalue()).hexdigest()[:12]
        styles.append(f"@font-face{{font-family:original{i};src:url('../../testFonts/{quote(path.name)}')}} @font-face{{font-family:trial{i};src:url('{filename}?v={revision}')}}")
        cells=[]
        for source,char,note,ok in rows:
            original_exists=app.has_outline(original_font,original_map.get(ord(char)))
            source_exists=all(app.has_outline(original_font,original_map.get(ord(c))) for c in source if c != ' ')
            cells.append('<tr><th>'+html.escape(source)+' → '+html.escape(char)+'</th><td class="glyph orig'+str(i)+'">'+(html.escape(source) if source_exists else '—')+'</td><td class="glyph trial'+str(i)+'">'+(html.escape(char) if ok else '—')+'</td><td class="glyph orig'+str(i)+'">'+(html.escape(char) if original_exists else '—')+'</td><td>'+html.escape(note)+'</td></tr>')
        styles.append(f'.orig{i}{{font-family:original{i}}}.trial{i}{{font-family:trial{i}}}')
        success=sum(row[3] for row in rows)
        sections.append(f'<section><h2>{html.escape(path.name)}</h2><p>{success}/{len(rows)} recipes built · <a href="{filename}" download>Download trial font</a></p><div class="scroll"><table><thead><tr><th>Recipe</th><th>Source</th><th>Generated</th><th>Original, if present</th><th>Result</th></tr></thead><tbody>{"".join(cells)}</tbody></table></div><div class="sample trial{i}" contenteditable="true" spellcheck="false">ċ š ū å • ± ‹ › « » “ ” – — … º ÷</div><small>Editable trial text</small></section>')
        results.append({'font':path.name,'built':success,'recipes':len(rows),'issues':[{'character':c,'reason':n} for _,c,n,ok in rows if not ok]})
        print(path.name,success,'/',len(rows), flush=True)
    page='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Outline reuse review</title><style>'''+''.join(styles)+'''*{box-sizing:border-box}body{font:15px/1.5 system-ui,sans-serif;background:#f4f3ef;color:#222;margin:0}main{max-width:1100px;margin:auto;padding:36px 20px}h1{font-size:2.5rem;letter-spacing:-.04em}section{background:white;border:1px solid #ddd;border-radius:10px;padding:20px;margin:25px 0}section h2{margin:0}p{color:#555}a{color:#276476}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{border-bottom:1px solid #eee;text-align:left;padding:8px;vertical-align:middle}thead th{font:600 12px system-ui;color:#666;text-transform:uppercase}.glyph{font-size:42px;line-height:1.4;color:#111;overflow-wrap:anywhere}.sample{font-size:38px;line-height:1.5;padding:12px;border:1px dashed #ccc;margin-top:15px;overflow-wrap:anywhere}small{color:#666}td:last-child{font-size:13px;color:#555}</style></head><body><main><h1>Outline reuse review</h1><p>Each test font is shown with source outlines, generated results, and the original character when the font already has one. Accent tests deliberately hide competing accents so that period, caret, hyphen, and o fallbacks are exercised. Quote pairs are independently built from the original opposite quote. A dash indicates an unavailable source or original glyph. Generated fonts are experimental copies for visual review.</p>'''+''.join(sections)+'''</main></body></html>'''
    (OUT/'index.html').write_text(page)
    (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__': main()
