"""Separate glyph sheets using low-ink grid boundaries, with advisory warnings."""
import io
from PIL import Image, ImageOps


def boundaries(mask, count, axis):
    width, height = mask.size
    length = width if axis == 'x' else height
    px = mask.load()
    ink = ([sum(px[x, y] != 0 for y in range(height)) for x in range(width)] if axis == 'x'
           else [sum(px[x, y] != 0 for x in range(width)) for y in range(height)])
    cuts, warnings = [0], set()
    for i in range(1, count):
        target = round(i * length / count)
        radius = max(1, int(length / count * .24))
        low, high = max(cuts[-1] + 2, target - radius), min(length - 2, target + radius)
        point = min(range(low, high + 1), key=lambda v: (ink[v - 1] + ink[v], abs(v - target)))
        if ink[point - 1] + ink[point]: warnings.add(i)
        cuts.append(point)
    return cuts + [length], warnings


def split(image_data, characters, size):
    image = Image.open(io.BytesIO(image_data)).convert('RGB')
    if image.width * image.height > 12_000_000: raise ValueError('Generated image is too large.')
    if not characters or len(characters) > size * size: raise ValueError('Invalid character count.')
    mask = image.convert('L').point(lambda v: 255 if v < 200 else 0)
    xs, xwarn = boundaries(mask, size, 'x'); ys, ywarn = boundaries(mask, size, 'y')
    results = []
    for index, char in enumerate(characters):
        row, col = divmod(index, size)
        box = (xs[col], ys[row], xs[col+1], ys[row+1])
        cell = image.crop(box); bounds = mask.crop(box).getbbox(); warnings = []
        if not bounds:
            results.append((char, None, ['No visible glyph was found.']))
            continue
        if any(n in xwarn for n in (col, col+1)) or any(n in ywarn for n in (row, row+1)):
            warnings.append('The separator crosses ink; inspect this glyph for clipping.')
        if (col == 0 and bounds[0] == 0 or row == 0 and bounds[1] == 0 or
            col == size-1 and bounds[2] == cell.width or row == size-1 and bounds[3] == cell.height):
            warnings.append('The glyph touches the image edge and may be clipped.')
        crop = ImageOps.expand(cell.crop(bounds), border=max(20, round(max(cell.size)*.12)), fill='white')
        output = io.BytesIO(); crop.save(output, 'PNG', optimize=True)
        results.append((char, output.getvalue(), warnings))
    return results
