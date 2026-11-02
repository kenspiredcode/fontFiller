import json,subprocess
from pathlib import Path
import build_trial as b

contexts='AVWTLYFPaehno.,)'

def shape(font,text):
    raw=subprocess.check_output(['hb-shape',str(font),text,'--output-format=json','--features=-liga,-clig'],text=True)
    return json.loads(raw)

def positions(v):return [(x['dx'],x['dy'],x['ax'],x['ay']) for x in v]

def main():
    for title,file in b.CASES:
        original=b.ROOT/'testFonts'/file;trial=Path(__file__).parent/('trial-'+file);total=0;nonzero=0
        for accented,base in b.CHARS.items():
            for context in contexts:
                for a,c in [(context+base,context+accented),(base+context,accented+context)]:
                    expected=shape(original,a);actual=shape(trial,c)
                    if positions(expected)!=positions(actual):raise AssertionError(f'{title}: {a!r} -> {c!r}: {positions(expected)} != {positions(actual)}')
                    unkerned=json.loads(subprocess.check_output(['hb-shape',str(original),a,'--output-format=json','--features=-kern,-liga,-clig'],text=True))
                    if positions(expected)!=positions(unkerned):nonzero+=1
                    total+=1
        print(title, f'{total} pairs matched, including {nonzero} with nonzero kerning')
if __name__=='__main__':main()
