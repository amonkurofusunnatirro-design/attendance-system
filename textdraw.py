"""映像にUnicode文字（日本語・ラテン文字）を描画します（Pillow、必要な小領域のみ変換）。"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FONTS = ["C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/msgothic.ttc",
          "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
          "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", "/Library/Fonts/Arial Unicode.ttf",
          "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
          "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
_cache = {}


def _font(size):
    if size not in _cache:
        f = None
        for p in _FONTS:
            if os.path.exists(p):
                try:
                    f = ImageFont.truetype(p, size)
                    break
                except OSError:
                    pass
        _cache[size] = f or ImageFont.load_default()
    return _cache[size]


def text_size(text, size=18):
    b = _font(size).getbbox(text)
    return b[2] - b[0], b[3] - b[1]


def put_text(img, text, org, size=18, color=(255, 255, 255)):
    f = _font(size)
    b = f.getbbox(text)
    w, h = b[2] - b[0] + 2, b[3] - b[1] + 2
    x, y = int(org[0]), int(org[1])
    H, W = img.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0:
        return img
    patch = img[y0:y1, x0:x1]
    pil = Image.fromarray(np.ascontiguousarray(patch[:, :, ::-1]))
    ImageDraw.Draw(pil).text((x - x0 - b[0], y - y0 - b[1]), text, font=f, fill=(color[2], color[1], color[0]))
    patch[:] = np.asarray(pil)[:, :, ::-1]
    return img
