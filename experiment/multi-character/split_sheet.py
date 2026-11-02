"""Split the preliminary three-column sheet; review crops before tracing."""
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
image = Image.open(HERE / 'ostrich-sheet.png').convert('RGB')
for index, name in enumerate(('ampersand', 'at', 'percent')):
    left, right = image.width * index // 3, image.width * (index + 1) // 3
    crop = image.crop((left, 0, right, image.height))
    # Flag ink close to a crop edge; disconnected marks must stay in the same column.
    mask = crop.convert('L').point(lambda value: 255 if value < 200 else 0)
    bounds = mask.getbbox()
    if not bounds:
        raise ValueError(f'{name}: no dark pixels')
    margin = min(bounds[0], bounds[1], crop.width - bounds[2], crop.height - bounds[3])
    crop.save(HERE / f'ostrich-{name}.png')
    print(f'{name}: bounds={bounds}, minimum edge margin={margin}px')
