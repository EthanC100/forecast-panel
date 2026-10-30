#!/usr/bin/env python3
# Usage: python3 scripts/make_icon.py site/icons   (needs Pillow and numpy)
"""Prism app icon: a translucent glass triangle prism on a soft white background; a thin white beam
enters the left face and leaves the right face as five bands (red, yellow, green, blue, pink)."""
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageChops

S = 2048  # master canvas; downsampled for every size

def lerp(a, b, t): return a + (b - a) * t

def blur(im, r):
    """Gaussian blur in premultiplied alpha, so transparent pixels do not bleed grey."""
    import numpy as np
    a = np.asarray(im, dtype=np.float32) / 255.0
    pm = a.copy(); pm[..., :3] *= pm[..., 3:4]
    chans = [Image.fromarray((pm[..., i] * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(r)) for i in range(4)]
    b = np.stack([np.asarray(c, dtype=np.float32) / 255.0 for c in chans], axis=-1)
    al = b[..., 3:4]
    rgb = np.where(al > 1e-4, b[..., :3] / np.maximum(al, 1e-4), 0)
    out = np.concatenate([np.clip(rgb, 0, 1), al], axis=-1)
    return Image.fromarray((out * 255).round().astype("uint8"), "RGBA")
def pt(a, b, t): return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))
def P(x, y): return (x * S, y * S)

BANDS = [(255, 77, 94), (255, 196, 46), (44, 204, 120), (59, 130, 246), (255, 95, 183)]  # red, yellow, green, blue, pink

def vertical_gradient(top, bottom):
    g = Image.new("RGBA", (1, S))
    for y in range(S):
        t = y / (S - 1)
        g.putpixel((0, y), tuple(int(lerp(top[i], bottom[i], t)) for i in range(4)))
    return g.resize((S, S))

def linear_gradient(c0, c1, angle_deg):
    import math
    g = Image.new("RGBA", (S, S))
    px = g.load()
    a = math.radians(angle_deg); dx, dy = math.cos(a), math.sin(a)
    # project onto direction, normalised to 0..1 over the canvas diagonal
    lo = min(0, dx * S) + min(0, dy * S); hi = max(0, dx * S) + max(0, dy * S)
    step = 4
    small = Image.new("RGBA", (S // step, S // step)); sp = small.load()
    for y in range(S // step):
        for x in range(S // step):
            t = ((x * step) * dx + (y * step) * dy - lo) / (hi - lo)
            sp[x, y] = tuple(int(lerp(c0[i], c1[i], t)) for i in range(4))
    return small.resize((S, S), Image.BILINEAR)

def mask_poly(pts, blur=0):
    m = Image.new("L", (S, S), 0); ImageDraw.Draw(m).polygon(pts, fill=255)
    return m.filter(ImageFilter.GaussianBlur(blur)) if blur else m

def build(full_bleed=False):
    # background: soft white with a faint cool tint toward the bottom
    bg = vertical_gradient((255, 255, 255, 255), (236, 239, 247, 255))
    tint = Image.new("RGBA", (S, S), (0, 0, 0, 0)); td = ImageDraw.Draw(tint)
    td.ellipse([S * 0.45, S * 0.35, S * 1.25, S * 1.15], fill=(255, 225, 240, 70))
    td.ellipse([S * -0.25, S * 0.55, S * 0.55, S * 1.3], fill=(225, 236, 255, 90))
    bg = Image.alpha_composite(bg, blur(tint, S * 0.12))
    img = bg.copy()

    top, bl, br = P(0.50, 0.215), P(0.235, 0.735), P(0.765, 0.735)
    entry = pt(top, bl, 0.56)
    ex0, ex1 = pt(top, br, 0.47), pt(top, br, 0.66)          # where the bands leave the right face
    out_x = 1.08 * S
    out_y0, out_y1 = 0.40 * S, 0.90 * S                       # where they reach the edge

    # bands outside the prism, with a soft glow
    bands = Image.new("RGBA", (S, S), (0, 0, 0, 0)); bd = ImageDraw.Draw(bands)
    for i, c in enumerate(BANDS):
        a0, a1 = pt(ex0, ex1, i / 5), pt(ex0, ex1, (i + 1) / 5)
        b0, b1 = (out_x, lerp(out_y0, out_y1, i / 5)), (out_x, lerp(out_y0, out_y1, (i + 1) / 5))
        bd.polygon([a0, b0, b1, a1], fill=c + (255,))
    glow = blur(bands, S * 0.03)
    glow.putalpha(glow.getchannel("A").point(lambda v: int(v * 0.55)))
    img = Image.alpha_composite(img, glow)
    img = Image.alpha_composite(img, bands)

    # the white beam, with a faint cool shadow so it reads on white
    beam_start = (-0.05 * S, 0.66 * S)
    w = S * 0.0145
    def beam_poly(p0, p1, w0, w1):
        import math
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]; L = math.hypot(dx, dy); nx, ny = -dy / L, dx / L
        return [(p0[0] + nx * w0, p0[1] + ny * w0), (p1[0] + nx * w1, p1[1] + ny * w1), (p1[0] - nx * w1, p1[1] - ny * w1), (p0[0] - nx * w0, p0[1] - ny * w0)]
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).polygon(beam_poly((beam_start[0], beam_start[1] + S * 0.006), (entry[0], entry[1] + S * 0.006), w * 1.25, w * 1.15), fill=(80, 100, 150, 60))
    img = Image.alpha_composite(img, blur(sh, S * 0.005))
    bm = Image.new("RGBA", (S, S), (0, 0, 0, 0)); bmd = ImageDraw.Draw(bm)
    bmd.polygon(beam_poly(beam_start, entry, w + S * 0.0035, w * 0.9 + S * 0.0035), fill=(150, 168, 210, 170))   # hairline edge
    bmd.polygon(beam_poly(beam_start, entry, w, w * 0.9), fill=(255, 255, 255, 255))
    halo = Image.new("RGBA", (S, S), (0, 0, 0, 0)); ImageDraw.Draw(halo).polygon(beam_poly(beam_start, entry, w * 1.6, w * 1.4), fill=(255, 255, 255, 200)); halo = blur(halo, S * 0.008)
    img = Image.alpha_composite(img, bm); img = Image.alpha_composite(img, halo)
    img = Image.alpha_composite(img, core) if False else img

    # inside the glass: the beam fanning into faint colour on its way to the far face
    inner = Image.new("RGBA", (S, S), (0, 0, 0, 0)); idr = ImageDraw.Draw(inner)
    for i, c in enumerate(BANDS):
        a0, a1 = pt(ex0, ex1, i / 5), pt(ex0, ex1, (i + 1) / 5)
        idr.polygon([pt(entry, (entry[0], entry[1] - w * 0.8), 0), (entry[0], entry[1] - w * 0.6 + i * w * 0.3), a0, a1], fill=c + (120,))
    tri = [top, bl, br]
    inner = blur(inner, S * 0.006)
    inner.putalpha(ImageChops.multiply(inner.getchannel("A"), mask_poly(tri)))

    # glass body: translucent, lighter at the top-left, a cool tint toward the base
    body = linear_gradient((255, 255, 255, 115), (188, 206, 244, 95), 70)
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon([(x, y + S * 0.035) for x, y in tri], fill=(60, 70, 110, 70))
    img = Image.alpha_composite(img, blur(shadow, S * 0.03))
    glass = Image.new("RGBA", (S, S), (0, 0, 0, 0)); glass.paste(body, (0, 0), mask_poly(tri))
    img = Image.alpha_composite(img, glass)
    img = Image.alpha_composite(img, inner)
    # facet: a slightly darker right half suggests depth
    facet = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(facet).polygon([top, P(0.5, 0.735), br], fill=(150, 170, 215, 28))
    img = Image.alpha_composite(img, facet)
    # edges: bright rim with a soft inner line
    edge = Image.new("RGBA", (S, S), (0, 0, 0, 0)); ed = ImageDraw.Draw(edge)
    ed.line(tri + [top], fill=(255, 255, 255, 235), width=int(S * 0.012), joint="curve")
    ed.line([pt(top, bl, 0.06), pt(top, bl, 0.42)], fill=(255, 255, 255, 255), width=int(S * 0.008))  # specular on the lit face
    rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(rim).line(tri + [top], fill=(120, 140, 190, 120), width=int(S * 0.02), joint="curve")
    img = Image.alpha_composite(img, blur(rim, S * 0.004))
    img = Image.alpha_composite(img, edge)
    for p in tri:
        ImageDraw.Draw(img).ellipse([p[0] - S * 0.006, p[1] - S * 0.006, p[0] + S * 0.006, p[1] + S * 0.006], fill=(255, 255, 255, 255))

    if full_bleed:
        return img
    # iOS-style rounded square (superellipse-ish radius 22.5%) with transparent corners
    m = Image.new("L", (S * 2, S * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, S * 2 - 1, S * 2 - 1], radius=int(S * 2 * 0.225), fill=255)
    m = m.resize((S, S), Image.LANCZOS)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0)); out.paste(img, (0, 0), m)
    return out

