"""Run one batch experiment directly using the app's fal model settings.

Set FAL_KEY in the environment, then run from the project
root: python3 experiment/multi-character/run_fal.py --count 5 --output /tmp/fal-five.png
Each invocation bypasses the app rate gate and may incur a charge.
"""
import argparse
import base64
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app import MODEL, specimen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--count', type=int, choices=(5, 9, 10, 16, 25), required=True)
parser.add_argument('--set', choices=('symbols', 'punctuation', 'letters'), default='symbols', help='Character set for 4x4 experiments')
parser.add_argument('--font', type=Path, default=ROOT / 'testFonts/ostrich-regular.ttf')
parser.add_argument('--output', type=Path, required=True, help='New output PNG path')
args = parser.parse_args()
if args.output.exists():
    parser.error('output already exists')
key = os.environ.get('FAL_KEY')
if not key:
    parser.error('FAL_KEY must be set')
reference = 'data:image/png;base64,' + base64.b64encode(specimen(args.font.read_bytes())).decode('ascii')
layouts = {5: 'one row of five equal-width cells: &, @, %, $, ? from left to right',
           9: 'a 3 by 3 grid: row 1 &, @, %; row 2 $, ?, !; row 3 +, =, #; read left to right',
           10: 'two rows of five equal-width cells: top row &, @, %, $, ?; bottom row !, +, =, #, *; read left to right',
           16: 'a 4 by 4 grid: row 1 &, @, %, $; row 2 ?, !, +, =; row 3 #, *, /, :; row 4 <, >, £, €; read left to right',
           25: 'a 5 by 5 grid: row 1 &, @, %, $, ?; row 2 !, +, =, #, *; row 3 (, ), [, ], /; row 4 :, ;, <, >, ^; row 5 ~, |, £, €, ¥; read left to right'}
if args.count != 16 and args.set != 'symbols':
    parser.error('--set applies only to --count 16')
sets = {
    'symbols': layouts[16],
    'punctuation': 'a 4 by 4 grid: row 1 &, @, %, $; row 2 ?, !, +, =; row 3 #, *, /, :; row 4 ;, ~, £, €; read left to right',
    'letters': 'a 4 by 4 grid of uppercase letters and digits: row 1 G, Q, R, S; row 2 T, U, V, W; row 3 X, Y, Z, 2; row 4 3, 5, 7, 9; read left to right',
}
layout = sets[args.set] if args.count == 16 else layouts[args.count]
prompt = (f'Use the provided image as a typeface style reference. Create exactly {args.count} characters in {layout}. '
          'Match the typeface stroke weight, proportions, slant and distinctive details. '
          'Show one black glyph per cell on a plain white background, centered with generous whitespace. '
          'No labels, borders, extra characters, texture or decoration.')
payload = json.dumps({'prompt': prompt, 'image_urls': [reference], 'image_size': '1024x1024',
                      'num_images': 1, 'output_format': 'png', 'sync_mode': True,
                      'quality': 'low', 'input_fidelity': 'low', 'background': 'opaque'}).encode()
req = Request('https://fal.run/' + MODEL, data=payload, method='POST',
              headers={'Authorization': 'Key ' + key, 'Content-Type': 'application/json', 'User-Agent': 'FontFiller/1.0'})
with urlopen(req, timeout=100) as response:
    result = json.load(response)
uri = result['images'][0]['url']
if not uri.startswith('data:image/png;base64,'):
    raise ValueError('fal returned an unexpected image')
args.output.write_bytes(base64.b64decode(uri.split(',', 1)[1], validate=True))
print(f'Saved {args.output}')
