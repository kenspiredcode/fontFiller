import io
import unittest
from PIL import Image, ImageDraw
import accents


def mark_image(strokes):
    image = Image.new('L', (160, 160), 255)
    draw = ImageDraw.Draw(image)
    for x in strokes:
        draw.polygon([(x, 120), (x+12, 120), (x+62, 35), (x+50, 35)], fill=0)
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


class DoubleAcuteIsolation(unittest.TestCase):
    def test_slanted_strokes_with_overlapping_column_ranges(self):
        image = mark_image([20, 45])
        result = accents.ai_mark(image, lambda _: 'M 0 0 L 10 0 L 10 20 Z', 'double acute')
        self.assertTrue(result)

    def test_single_or_three_strokes_are_rejected(self):
        for strokes in ([20], [10, 35, 60]):
            with self.subTest(strokes=strokes), self.assertRaises(ValueError):
                accents.ai_mark(mark_image(strokes), lambda _: '', 'double acute')