def maskable():
    # full-bleed background, artwork scaled into the 80% safe zone
    art = build(True)
    bg = art.crop((0, 0, 1, 1)).resize((S, S))
    bgfull = build(True)
    small = art.resize((int(S * 0.8), int(S * 0.8)), Image.LANCZOS)
    canvas = bgfull.copy()
    base = Image.new("RGBA", (S, S)); base.paste(Image.new("RGBA", (S, S), (246, 247, 251, 255)))
    base = Image.alpha_composite(base, Image.new("RGBA", (S, S), (0, 0, 0, 0)))
    from PIL import ImageOps
    grad = Image.new("RGBA", (S, S))
    g = art.resize((S, S))
    canvas = Image.new("RGBA", (S, S), (244, 246, 251, 255))
    canvas.paste(small, (int(S * 0.1), int(S * 0.1)))
    return canvas

if __name__ == "__main__":
    out = sys.argv[1]
    rounded = build(False)
    square = build(True)
    rounded.save(out + "/prism-1024.png") if False else None
    rounded.resize((1024, 1024), Image.LANCZOS).save(out + "/icon-1024.png")
    for n in (512, 384, 256, 192, 144, 128, 96, 72, 48, 32, 16):
        rounded.resize((n, n), Image.LANCZOS).save(f"{out}/icon-{n}.png")
    # Apple touch icons: opaque squares; iOS applies its own rounded mask
    for n in (180, 167, 152, 120, 87, 80, 76, 60, 58, 40):
        square.resize((n, n), Image.LANCZOS).convert("RGB").save(f"{out}/apple-touch-icon-{n}.png")
    square.resize((180, 180), Image.LANCZOS).convert("RGB").save(f"{out}/apple-touch-icon.png")
    square.resize((1024, 1024), Image.LANCZOS).convert("RGB").save(f"{out}/app-store-1024.png")
    mk = maskable()
    for n in (192, 512):
        mk.resize((n, n), Image.LANCZOS).save(f"{out}/maskable-{n}.png")
