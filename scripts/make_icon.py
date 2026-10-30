#!/usr/bin/env python3
# Usage: python3 scripts/make_icon.py site/icons   (needs Pillow and numpy)
"""Catalyst app icon: a bright lightning bolt made of five bands (red, yellow, green, blue, pink) on a
soft white rounded-square background, with a soft glow, a faint shadow and three small sparkles.

Writes every size the web manifest and iOS use: rounded icons (16-1024 px, transparent corners),
opaque Apple touch icons (iOS rounds them itself), maskable icons (art inside the 80% safe zone) and a
1024 px App Store square.
"""
import math
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 2048  # master canvas; every size is downsampled from it
BANDS = [(255, 77, 94), (255, 196, 46), (44, 204, 120), (59, 130, 246), (255, 95, 183)]  # red, yellow, green, blue, pink
# the bolt, in unit coordinates: top edge, long left edge, step, tip, step back, up to the top
BOLT = [(0.56, 0.08), (0.27, 0.56), (0.47, 0.56), (0.40, 0.92), (0.74, 0.42), (0.54, 0.42), (0.72, 0.08)]


def lerp(a, b, t):
    return a + (b - a) * t


def blur(im, r):
    """Gaussian blur in premultiplied alpha, so transparent pixels do not bleed grey into colours."""
    a = np.asarray(im, dtype=np.float32) / 255.0
    pm = a.copy()
    pm[..., :3] *= pm[..., 3:4]
    chans = [Image.fromarray((pm[..., i] * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(r)) for i in range(4)]
    b = np.stack([np.asarray(c, dtype=np.float32) / 255.0 for c in chans], axis=-1)
    al = b[..., 3:4]
    rgb = np.where(al > 1e-4, b[..., :3] / np.maximum(al, 1e-4), 0)
    return Image.fromarray((np.concatenate([np.clip(rgb, 0, 1), al], axis=-1) * 255).round().astype("uint8"), "RGBA")


def background():
    """Soft white with a faint cool tint toward the bottom and two pale colour washes."""
    col = np.linspace(0, 1, S, dtype=np.float32)[:, None]
    top, bot = np.array([255, 255, 255], np.float32), np.array([238, 240, 248], np.float32)
    rgb = top + (bot - top) * col[..., None]
    bg = Image.fromarray(np.broadcast_to(rgb, (S, S, 3)).astype("uint8"), "RGB").convert("RGBA")
    wash = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    d = ImageDraw.Draw(wash)
    d.ellipse([S * 0.50, S * -0.20, S * 1.30, S * 0.60], fill=(255, 236, 200, 90))   # warm, top right
    d.ellipse([S * -0.30, S * 0.55, S * 0.50, S * 1.35], fill=(226, 232, 255, 110))  # cool, bottom left
    return Image.alpha_composite(bg, blur(wash, S * 0.14))


def bolt_mask(scale=1.0, offset=(0.0, 0.0)):
    """The bolt silhouette with rounded corners (blur, then threshold)."""
    cx, cy = 0.5, 0.5
    pts = [((cx + (x - cx) * scale + offset[0]) * S, (cy + (y - cy) * scale + offset[1]) * S) for x, y in BOLT]
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    m = m.filter(ImageFilter.GaussianBlur(S * 0.012 * scale))
    return m.point(lambda v: 255 if v > 128 else 0).filter(ImageFilter.GaussianBlur(1.2)), pts


def stripes(scale=1.0, gap=0.012):
    """Five horizontal bands spanning the bolt's height, with thin gaps between them."""
    y0, y1 = 0.5 + (BOLT[0][1] - 0.5) * scale, 0.5 + (BOLT[3][1] - 0.5) * scale
    im = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    h = (y1 - y0) / 5
    for i, c in enumerate(BANDS):
        top = y0 + i * h + (gap * scale / 2 if i else -0.05)
        bottom = y0 + (i + 1) * h - (gap * scale / 2 if i < 4 else -0.05)
        d.rectangle([0, top * S, S, bottom * S], fill=c + (255,))
    return im


def sparkle(draw, x, y, r, color):
    """A four-point star."""
    pts = []
    for k in range(8):
        a = math.pi / 4 * k - math.pi / 2
        rr = r if k % 2 == 0 else r * 0.28
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    draw.polygon(pts, fill=color)


def art(scale=1.0):
    """Bolt, glow, shadow and sparkles on a transparent canvas."""
    out = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    mask, pts = bolt_mask(scale)
    bands = stripes(scale)
    # soft colour glow behind the bolt
    glow_src = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    glow_src.paste(bands, (0, 0), mask)
    glow = blur(glow_src, S * 0.045 * scale)
    glow.putalpha(glow.getchannel("A").point(lambda v: int(v * 0.55)))
    # a faint cool shadow below
    sh_mask, _ = bolt_mask(scale, (0.0, 0.022 * scale))
    shadow = Image.new("RGBA", (S, S), (70, 80, 130, 0))
    shadow.putalpha(sh_mask.point(lambda v: int(v * 0.30)))
    out = Image.alpha_composite(out, blur(shadow, S * 0.02 * scale))
    out = Image.alpha_composite(out, glow)
    # the bolt itself: bands clipped to the silhouette, with a thin white rim
    rim_mask = mask.filter(ImageFilter.MaxFilter(int(S * 0.010 * scale) | 1))
    rim = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    rim.putalpha(rim_mask)
    out = Image.alpha_composite(out, rim)
    body = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    body.paste(bands, (0, 0), mask)
    out = Image.alpha_composite(out, body)
    # a gentle highlight along the upper-left of the bolt
    hl = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    hd = ImageDraw.Draw(hl)
    a, b = pts[0], pts[1]
    inset = S * 0.018 * scale
    hd.line([(lerp(a[0], b[0], 0.08) + inset, lerp(a[1], b[1], 0.08) + inset * 0.3),
             (lerp(a[0], b[0], 0.55) + inset, lerp(a[1], b[1], 0.55) + inset * 0.3)], fill=(255, 255, 255, 150), width=int(S * 0.012 * scale))
    hl.putalpha(Image.fromarray(np.minimum(np.asarray(hl.getchannel("A")), np.asarray(mask))))
    out = Image.alpha_composite(out, blur(hl, S * 0.004 * scale))
    # sparkles
    sp = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    sd = ImageDraw.Draw(sp)
    c = lambda u, v: (0.5 + (u - 0.5) * scale, 0.5 + (v - 0.5) * scale)
    for (u, v), r, col in (((0.25, 0.25), 0.055, BANDS[3]), ((0.80, 0.70), 0.045, BANDS[4]), ((0.80, 0.20), 0.030, BANDS[1])):
        x, y = c(u, v)
        sparkle(sd, x * S, y * S, r * S * scale, col + (255,))
    sp_glow = blur(sp, S * 0.012 * scale)
    out = Image.alpha_composite(out, sp_glow)
    return Image.alpha_composite(out, sp)


def rounded(img):
    """iOS-style rounded square (corner radius 22.5%) with transparent corners."""
    m = Image.new("L", (S * 2, S * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, S * 2 - 1, S * 2 - 1], radius=int(S * 2 * 0.225), fill=255)
    m = m.resize((S, S), Image.LANCZOS)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), m)
    return out


def main(out_dir):
    square = Image.alpha_composite(background(), art(1.0))
    safe = Image.alpha_composite(background(), art(0.80))   # maskable: art inside the 80% safe zone
    icon = rounded(square)
    for n in (1024, 512, 384, 256, 192, 144, 128, 96, 72, 48, 32, 16):
        icon.resize((n, n), Image.LANCZOS).save(f"{out_dir}/icon-{n}.png")
    for n in (180, 167, 152, 120, 87, 80, 76, 60, 58, 40):
        square.resize((n, n), Image.LANCZOS).convert("RGB").save(f"{out_dir}/apple-touch-icon-{n}.png")
    square.resize((180, 180), Image.LANCZOS).convert("RGB").save(f"{out_dir}/apple-touch-icon.png")
    square.resize((1024, 1024), Image.LANCZOS).convert("RGB").save(f"{out_dir}/app-store-1024.png")
    for n in (192, 512):
        safe.resize((n, n), Image.LANCZOS).save(f"{out_dir}/maskable-{n}.png")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site/icons")
