import io
import unittest
from PIL import Image, ImageDraw
import bulk_grid


class GridSeparationTests(unittest.TestCase):
    def test_moves_grid_seam_into_whitespace(self):
        image = Image.new('L', (200, 200), 0)
        draw = ImageDraw.Draw(image)
        for top in (20, 120):
            draw.rectangle((30, top, 105, top + 40), fill=255)
            draw.rectangle((120, top, 170, top + 40), fill=255)
        cuts, warnings = bulk_grid.boundaries(image, 2, 'x')
        self.assertGreater(cuts[1], 105)
        self.assertLess(cuts[1], 120)
        self.assertFalse(warnings)

    def test_crossing_ink_produces_crops_with_warnings(self):
        image = Image.new('RGB', (200, 200), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((25, 25, 175, 75), fill='black')
        draw.rectangle((25, 125, 175, 175), fill='black')
        data = io.BytesIO(); image.save(data, format='PNG')
        results = bulk_grid.split(data.getvalue(), 'ABCD', 2)
        self.assertEqual(len(results), 4)
        self.assertTrue(all(crop and warnings for _, crop, warnings in results))


if __name__ == '__main__': unittest.main()
