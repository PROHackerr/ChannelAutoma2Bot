import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, IO, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageStat
from django.conf import settings


@dataclass
class Font:
    id: str
    name: str
    path: Path


class _Fonts(dict):
    def __init__(self):
        available_fonts = {}
        fonts_info_file = settings.AVAILABLE_FONTS

        with open(fonts_info_file) as file:
            fonts_info = json.load(file)

        sys_fonts = fonts_info.get(sys.platform, {})
        for font_id, values in sys_fonts.get('fonts', {}).items():
            try:
                ImageFont.truetype(values['path'], 14)
                available_fonts[font_id] = Font(name=values['name'], path=Path(values['path']), id=font_id)
            except OSError:
                continue

        if 'default' not in sys_fonts or sys_fonts['default'] not in available_fonts:
            raise OSError('Default font not defined or not available')

        self.default_font: Font = available_fonts[sys_fonts['default']]
        self.available_fonts: Dict[str, Font] = available_fonts
        super(_Fonts, self).__init__(self.available_fonts)

    def __getitem__(self, name: str) -> Font:
        return self.get_font(name)

    def get(self, font: str) -> Font:
        return self.get_font(font)

    def get_font(self, font_name: str = None, fallback: str = None) -> Font:
        return self.available_fonts.get(font_name, fallback) or self.default_font


Fonts = _Fonts()


def get_text_position(position: str, image_size: Tuple[int, int], text_size: Tuple[int, int]):
    x = 5
    if position in 'nsc':
        x = (image_size[0] - text_size[0]) // 2
    elif position in 'nese':
        x = image_size[0] - text_size[0] - 5

    y = 5
    if position in 'wec':
        y = (image_size[1] - text_size[1]) // 2
    elif position in 'swse':
        y = image_size[1] - text_size[1] - 5

    return x, y


def image_brightness(image: Image) -> float:
    stat = ImageStat.Stat(image)
    r, g, b, a = stat.mean
    return math.sqrt(0.241 * (r ** 2) + 0.691 * (g ** 2) + 0.068 * (b ** 2))


def watermark_text(in_image: IO or str or Path,
                   out_buffer: IO or str or Path,
                   text: str,
                   file_extension: str = None,
                   pos: Tuple[int, int] or str = None,
                   colour: Tuple[int, int, int] = None,
                   font: str or Font = None,
                   font_size: int = None,
                   font_size_percentage: int = None,
                   alpha: int = None):
    font_path = str((font if isinstance(font, Font) else Fonts.get_font(font)).path)
    if not isinstance(out_buffer, (str, Path)) and not file_extension:
        raise AttributeError('If out_image is a Buffer file_extension must be set')

    photo = Image.open(in_image).convert('RGBA')
    txt = Image.new('RGBA', photo.size, (255, 255, 255, 0))
    drawing = ImageDraw.Draw(txt)

    if not font_size or font_size_percentage:
        font_size_percentage = font_size_percentage or 50
        fontsize = 1
        img_fraction = font_size_percentage / 100

        font = ImageFont.truetype(font_path, fontsize)
        breakpoint = img_fraction * photo.size[0]
        jumpsize = 75
        while True:
            if font.getsize(text)[0] < breakpoint:
                fontsize += jumpsize
            else:
                jumpsize = int(jumpsize / 2)
                fontsize -= jumpsize
            font = ImageFont.truetype(font_path, fontsize)
            if jumpsize <= 1:
                break
    else:
        font = ImageFont.truetype(font_path, font_size)

    real_pos = pos or (0, 0)
    text_size = drawing.multiline_textsize(text, font)
    align = 'left'
    if isinstance(pos, str):
        real_pos = get_text_position(pos, photo.size, text_size)
        if pos in 'ns':
            align = 'center'
        elif pos in 'nese':
            align = 'right'

    if not colour:
        cropped = photo.crop((*real_pos, real_pos[0] + text_size[0], real_pos[1] + text_size[1]))
        brightness = image_brightness(cropped)
        if brightness > 120:
            colour = (0, 0, 0, alpha)
        else:
            colour = (255, 255, 255, alpha)

    drawing.text(real_pos, text, fill=colour, font=font, align=align)
    out = Image.alpha_composite(photo, txt)
    out.save(out_buffer, format='png', lossless=True)

    if hasattr(out_buffer, 'seek'):
        out_buffer.seek(0)
